#!/usr/bin/env python3
"""
Adaptador de transcripciones para el runtime Claude Code.
Parsea archivos JSON y JSONL de sesiones y logs de Claude Code.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import (
    ConversationMetadata,
    NormalizedStep,
    NormalizedToolCall,
    TranscriptAdapter,
    clean_title,
)


class ClaudeAdapter(TranscriptAdapter):
    """Adaptador para transcripciones generadas por Claude Code."""

    def resolve_path(self, target: Path) -> Path:
        """Resuelve la ruta física del log de Claude Code."""
        p = target.expanduser().resolve()
        if p.is_file():
            return p
        if p.is_dir():
            # Buscar archivos JSON o JSONL en el directorio
            for ext in ("*.jsonl", "*.json"):
                matches = list(p.glob(ext))
                if matches:
                    return sorted(matches)[-1]
        # Búsqueda en directorio ~/.claude
        claude_home = Path.home() / ".claude"
        if claude_home.is_dir():
            cand = claude_home / target.name
            if cand.is_file():
                return cand
        return target

    def detect(self, path: Path) -> bool:
        """Determina si el archivo corresponde a una sesión de Claude Code."""
        resolved = self.resolve_path(path)
        if not resolved.is_file():
            return False

        try:
            with open(resolved, "r", encoding="utf-8") as f:
                first_chunk = f.read(2048)
                if not first_chunk:
                    return False
                # Claude Code suele usar roles "assistant", "user", "tool_use", "tool_result"
                if '"role":' in first_chunk and ('"assistant"' in first_chunk or '"user"' in first_chunk):
                    if '"tool_use"' in first_chunk or '"tool_result"' in first_chunk or 'claude' in str(resolved).lower():
                        return True
        except Exception:
            return False
        return False

    @staticmethod
    def _unwrap_event(event: Dict[str, Any]) -> Dict[str, Any]:
        """Aplana el formato JSONL de Claude Code ({"type", "message": {role, content, usage}, "timestamp"})."""
        msg = event.get("message")
        if isinstance(msg, dict) and "role" in msg:
            flat = {k: v for k, v in event.items() if k != "message"}
            flat.update(msg)
            return flat
        return event

    @staticmethod
    def _merge_message_blocks(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Fusiona registros JSONL consecutivos que comparten `message.id`.

        Claude Code escribe cada bloque (thinking, text, tool_use) de una misma respuesta
        como una línea aparte, repitiendo `usage`. Se conservan los metadatos del primer
        registro, se concatenan los bloques en orden y se toma el `usage` de la última línea
        (una sola vez). Los eventos sin `message.id` se devuelven intactos.
        """
        merged: List[Dict[str, Any]] = []
        last_id: Optional[str] = None
        for ev in events:
            msg = ev.get("message")
            msg_id = msg.get("id") if isinstance(msg, dict) else None
            if msg_id and msg_id == last_id:
                prev_msg = merged[-1]["message"]
                content = msg.get("content")
                if isinstance(content, str):
                    content = [{"type": "text", "text": content}]
                if isinstance(content, list):
                    prev_msg["content"] = prev_msg["content"] + content
                if "usage" in msg:
                    prev_msg["usage"] = msg["usage"]
                continue
            if msg_id:
                first_content = msg.get("content")
                if isinstance(first_content, str):
                    first_content = [{"type": "text", "text": first_content}]
                elif not isinstance(first_content, list):
                    first_content = []
                ev = {**ev, "message": {**msg, "content": list(first_content)}}
            merged.append(ev)
            last_id = msg_id
        return merged

    @staticmethod
    def _is_tool_result_event(event: Dict[str, Any]) -> bool:
        """Determina si un evento corresponde exclusivamente a resultados de herramientas."""
        role = event.get("role")
        if role in ("tool_result", "tool"):
            return True
        if role != "user":
            return False
        raw_content = event.get("content")
        if isinstance(raw_content, list) and raw_content:
            return all(isinstance(b, dict) and b.get("type") == "tool_result" for b in raw_content)
        return False

    @staticmethod
    def _extract_content_text(content: Any) -> str:
        """Extrae el contenido textual limpio de un campo content (str o lista de bloques)."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for sub in content:
                if isinstance(sub, dict) and sub.get("type") == "text":
                    parts.append(sub.get("text", ""))
                elif isinstance(sub, str):
                    parts.append(sub)
            return "\n".join(parts)
        if content is None:
            return ""
        return str(content)

    def parse(self, path: Path) -> List[NormalizedStep]:
        """Parsea logs de Claude Code a NormalizedStep."""
        resolved = self.resolve_path(path)
        if not resolved.is_file():
            raise FileNotFoundError(f"No se encontró el log de Claude: {path}")

        raw_events: List[Dict[str, Any]] = []
        with open(resolved, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return []
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    raw_events = data
                elif isinstance(data, dict):
                    if "messages" in data and isinstance(data["messages"], list):
                        raw_events = data["messages"]
                    else:
                        raw_events = [data]
            except Exception:
                # Tratar como JSONL (un objeto JSON por línea)
                raw_events = []
                for line in content.splitlines():
                    line = line.strip()
                    if line:
                        try:
                            raw_events.append(json.loads(line))
                        except Exception:
                            pass

        # Aplanar eventos anidados y descartar registros sin mensaje (snapshots, summaries, metadatos)
        raw_events = [e for e in raw_events if isinstance(e, dict)]
        raw_events = self._merge_message_blocks(raw_events)
        raw_events = [self._unwrap_event(e) for e in raw_events]
        raw_events = [e for e in raw_events if "role" in e]

        normalized_steps: List[NormalizedStep] = []
        tool_results_by_id: Dict[str, Dict[str, Any]] = {}

        # Primera pasada: indexar tool_results si están desacoplados
        for event in raw_events:
            blocks = event.get("content", [])
            if isinstance(blocks, list):
                for b in blocks:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        t_id = b.get("tool_use_id", "")
                        if t_id:
                            tool_results_by_id[t_id] = b

        step_idx = 0
        for event in raw_events:
            role = event.get("role", "unknown")
            raw_content = event.get("content", "")

            is_tool_result = self._is_tool_result_event(event)
            if is_tool_result:
                source = "SYSTEM"
                step_type = "TOOL_OUTPUT"
            elif role == "user":
                source = "USER"
                step_type = "USER_INPUT"
            elif role == "assistant":
                source = "MODEL"
                step_type = "PLANNER_RESPONSE"
            else:
                source = "SYSTEM"
                step_type = "SYSTEM"

            ts_raw = event.get("timestamp") or event.get("created_at") or event.get("ts")
            created_at: Optional[datetime] = None
            if ts_raw:
                try:
                    created_at = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                except Exception:
                    pass

            text_content: List[str] = []
            thinking_parts: List[str] = []
            tool_calls: List[NormalizedToolCall] = []

            if isinstance(raw_content, str):
                text_content.append(raw_content)
            elif isinstance(raw_content, list):
                for block in raw_content:
                    if not isinstance(block, dict):
                        continue
                    b_type = block.get("type")
                    if b_type == "text":
                        text_content.append(block.get("text", ""))
                    elif b_type == "thinking":
                        thinking_parts.append(block.get("thinking", ""))
                    elif b_type == "tool_use":
                        t_id = block.get("id", "")
                        t_name = block.get("name", "tool")
                        t_input = block.get("input", {})
                        res = tool_results_by_id.get(t_id, {})
                        is_error = res.get("is_error", False)
                        res_content = self._extract_content_text(res.get("content", ""))

                        norm_tc = NormalizedToolCall(
                            name=t_name,
                            args=t_input if isinstance(t_input, dict) else {"raw": t_input},
                            call_id=t_id,
                            status="ERROR" if is_error else "DONE",
                            error=res_content if is_error else None,
                            raw_output=res_content if not is_error else None,
                        )
                        tool_calls.append(norm_tc)
                    elif b_type == "tool_result":
                        extracted = self._extract_content_text(block.get("content", ""))
                        if extracted:
                            text_content.append(extracted)

            usage = event.get("usage", {})
            tokens = {
                "input": usage.get("input_tokens", 0),
                "output": usage.get("output_tokens", 0),
                "cache_read": usage.get("cache_read_input_tokens", 0),
            }

            status = "DONE"
            if is_tool_result and isinstance(raw_content, list):
                if any(isinstance(b, dict) and b.get("is_error") for b in raw_content):
                    status = "ERROR"

            norm_step = NormalizedStep(
                step_index=step_idx,
                source=source,
                step_type=step_type,
                created_at=created_at,
                content="\n".join(text_content) if text_content else None,
                thinking="\n".join(thinking_parts) if thinking_parts else None,
                tool_calls=tool_calls,
                status=status,
                tokens=tokens,
                raw=event,
            )
            normalized_steps.append(norm_step)
            step_idx += 1

        # Calcular duraciones relativas
        for i in range(len(normalized_steps) - 1):
            s_curr = normalized_steps[i]
            s_next = normalized_steps[i + 1]
            if s_curr.created_at and s_next.created_at:
                delta = (s_next.created_at - s_curr.created_at).total_seconds()
                s_curr.duration_seconds = max(0.0, delta)

        return normalized_steps

    def extract_metadata(self, path: Path, steps: List[NormalizedStep]) -> ConversationMetadata:
        """Extrae metadatos globales de la sesión Claude."""
        resolved = self.resolve_path(path)
        session_id = resolved.stem
        start_time = steps[0].created_at if steps and steps[0].created_at else None
        end_time = steps[-1].created_at if steps and steps[-1].created_at else None

        title: Optional[str] = None
        for s in steps:
            if s.source == "USER" or s.step_type == "USER_INPUT":
                if s.content:
                    title = clean_title(s.content)
                    if title:
                        break

        return ConversationMetadata(
            session_id=session_id,
            runtime="claude",
            source_path=str(resolved),
            title=title,
            start_time=start_time,
            end_time=end_time,
        )

    def fast_extract_metadata(self, path: Path) -> ConversationMetadata:
        """Extrae metadatos globales de forma rápida sin parsear todos los eventos."""
        resolved = self.resolve_path(path)
        if not resolved.is_file():
            raise FileNotFoundError(f"No se encontró el log de Claude: {path}")

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

                if isinstance(record, dict):
                    record = self._unwrap_event(record)
                    ts_raw = record.get("timestamp") or record.get("created_at") or record.get("ts")
                    if ts_raw and start_time is None:
                        try:
                            start_time = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                        except Exception:
                            pass

                    role = record.get("role")
                    if title is None and role == "user":
                        raw_c = record.get("content", "")
                        if isinstance(raw_c, str):
                            title = clean_title(raw_c)
                        elif isinstance(raw_c, list):
                            for b in raw_c:
                                if isinstance(b, dict) and b.get("type") == "text":
                                    title = clean_title(b.get("text", ""))
                                    if title:
                                        break

                if title is not None and start_time is not None:
                    break

        if title is None and start_time is None:
            steps = self.parse(path)
            return self.extract_metadata(path, steps)

        return ConversationMetadata(
            session_id=session_id,
            runtime="claude",
            source_path=str(resolved),
            title=title,
            start_time=start_time,
            end_time=None,
        )

