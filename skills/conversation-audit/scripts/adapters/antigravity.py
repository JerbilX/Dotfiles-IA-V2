#!/usr/bin/env python3
"""
Adaptador de transcripciones para el runtime Antigravity.
Parsea archivos transcript.jsonl del directorio brain de Antigravity.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import (
    ConversationMetadata,
    NormalizedStep,
    NormalizedToolCall,
    TranscriptAdapter,
    clean_title,
)


class AntigravityAdapter(TranscriptAdapter):
    """Adaptador para transcripciones generadas por Google Antigravity."""

    def resolve_path(self, target: Path) -> Path:
        """Resuelve la ruta física del archivo transcript.jsonl."""
        p = target.expanduser().resolve()
        if p.is_file():
            return p
        if p.is_dir():
            # Buscar en estructura brain típica
            cand1 = p / ".system_generated" / "logs" / "transcript.jsonl"
            if cand1.is_file():
                return cand1
            cand2 = p / "transcript.jsonl"
            if cand2.is_file():
                return cand2
        # Si es un ID de conversación (ej. UUID)
        home_brain = Path.home() / ".gemini" / "antigravity" / "brain" / target.name
        if home_brain.is_dir():
            cand = home_brain / ".system_generated" / "logs" / "transcript.jsonl"
            if cand.is_file():
                return cand
        return target

    def detect(self, path: Path) -> bool:
        """Detecta si el archivo corresponde al formato de Antigravity."""
        resolved = self.resolve_path(path)
        if not resolved.is_file():
            return False

        # Si el nombre es canónico
        if resolved.name in ("transcript.jsonl", "transcript_full.jsonl"):
            return True

        # Inspeccionar las primeras líneas
        try:
            with open(resolved, "r", encoding="utf-8") as f:
                for _ in range(5):
                    line = f.readline()
                    if not line:
                        break
                    data = json.loads(line)
                    if "step_index" in data and ("source" in data or "type" in data):
                        return True
        except Exception:
            return False
        return False

    def parse(self, path: Path) -> List[NormalizedStep]:
        """Parsea transcript.jsonl a una lista de NormalizedStep."""
        resolved = self.resolve_path(path)
        if not resolved.is_file():
            raise FileNotFoundError(f"No se encontró el archivo de transcripción: {path}")

        raw_records: List[Dict[str, Any]] = []
        with open(resolved, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    raw_records.append(record)
                except json.JSONDecodeError:
                    continue

        # El transcript no trae IDs que vinculen llamada y salida: cada GENERIC es la salida
        # de las llamadas del paso no-salida inmediatamente anterior. Ordenar por step_index
        # garantiza esa adyacencia (#237).
        raw_records.sort(key=lambda r: r.get("step_index") if isinstance(r.get("step_index"), int) else 0)

        normalized_steps: List[NormalizedStep] = []
        pending_tool_calls: List[NormalizedToolCall] = []

        for record in raw_records:
            step_idx = record.get("step_index", len(normalized_steps))
            source = str(record.get("source", "UNKNOWN"))
            step_type = str(record.get("type", "UNKNOWN"))
            status = str(record.get("status", "DONE"))
            created_at_str = record.get("created_at")
            created_at: Optional[datetime] = None
            if created_at_str:
                try:
                    # Soporte para Z y formato ISO 8601
                    ts = created_at_str.replace("Z", "+00:00")
                    created_at = datetime.fromisoformat(ts)
                except Exception:
                    pass

            content = record.get("content")
            thinking = record.get("thinking")
            truncated = record.get("truncated_fields", [])
            tokens = record.get("tokens", {})

            step_tool_calls: List[NormalizedToolCall] = []
            for tc in record.get("tool_calls", []):
                tc_name = tc.get("name", "unknown_tool")
                raw_args = tc.get("args", {})
                args = raw_args
                if isinstance(raw_args, str):
                    try:
                        args = json.loads(raw_args)
                    except Exception:
                        args = {"raw": raw_args}

                tool_action = args.get("toolAction", "")
                tool_summary = args.get("toolSummary", "")

                norm_tc = NormalizedToolCall(
                    name=tc_name,
                    args=args,
                    tool_action=tool_action,
                    tool_summary=tool_summary,
                    call_id=tc.get("id"),
                    status="DONE",
                )
                step_tool_calls.append(norm_tc)

            is_output_step = step_type in ("GENERIC", "TOOL_OUTPUT")
            if not is_output_step:
                # Las llamadas previas sin salida registrada (pasos faltantes) se descartan
                # para que no desplacen el emparejamiento de las siguientes (#237).
                pending_tool_calls = list(step_tool_calls)

            # Si es un step de resultado de herramienta (ej. GENERIC con output/error)
            if is_output_step and pending_tool_calls:
                last_call = pending_tool_calls.pop(0)
                last_call.raw_output = content

                is_error = False
                if status == "ERROR":
                    is_error = True
                elif content:
                    if "Encountered error in tool execution" in content:
                        is_error = True
                    elif "There were sandbox errors that may or may not be related to the failure" in content:
                        is_error = True
                    elif last_call.name in ("run_command", "bash", "execute_command"):
                        # Detección de códigos de retorno no cero (ej. The command exited with code 1)
                        code_match = re.search(r"The command exited with code\s+(-?\d+)", content)
                        if code_match:
                            if int(code_match.group(1)) != 0:
                                is_error = True
                        elif "HTTP 403: 403 Forbidden" in content or "403 Forbidden" in content:
                            is_error = True

                if is_error:
                    last_call.status = "ERROR"
                    last_call.error = content
                    status = "ERROR"

            norm_step = NormalizedStep(
                step_index=step_idx,
                source=source,
                step_type=step_type,
                created_at=created_at,
                content=content,
                thinking=thinking,
                tool_calls=step_tool_calls,
                status=status,
                truncated_fields=truncated,
                tokens=tokens,
                raw=record,
            )
            normalized_steps.append(norm_step)

        # Ordenar pasos por step_index y calcular latencias relativas
        normalized_steps.sort(key=lambda s: s.step_index)
        for i in range(len(normalized_steps) - 1):
            s_curr = normalized_steps[i]
            s_next = normalized_steps[i + 1]
            if s_curr.created_at and s_next.created_at:
                delta = (s_next.created_at - s_curr.created_at).total_seconds()
                s_curr.duration_seconds = max(0.0, delta)

        return normalized_steps

    def extract_metadata(self, path: Path, steps: List[NormalizedStep]) -> ConversationMetadata:
        """Extrae metadatos globales de la sesión Antigravity."""
        resolved = self.resolve_path(path)
        if ".system_generated" in resolved.parts:
            idx = resolved.parts.index(".system_generated")
            session_id = resolved.parts[idx - 1]
        elif resolved.stem in ("transcript", "transcript_full"):
            session_id = resolved.parent.name
        else:
            session_id = resolved.stem
        start_time = steps[0].created_at if steps and steps[0].created_at else None
        end_time = steps[-1].created_at if steps and steps[-1].created_at else None

        title: Optional[str] = None
        for s in steps:
            if s.source in ("USER", "USER_EXPLICIT") or s.step_type == "USER_INPUT":
                if s.content:
                    title = clean_title(s.content)
                    if title:
                        break

        return ConversationMetadata(
            session_id=session_id,
            runtime="antigravity",
            source_path=str(resolved),
            title=title,
            start_time=start_time,
            end_time=end_time,
        )

    def fast_extract_metadata(self, path: Path) -> ConversationMetadata:
        """Extrae metadatos de sesión (ID, título, tiempos) de forma instantánea sin parsear toda la transcripción."""
        resolved = self.resolve_path(path)
        if not resolved.is_file():
            raise FileNotFoundError(f"No se encontró el archivo de transcripción: {path}")

        if ".system_generated" in resolved.parts:
            idx = resolved.parts.index(".system_generated")
            session_id = resolved.parts[idx - 1]
        elif resolved.stem in ("transcript", "transcript_full"):
            session_id = resolved.parent.name
        else:
            session_id = resolved.stem

        title: Optional[str] = None
        start_time: Optional[datetime] = None

        with open(resolved, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    continue

                ts_str = record.get("created_at")
                if ts_str and start_time is None:
                    try:
                        start_time = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    except Exception:
                        pass

                source = str(record.get("source", ""))
                step_type = str(record.get("type", ""))
                if title is None and (source in ("USER", "USER_EXPLICIT") or step_type == "USER_INPUT"):
                    content = record.get("content")
                    if content:
                        title = clean_title(content)

                if title is not None and start_time is not None:
                    break

        return ConversationMetadata(
            session_id=session_id,
            runtime="antigravity",
            source_path=str(resolved),
            title=title,
            start_time=start_time,
            end_time=None,
        )

