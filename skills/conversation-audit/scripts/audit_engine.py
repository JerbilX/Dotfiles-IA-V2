#!/usr/bin/env python3
"""
Motor de cálculo, agregación de métricas y detección de antipatrones para conversation-audit.
"""

import json
import re
import shlex
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from adapters.base import ConversationMetadata, NormalizedStep, NormalizedToolCall


ANTIPATTERN_RULE_MAP: Dict[str, str] = {
    "UNPAGINATED_FILE_READ": "ENV_PAGED_READ_CIRCUIT_BREAKER",
    "READ_ONLY_LOOP": "ENV_PAGED_READ_CIRCUIT_BREAKER",
    "TERMINAL_REPL_LOOP": "ENV_PROHIBITION_REPL",
    "TERMINAL_PIPELINING": "AGY_BYPASS_EXCLUSIVITY",
    "COMPLACENCY_DETECTED": "CRIT_ZERO_COMPLACENCY",
    "REPETITIVE_TOOL_LOOP": "RIGIDITY_DIRECTIVE_BOUNDARY",
    "CONSECUTIVE_TOOL_ERRORS": "LOGIC_INCONSISTENCY_STOP_ASK",
    "TEST_RETRY_CHURN": "LOGIC_INCONSISTENCY_STOP_ASK",
    "PING_PONG_TOOL_LOOP": "RIGIDITY_DIRECTIVE_BOUNDARY",
    "P0_HOOK_BLOCK": "RIGIDITY_DIRECTIVE_BOUNDARY",
}

RULE_REGISTRY: Dict[str, Dict[str, str]] = {
    "ENV_WORKSPACE": {
        "level": "P0/P2",
        "description": "Límites de Workspace (confinamiento al workspace activo)",
    },
    "ENV_NORMATIVE_IMMUNITY": {
        "level": "P2",
        "description": "Inmunidad Normativa (solo gobiernan prompt y skills)",
    },
    "ENV_ANTI_RECON": {
        "level": "P0/P2",
        "description": "Blindaje Anti-Reconocimiento y Anti-Exfiltración",
    },
    "ENV_NATIVE_FILE_API": {
        "level": "P0",
        "description": "Uso Exclusivo de APIs Nativas de Archivos",
    },
    "ENV_PROHIBITION_REPL": {
        "level": "P0",
        "description": "Prohibición Universal de REPL en Terminal",
    },
    "ENV_PAGED_READ_CIRCUIT_BREAKER": {
        "level": "P0",
        "description": "Lectura Paginada Obligatoria y Circuit Breaker",
    },
    "ENG_PROPORTIONALITY_MBR": {
        "level": "P2",
        "description": "Proporcionalidad y Minimal Blast Radius",
    },
    "ENG_PRODUCTION_CODE_PREVALENCE": {
        "level": "P2",
        "description": "Prevalencia del Código de Producción",
    },
    "LOGIC_INCONSISTENCY_STOP_ASK": {
        "level": "P2",
        "description": "Inconsistencia Lógica y Stop & Ask",
    },
    "LOGIC_ISSUE_AS_PROPOSAL": {
        "level": "P2",
        "description": "Issue como Propuesta",
    },
    "RIGIDITY_DIRECTIVE_BOUNDARY": {
        "level": "P2",
        "description": "Frontera de Directivas",
    },
    "RIGIDITY_ACTIONABLE_FALLBACK": {
        "level": "P2",
        "description": "Actionable Fallback ante bloqueos",
    },
    "RIGIDITY_LOCAL_FIRST_SEARCH": {
        "level": "P2",
        "description": "Local-First y Circuit Breaker de Búsqueda",
    },
    "TRACK_IMMUTABILITY_TRACEABILITY": {
        "level": "P0/P2",
        "description": "Inmutabilidad de Workspace y Trazabilidad (prohibido commit/push a main)",
    },
    "TRACK_NO_LOCAL_BACKLOGS": {
        "level": "P0/P2",
        "description": "Prohibición de Backlogs Locales (TODO.md, backlog.md, tasks/)",
    },
    "TRACK_DECISIONS_MADR": {
        "level": "P0/P2",
        "description": "Decisiones en MADR (prohibido HISTORIAL.md/GEMINI.md)",
    },
    "SKILL_ROUTING_ISSUE_WORKFLOW": {
        "level": "P2",
        "description": "Activación obligatoria de issue-driven-workflow",
    },
    "SKILL_ROUTING_ADR_MANAGER": {
        "level": "P2",
        "description": "Activación obligatoria de adr-manager",
    },
    "SKILL_ROUTING_PROJECT_DOCS": {
        "level": "P2",
        "description": "Activación obligatoria de project-documentation",
    },
    "SKILL_ROUTING_CONVERSATION_AUDIT": {
        "level": "P2",
        "description": "Activación obligatoria de conversation-audit",
    },
    "SKILL_ROUTING_AUTONOMOUS_LEARNING": {
        "level": "P2",
        "description": "Activación obligatoria de autonomous-learning",
    },
    "CRIT_ZERO_COMPLACENCY": {
        "level": "P2",
        "description": "Cero complacencia y validación vacía",
    },
    "CRIT_CHALLENGE_PROPOSE": {
        "level": "P2",
        "description": "Cuestionar y proponer ante fallas técnicas",
    },
    "CRIT_ZERO_FLATTERY_APOLOGIES": {
        "level": "P2",
        "description": "Cero adulación y disculpas innecesarias",
    },
    "AGY_GIT_SANDBOX_BYPASS": {
        "level": "P0/P2",
        "description": "Ejecución de Git y Bypass de Sandbox",
    },
    "AGY_DOTFILES_PROVISIONING": {
        "level": "P2",
        "description": "Aprovisionamiento Hermético de Dotfiles",
    },
    "AGY_BYPASS_EXCLUSIVITY": {
        "level": "P0/P2",
        "description": "Exclusividad de Bypass y comandos atómicos sin && ni |",
    },
    "AGY_ATTRIBUTION": {
        "level": "P2",
        "description": "Atribución en commits y PRs (Antigravity)",
    },
    "CLAUDE_SKILLS_CIRCUIT_BREAKER": {
        "level": "P0/P2",
        "description": "Circuit Breaker en Claude Code",
    },
    "CLAUDE_SUBAGENTS": {
        "level": "P2",
        "description": "Criterio de despacho de subagentes en Claude Code",
    },
    "CLAUDE_RUNTIME_CONTINUITY": {
        "level": "P2",
        "description": "Continuidad entre Runtimes",
    },
    "CLAUDE_ATTRIBUTION": {
        "level": "P2",
        "description": "Atribución en commits y PRs (Claude Code)",
    },
}


@dataclass
class DetectedAntipattern:
    """Representa un antipatrón o vicio de comportamiento detectado."""
    severity: str  # CRÍTICA, ALTA, MEDIA, BAJA
    code: str
    title: str
    step_index: int
    description: str
    recommendation: str
    rule_id: Optional[str] = None

    def __post_init__(self):
        if self.rule_id is None and self.code in ANTIPATTERN_RULE_MAP:
            self.rule_id = ANTIPATTERN_RULE_MAP[self.code]


@dataclass
class RuleViolationSummary:
    """Resumen consolidado de violaciones para un ID de regla específico."""
    rule_id: str
    level: str
    description: str
    total_violations: int
    sessions_count: int
    sessions: List[str]
    antipattern_count: int
    p0_block_count: int
    action_suggestion: str


@dataclass
class RulesViolationReport:
    """Reporte consolidado de métricas de violación por ID de regla."""
    total_sessions: int
    total_violations: int
    rule_summaries: List[RuleViolationSummary]
    unmapped_antipatterns: int = 0


@dataclass
class ToolMetrics:
    """Métricas asociadas a una herramienta específica."""
    name: str
    invocations: int = 0
    errors: int = 0

    @property
    def error_rate(self) -> float:
        return (self.errors / self.invocations * 100.0) if self.invocations > 0 else 0.0


@dataclass
class AuditReport:
    """Reporte cuantitativo y cualitativo consolidado de una sesión."""
    metadata: ConversationMetadata
    total_steps: int = 0
    user_turns: int = 0
    model_turns: int = 0
    system_steps: int = 0
    wall_clock_seconds: float = 0.0
    avg_step_latency_seconds: float = 0.0
    max_step_latency_seconds: float = 0.0
    slowest_steps: List[Dict[str, Any]] = field(default_factory=list)
    total_tool_calls: int = 0
    total_tool_errors: int = 0
    tool_metrics: Dict[str, ToolMetrics] = field(default_factory=dict)
    thinking_steps_count: int = 0
    total_thinking_chars: int = 0
    avg_thinking_chars: float = 0.0
    antipatterns: List[DetectedAntipattern] = field(default_factory=list)
    steps_timeline: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def overall_tool_error_rate(self) -> float:
        return (self.total_tool_errors / self.total_tool_calls * 100.0) if self.total_tool_calls > 0 else 0.0


class AuditEngine:
    """Motor de análisis de sesiones de agentes."""

    COMPLACENCY_PATTERNS = [
        "gran idea",
        "tienes toda la razón",
        "tienes razón",
        "disculpa las molestias",
        "mil disculpas",
        "pido disculpas",
        "análisis impecable",
        "excelente observación",
    ]

    TERMINAL_TOOL_NAMES = {
        "run_command",
        "bash",
        "execute_command",
        "terminal",
        "sh",
        "run_shell_command",
    }

    FILE_READ_TOOL_NAMES = {
        "view_file",
        "view",
        "read_file",
        "readfile",
        "read_local_file",
    }

    EDIT_TOOL_NAMES = {
        "replace_file_content",
        "write_to_file",
        "write_file",
        "write",
        "edit_file",
        "edit",
    }

    TEST_COMMAND_REGEX = re.compile(
        r"\b(pytest|unittest|busted|jest|mocha|vitest|ctest)\b|"
        r"(?:cargo|npm|yarn|pnpm|go|make|rake|mix)\s+(?:test|check)|"
        r"(?:build\.sh|\./build\.sh)\s+check|"
        r"\b(?:test|tests)\b|"
        r"(?:\b|_)(?:test|tests)_[a-zA-Z0-9_-]+|"
        r"[a-zA-Z0-9_-]+_(?:test|tests)(?:\.[a-zA-Z0-9]+)?\b",
        re.IGNORECASE,
    )

    TEST_FAILURE_REGEX = re.compile(
        r"(?:FAIL|FAILED|AssertionError|failures=|test\s+failed|tests\s+failed|assertion\s+failed|exited with code [1-9])",
        re.IGNORECASE,
    )

    PASSIVE_INSPECTION_TOOLS = {
        "view_file",
        "view",
        "read_file",
        "readfile",
        "read_local_file",
        "read",
        "grep_search",
        "grep",
        "search",
        "find_by_name",
        "find",
        "glob",
        "list_dir",
        "list_directory",
        "read_url_content",
        "read_browser_page",
    }

    ACTIVE_MUTATION_TOOLS = {
        "replace_file_content",
        "write_to_file",
        "write_file",
        "write",
        "edit_file",
        "edit",
        "run_command",
        "bash",
        "execute_command",
        "terminal",
        "sh",
        "run_shell_command",
        "generate_image",
        "ask_question",
    }

    BINARY_EXTENSIONS = {
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tiff",
        ".mp3", ".wav", ".ogg", ".mp4", ".mkv", ".webm", ".avi",
        ".pdf", ".bin", ".exe", ".zip", ".tar", ".gz", ".tgz", ".bz2", ".7z",
        ".woff", ".woff2", ".ttf", ".eot",
    }

    INTERPRETER_REGEX = re.compile(
        r"^(python(?:\d+(?:\.\d+)?)?|node|nodejs|ruby|perl)(\.exe)?$",
        re.IGNORECASE,
    )

    WRAPPERS = {"sudo", "env", "nohup", "time", "winpty"}

    EVAL_FLAGS_BY_RUNTIME = {
        "python": {"-c"},
        "node": {"-e", "--eval"},
        "nodejs": {"-e", "--eval"},
        "ruby": {"-e"},
        "perl": {"-e"},
    }

    NON_EVAL_COMMANDS = {
        "echo", "cat", "grep", "git", "which", "curl", "wget", "sed", "awk",
        "find", "rg", "head", "tail", "less", "more", "touch", "rm", "cp", "mv",
        "ls", "pytest", "cargo", "npm", "yarn", "pnpm", "pip", "pip3", "docker",
    }

    FALLBACK_INLINE_EVAL_REGEX = re.compile(
        r"""
        (?:^|[\s;&|`$()])
        (?:(?:/[^\s/]+/)*(?:sudo\s+|env\s+(?:\w+=\S+\s+)*)*)?
        (?P<runtime>python(?:\d+(?:\.\d+)?)?|node|nodejs|ruby|perl)
        (?:\.exe)?
        \s+
        (?:-[a-zA-Z0-9_\-]+\s+)*
        (?P<flag>-c|-e|--eval)\b
        """,
        re.VERBOSE | re.IGNORECASE,
    )

    @classmethod
    def check_inline_eval(cls, cmd: str) -> Tuple[bool, str]:
        """Detecta si un comando invoca una evaluación en línea (REPL) en un intérprete soportado."""
        cmd_str = cmd.strip()
        if not cmd_str:
            return False, ""

        # Descarte rápido de comandos CLI no evaluadores
        first_word = cmd_str.split()[0].lower()
        first_word_clean = Path(first_word).name
        if first_word_clean in cls.NON_EVAL_COMMANDS:
            return False, ""

        # 1. Análisis estructurado de tokens vía shlex
        try:
            tokens = shlex.split(cmd_str)
        except Exception:
            tokens = None

        if tokens:
            idx = 0
            while idx < len(tokens):
                tok = tokens[idx]
                # Saltar asignaciones de variables de entorno (VAR=val)
                if "=" in tok and not tok.startswith("-"):
                    idx += 1
                    continue
                # Saltar ejecutables envoltorios comunes
                if tok.lower() in cls.WRAPPERS:
                    idx += 1
                    continue
                break

            if idx < len(tokens):
                candidate = Path(tokens[idx]).name.lower()
                if candidate.endswith(".exe"):
                    candidate = candidate[:-4]

                m = cls.INTERPRETER_REGEX.match(candidate)
                if m:
                    runtime_family = "python" if candidate.startswith("python") else candidate
                    valid_flags = cls.EVAL_FLAGS_BY_RUNTIME.get(runtime_family, {"-c", "-e", "--eval"})

                    # Verificar tokens subsiguientes
                    for arg in tokens[idx + 1:]:
                        if arg in valid_flags:
                            return True, candidate
                        if not arg.startswith("-"):
                            # Token no es flag: es el nombre de un archivo script (ej. python script.py -c ...)
                            return False, ""
                    return False, ""
            return False, ""

        # 2. Heurística fallback mediante regex
        m = cls.FALLBACK_INLINE_EVAL_REGEX.search(cmd_str)
        if m:
            rt = m.group("runtime").lower()
            flag = m.group("flag").lower()
            rt_family = "python" if rt.startswith("python") else rt
            valid_flags = cls.EVAL_FLAGS_BY_RUNTIME.get(rt_family, {"-c", "-e", "--eval"})
            if flag in valid_flags:
                return True, rt

        return False, ""

    @classmethod
    def is_file_read_tool(cls, tool_name: str) -> bool:
        """Determina si una herramienta corresponde a operaciones de lectura de archivos."""
        candidate = tool_name.split(":")[-1].lower()
        return candidate in cls.FILE_READ_TOOL_NAMES

    @classmethod
    def extract_file_target(cls, args: Dict[str, Any]) -> str:
        """Extrae la ruta del archivo objetivo desde los argumentos si está disponible."""
        if not isinstance(args, dict):
            return ""
        for k in ("AbsolutePath", "TargetFile", "file_path", "filePath", "path", "filename", "file"):
            if k in args and args[k]:
                return str(args[k]).strip('\'"')
        for k, v in args.items():
            if k.lower().replace("_", "") in ("absolutepath", "targetfile", "filepath", "path", "file"):
                if v:
                    return str(v).strip('\'"')
        return ""

    @classmethod
    def extract_file_read_bounds(cls, args: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
        """Extrae límites numéricos (StartLine, EndLine o view_range) de una llamada a lectura."""
        if not isinstance(args, dict):
            return None, None

        # Formato de Claude Code: view_range: [start, end]
        vr = args.get("view_range")
        if isinstance(vr, (list, tuple)) and len(vr) >= 2:
            try:
                return int(vr[0]), int(vr[1])
            except (ValueError, TypeError):
                pass

        start_line: Optional[int] = None
        end_line: Optional[int] = None

        for k, v in args.items():
            k_clean = k.lower().replace("_", "")
            if k_clean in ("startline", "start"):
                try:
                    start_line = int(v)
                except (ValueError, TypeError):
                    pass
            elif k_clean in ("endline", "end"):
                try:
                    end_line = int(v)
                except (ValueError, TypeError):
                    pass

        return start_line, end_line

    def __init__(self, latency_threshold_seconds: float = 60.0, file_lines_threshold: int = 200):
        self.latency_threshold = latency_threshold_seconds
        self.file_lines_threshold = int(file_lines_threshold) if file_lines_threshold is not None else 200

    def analyze(self, metadata: ConversationMetadata, steps: List[NormalizedStep]) -> AuditReport:
        """Calcula todas las métricas y detecta antipatrones a partir de los pasos."""
        report = AuditReport(metadata=metadata)
        report.total_steps = len(steps)

        if not steps:
            return report

        # 1. Contabilización de turnos
        for s in steps:
            if s.source == "USER" or s.step_type == "USER_INPUT":
                report.user_turns += 1
            elif s.source == "MODEL" or s.step_type == "PLANNER_RESPONSE":
                report.model_turns += 1
            else:
                report.system_steps += 1

        # 2. Métricas temporales (Wall-Clock y Latencias)
        valid_ts = [s.created_at for s in steps if s.created_at is not None]
        if valid_ts:
            valid_ts.sort()
            report.wall_clock_seconds = max(0.0, (valid_ts[-1] - valid_ts[0]).total_seconds())

        durations = [s.duration_seconds for s in steps if s.duration_seconds is not None]
        if durations:
            report.avg_step_latency_seconds = sum(durations) / len(durations)
            report.max_step_latency_seconds = max(durations)

        # Pasos más lentos (Top 5)
        steps_with_dur = [s for s in steps if s.duration_seconds is not None]
        steps_with_dur.sort(key=lambda s: s.duration_seconds or 0.0, reverse=True)
        report.slowest_steps = []
        for s in steps_with_dur[:5]:
            item = {
                "step_index": s.step_index,
                "duration_seconds": round(s.duration_seconds or 0.0, 2),
                "type": s.step_type,
                "source": s.source,
                "tools": [tc.name for tc in s.tool_calls],
            }
            if s.tool_calls:
                actions = [tc.tool_action or tc.args.get("CommandLine", "")[:60] for tc in s.tool_calls if tc.tool_action or tc.args.get("CommandLine")]
                if actions:
                    item["detail"] = " | ".join(actions)
            elif s.content:
                clean_c = s.content.strip().replace("\n", " ")
                item["detail"] = clean_c[:80] + "..." if len(clean_c) > 80 else clean_c
            report.slowest_steps.append(item)

        # Cronología de pasos
        for s in steps:
            tools_summary = []
            for tc in s.tool_calls:
                cmd = tc.args.get("CommandLine") or tc.args.get("command") or ""
                act = tc.tool_action or tc.tool_summary or ""
                target = tc.args.get("TargetFile") or tc.args.get("AbsolutePath") or ""
                tools_summary.append({
                    "name": tc.name,
                    "action": act,
                    "command": cmd,
                    "target": target,
                })

            report.steps_timeline.append({
                "step_index": s.step_index,
                "source": s.source,
                "type": s.step_type,
                "duration_seconds": round(s.duration_seconds or 0.0, 2),
                "tools": tools_summary,
                "content_snippet": (s.content[:100].replace("\n", " ") + "...") if s.content else "",
                "truncated": s.truncated_fields,
            })

        # 3. Métricas de Herramientas
        tool_counts: Dict[str, int] = defaultdict(int)
        tool_errors: Dict[str, int] = defaultdict(int)

        for s in steps:
            for tc in s.tool_calls:
                report.total_tool_calls += 1
                tool_counts[tc.name] += 1
                if tc.status == "ERROR":
                    report.total_tool_errors += 1
                    tool_errors[tc.name] += 1

        for name, count in tool_counts.items():
            report.tool_metrics[name] = ToolMetrics(
                name=name,
                invocations=count,
                errors=tool_errors[name],
            )

        # 4. Métricas de Thinking / Razonamiento
        for s in steps:
            if s.thinking:
                report.thinking_steps_count += 1
                report.total_thinking_chars += len(s.thinking)

        if report.thinking_steps_count > 0:
            report.avg_thinking_chars = report.total_thinking_chars / report.thinking_steps_count

        # 5. Detección de Antipatrones
        report.antipatterns = self._detect_antipatterns(steps)

        return report

    def _detect_antipatterns(self, steps: List[NormalizedStep]) -> List[DetectedAntipattern]:
        """Ejecuta heurísticas para identificar comportamientos defectuosos o ineficientes."""
        antipatterns: List[DetectedAntipattern] = []

        # A. Latencias anómalas
        for s in steps:
            if s.duration_seconds and s.duration_seconds > self.latency_threshold:
                antipatterns.append(
                    DetectedAntipattern(
                        severity="MEDIA",
                        code="HIGH_LATENCY_STEP",
                        title="Paso de Alta Latencia",
                        step_index=s.step_index,
                        description=f"El paso {s.step_index} tardó {s.duration_seconds:.1f}s (umbral: {self.latency_threshold}s). Herramientas invocadas: {[tc.name for tc in s.tool_calls]}.",
                        recommendation="Verificar si hubo descargas pesadas de red, subprocesos bloqueantes o si conviene acotar el alcance de la herramienta.",
                    )
                )

        # B. Truncamiento en el registro del transcript (#237): `truncated_fields` indica que el
        # runtime recortó el campo al persistir el transcript, no que el modelo perdiera contexto.
        # Se reporta como señal de volumen (BAJA), sin inferir pérdida de información.
        for s in steps:
            if s.truncated_fields:
                antipatterns.append(
                    DetectedAntipattern(
                        severity="BAJA",
                        code="CONTEXT_TRUNCATION",
                        title="Campo Truncado en el Registro del Transcript",
                        step_index=s.step_index,
                        description=f"El transcript guardó recortados los campos {', '.join(s.truncated_fields)} del paso {s.step_index}. Es un recorte del registro persistido; por sí solo no evidencia pérdida de contexto del modelo.",
                        recommendation="Si el contenido es relevante, verificar en pasos posteriores si el modelo lo usó correctamente. Si hay recortes recurrentes, acotar las lecturas o salidas voluminosas que los originan.",
                    )
                )

        # C. Bucles de reintento / Herramientas repetitivas
        for i in range(len(steps) - 1):
            curr_s = steps[i]
            next_s = steps[i + 1]
            if curr_s.tool_calls and next_s.tool_calls:
                curr_names = [tc.name for tc in curr_s.tool_calls]
                next_names = [tc.name for tc in next_s.tool_calls]
                if curr_names == next_names and len(curr_names) == 1:
                    # Comparar argumentos
                    tc1 = curr_s.tool_calls[0]
                    tc2 = next_s.tool_calls[0]
                    if tc1.args == tc2.args:
                        antipatterns.append(
                            DetectedAntipattern(
                                severity="ALTA",
                                code="REPETITIVE_TOOL_LOOP",
                                title="Bucle Repetitivo de Herramienta",
                                step_index=next_s.step_index,
                                description=f"Invocación consecutiva e idéntica de '{tc1.name}' entre los pasos {curr_s.step_index} y {next_s.step_index} con argumentos idénticos.",
                                recommendation="Verificar si el agente cayó en un bucle ciego sin procesar adecuadamente la respuesta anterior.",
                            )
                        )

        # D. Errores consecutivos de herramientas
        consecutive_errors = 0
        last_error_step = -1
        for s in steps:
            has_error = False
            for tc in s.tool_calls:
                if tc.status == "ERROR":
                    has_error = True
                    break
            if has_error:
                consecutive_errors += 1
                last_error_step = s.step_index
            else:
                if consecutive_errors >= 2:
                    antipatterns.append(
                        DetectedAntipattern(
                            severity="CRÍTICA",
                            code="CONSECUTIVE_TOOL_ERRORS",
                            title="Errores Consecutivos de Herramientas",
                            step_index=last_error_step,
                            description=f"Se registraron {consecutive_errors} pasos consecutivos con errores en ejecución de herramientas finalizando en el paso {last_error_step}.",
                            recommendation="Aplicar Stop & Ask tras 2-3 fallos consecutivos en lugar de iterar a ciegas.",
                        )
                    )
                consecutive_errors = 0

        if consecutive_errors >= 2:
            antipatterns.append(
                DetectedAntipattern(
                    severity="CRÍTICA",
                    code="CONSECUTIVE_TOOL_ERRORS",
                    title="Errores Consecutivos de Herramientas",
                    step_index=last_error_step,
                    description=f"Se registraron {consecutive_errors} pasos consecutivos con errores en ejecución de herramientas finalizando en el paso {last_error_step}.",
                    recommendation="Aplicar Stop & Ask tras 2-3 fallos consecutivos en lugar de iterar a ciegas.",
                )
            )

        # E. Pipelining / Encadenamiento en Terminal
        for s in steps:
            for tc in s.tool_calls:
                if tc.name in ("run_command", "bash", "execute_command"):
                    cmd = str(tc.args.get("CommandLine", tc.args.get("command", "")))
                    if any(pipe in cmd for pipe in (" | ", " && ", " || ", ";")):
                        antipatterns.append(
                            DetectedAntipattern(
                                severity="MEDIA",
                                code="TERMINAL_PIPELINING",
                                title="Encadenamiento de Comandos en Terminal",
                                step_index=s.step_index,
                                description=f"El paso {s.step_index} invocó comando con pipes o conectores ('{cmd[:60]}...'). Rompe el prefix matching de sandbox.",
                                recommendation="Dividir en llamadas atómicas independientes o utilizar herramientas nativas de archivos.",
                            )
                        )

        # F. Complacencia o adulación vacía
        for s in steps:
            if s.source == "MODEL" and s.content:
                low_c = s.content.lower()
                for pat in self.COMPLACENCY_PATTERNS:
                    if pat in low_c:
                        antipatterns.append(
                            DetectedAntipattern(
                                severity="BAJA",
                                code="COMPLACENCY_DETECTED",
                                title="Complacencia o Disculpa Innecesaria",
                                step_index=s.step_index,
                                description=f"El paso {s.step_index} contiene frase de complacencia ('{pat}'), contraria a core/01-critical-feedback.md.",
                                recommendation="Mantener tono neutro, técnico y asertivo; evitar disculpas o validaciones complacientes vacías.",
                            )
                        )
                        break

        # G. Bucle REPL Iterativo en Terminal (TERMINAL_REPL_LOOP)
        tool_events: List[Dict[str, Any]] = []
        for s in steps:
            for tc in s.tool_calls:
                is_terminal = tc.name.lower() in self.TERMINAL_TOOL_NAMES
                cmd = str(
                    tc.args.get("CommandLine")
                    or tc.args.get("command")
                    or tc.args.get("cmd")
                    or ""
                ) if isinstance(tc.args, dict) else ""

                is_eval = False
                rt = ""
                if is_terminal and cmd:
                    is_eval, rt = self.check_inline_eval(cmd)

                tool_events.append({
                    "step_index": s.step_index,
                    "tool_name": tc.name,
                    "command": cmd,
                    "is_eval": is_eval,
                    "runtime": rt,
                })

        window_size = 5
        min_density = 3
        flagged_indices = set()
        n_events = len(tool_events)

        for i in range(n_events):
            window = tool_events[i : i + window_size]
            eval_indices = [i + offset for offset, ev in enumerate(window) if ev["is_eval"]]
            if len(eval_indices) >= min_density:
                flagged_indices.update(eval_indices)

        if flagged_indices:
            sorted_flagged = sorted(flagged_indices)
            clusters: List[List[int]] = []
            curr_cluster: List[int] = []

            for idx in sorted_flagged:
                if not curr_cluster:
                    curr_cluster.append(idx)
                else:
                    if idx - curr_cluster[-1] <= window_size:
                        curr_cluster.append(idx)
                    else:
                        clusters.append(curr_cluster)
                        curr_cluster = [idx]
            if curr_cluster:
                clusters.append(curr_cluster)

            for cluster in clusters:
                cluster_events = [tool_events[idx] for idx in cluster]
                count = len(cluster_events)
                start_step = cluster_events[0]["step_index"]
                end_step = cluster_events[-1]["step_index"]
                runtimes = ", ".join(sorted(set(ev["runtime"] for ev in cluster_events if ev["runtime"]))) or "código en línea"

                if start_step == end_step:
                    step_desc = f"en el paso {start_step}"
                else:
                    step_desc = f"entre los pasos {start_step} y {end_step}"

                antipatterns.append(
                    DetectedAntipattern(
                        severity="ALTA",
                        code="TERMINAL_REPL_LOOP",
                        title="Bucle REPL Iterativo en Terminal",
                        step_index=end_step,
                        description=(
                            f"Se detectaron {count} ejecuciones de evaluación de código en línea ({runtimes}) "
                            f"en terminal {step_desc}. Indican un patrón de micro-evaluación iterativa / REPL "
                            f"costoso e ineficiente."
                        ),
                        recommendation=(
                            "Desalentar el uso de terminal como REPL e indicar la refactorización hacia un script "
                            "de prueba dedicado en scratch (<appDataDir>/brain/<conversation-id>/scratch/) "
                            "o tests unitarios locales."
                        ),
                    )
                )

        # H. Lectura No Paginada de Archivos (UNPAGINATED_FILE_READ)
        for s in steps:
            for tc in s.tool_calls:
                if not self.is_file_read_tool(tc.name):
                    continue

                args = tc.args if isinstance(tc.args, dict) else {}
                target_path = self.extract_file_target(args)
                if target_path:
                    ext = Path(target_path).suffix.lower()
                    if ext in self.BINARY_EXTENSIONS:
                        continue

                start_line, end_line = self.extract_file_read_bounds(args)
                target_info = f" en '{Path(target_path).name}'" if target_path else ""

                if start_line is None or end_line is None:
                    if start_line is None and end_line is None:
                        bound_detail = "sin especificar delimitadores de paginación (StartLine / EndLine)"
                    elif start_line is None:
                        bound_detail = f"sin especificar StartLine (únicamente EndLine={end_line})"
                    else:
                        bound_detail = f"sin especificar EndLine (únicamente StartLine={start_line})"

                    antipatterns.append(
                        DetectedAntipattern(
                            severity="ALTA",
                            code="UNPAGINATED_FILE_READ",
                            title="Lectura No Paginada de Archivo",
                            step_index=s.step_index,
                            description=(
                                f"El paso {s.step_index} ejecutó lectura de archivo mediante '{tc.name}'{target_info} "
                                f"{bound_detail} (lectura masiva no acotada)."
                            ),
                            recommendation=(
                                f"Utilizar grep_search para localización previa y acotamiento de ventana mediante "
                                f"StartLine y EndLine (máximo {self.file_lines_threshold} líneas)."
                            ),
                        )
                    )
                else:
                    lines_diff = abs(end_line - start_line)
                    if lines_diff > self.file_lines_threshold:
                        antipatterns.append(
                            DetectedAntipattern(
                                severity="ALTA",
                                code="UNPAGINATED_FILE_READ",
                                title="Lectura No Paginada de Archivo",
                                step_index=s.step_index,
                                description=(
                                    f"El paso {s.step_index} ejecutó lectura de archivo mediante '{tc.name}'{target_info} "
                                    f"con un rango de {lines_diff} líneas (líneas {start_line} a {end_line}), "
                                    f"superando el umbral configurable de {self.file_lines_threshold} líneas."
                                ),
                                recommendation=(
                                    f"Utilizar grep_search para localización previa y acotamiento de ventana mediante "
                                    f"StartLine y EndLine (máximo {self.file_lines_threshold} líneas)."
                                ),
                            )
                        )
        # I. Bucle de Solo Lectura / Parálisis por Inspección (READ_ONLY_LOOP)
        current_passive_steps: List[NormalizedStep] = []
        for s in steps:
            if s.source == "USER" or s.step_type == "USER_INPUT":
                if len(current_passive_steps) >= 4:
                    start_step = current_passive_steps[0].step_index
                    end_step = current_passive_steps[-1].step_index
                    count = len(current_passive_steps)
                    tools_used = sorted(set(tc.name for st in current_passive_steps for tc in st.tool_calls))
                    tools_str = ", ".join(tools_used)
                    antipatterns.append(
                        DetectedAntipattern(
                            severity="ALTA",
                            code="READ_ONLY_LOOP",
                            title="Bucle de Solo Lectura / Parálisis por Inspección",
                            step_index=end_step,
                            description=(
                                f"Se detectaron {count} pasos consecutivos de lecturas pasivas mediante '{tools_str}' "
                                f"sin mutación intermedia de código ni ejecución de pruebas "
                                f"(entre los pasos {start_step} y {end_step}). Indican parálisis por inspección."
                            ),
                            recommendation=(
                                "Detener lecturas consecutivas, formular hipótesis y proceder a mutar código, "
                                "ejecutar pruebas o detenerse con síntesis."
                            ),
                        )
                    )
                current_passive_steps = []
                continue

            if s.tool_calls:
                has_active = any(
                    tc.name.lower() in self.ACTIVE_MUTATION_TOOLS
                    for tc in s.tool_calls
                )
                if has_active:
                    if len(current_passive_steps) >= 4:
                        start_step = current_passive_steps[0].step_index
                        end_step = current_passive_steps[-1].step_index
                        count = len(current_passive_steps)
                        tools_used = sorted(set(tc.name for st in current_passive_steps for tc in st.tool_calls))
                        tools_str = ", ".join(tools_used)
                        antipatterns.append(
                            DetectedAntipattern(
                                severity="ALTA",
                                code="READ_ONLY_LOOP",
                                title="Bucle de Solo Lectura / Parálisis por Inspección",
                                step_index=end_step,
                                description=(
                                    f"Se detectaron {count} pasos consecutivos de lecturas pasivas mediante '{tools_str}' "
                                    f"sin mutación intermedia de código ni ejecución de pruebas "
                                    f"(entre los pasos {start_step} y {end_step}). Indican parálisis por inspección."
                                ),
                                recommendation=(
                                    "Detener lecturas consecutivas, formular hipótesis y proceder a mutar código, "
                                    "ejecutar pruebas o detenerse con síntesis."
                                ),
                            )
                        )
                    current_passive_steps = []
                elif all(
                    tc.name.lower() in self.PASSIVE_INSPECTION_TOOLS
                    for tc in s.tool_calls
                ):
                    current_passive_steps.append(s)

        if len(current_passive_steps) >= 4:
            start_step = current_passive_steps[0].step_index
            end_step = current_passive_steps[-1].step_index
            count = len(current_passive_steps)
            tools_used = sorted(set(tc.name for st in current_passive_steps for tc in st.tool_calls))
            tools_str = ", ".join(tools_used)
            antipatterns.append(
                DetectedAntipattern(
                    severity="ALTA",
                    code="READ_ONLY_LOOP",
                    title="Bucle de Solo Lectura / Parálisis por Inspección",
                    step_index=end_step,
                    description=(
                        f"Se detectaron {count} pasos consecutivos de lecturas pasivas mediante '{tools_str}' "
                        f"sin mutación intermedia de código ni ejecución de pruebas "
                        f"(entre los pasos {start_step} y {end_step}). Indican parálisis por inspección."
                    ),
                    recommendation=(
                        "Detener lecturas consecutivas, formular hipótesis y proceder a mutar código, "
                        "ejecutar pruebas o detenerse con síntesis."
                    ),
                )
            )

        # J. Bucle Cíclico Alternante / Ping-Pong (PING_PONG_TOOL_LOOP)
        tool_events = []
        for s in steps:
            for tc in s.tool_calls:
                target = self.extract_file_target(tc.args) if isinstance(tc.args, dict) else ""
                target_base = Path(target).name if target else ""
                sig = f"{tc.name}:{target_base}" if target_base else tc.name
                tool_events.append((s.step_index, sig))

        if len(tool_events) >= 4:
            flagged_ping_pong_ranges = []
            i = 0
            while i <= len(tool_events) - 4:
                if (tool_events[i][1] != tool_events[i+1][1] and
                    tool_events[i][1] == tool_events[i+2][1] and
                    tool_events[i+1][1] == tool_events[i+3][1]):
                    k = i + 4
                    while k + 1 < len(tool_events) and tool_events[k][1] == tool_events[i][1] and tool_events[k+1][1] == tool_events[i+1][1]:
                        k += 2
                    flagged_ping_pong_ranges.append((tool_events[i][0], tool_events[k-1][0], f"{tool_events[i][1]} <-> {tool_events[i+1][1]}"))
                    i = k
                else:
                    i += 1

            for start_st, end_st, pat in flagged_ping_pong_ranges:
                antipatterns.append(
                    DetectedAntipattern(
                        severity="ALTA",
                        code="PING_PONG_TOOL_LOOP",
                        title="Bucle Cíclico Alternante (Ping-Pong)",
                        step_index=end_st,
                        description=(
                            f"Se detectó un patrón cíclico alternante ('{pat}') "
                            f"entre los pasos {start_st} y {end_st}. "
                            f"El agente alterna herramientas/archivos repetidamente eludiendo límites per-file."
                        ),
                        recommendation=(
                            "Romper la alternancia ciega entre archivos; aplicar disyuntor de seguridad "
                            "y contrastar hipótesis en pruebas o solicitar clarificación."
                        ),
                    )
                )
        # K. Bucle de Parches Ciegos en Pruebas (TEST_RETRY_CHURN)
        antipatterns.extend(self._detect_test_retry_churn(steps))

        # L. Bloqueos de Hooks Deterministas P0
        antipatterns.extend(self._detect_p0_hook_blocks(steps))

        return antipatterns

    def _is_test_tool_call(self, tc: NormalizedToolCall) -> bool:
        """Determina si un tool call corresponde a la ejecución de una prueba o verificación."""
        if tc.name.lower() not in self.TERMINAL_TOOL_NAMES:
            return False
        cmd = str(tc.args.get("CommandLine") or tc.args.get("command") or tc.args.get("cmd") or "") if isinstance(tc.args, dict) else ""
        if self.TEST_COMMAND_REGEX.search(cmd):
            return True
        action_summary = f"{tc.tool_action or ''} {tc.tool_summary or ''}".lower()
        if re.search(r"\b(test|tests|check|prueba|pruebas|verific|suite)\b", action_summary):
            return True
        out_err = f"{tc.raw_output or ''} {tc.error or ''}"
        if self.TEST_FAILURE_REGEX.search(out_err):
            return True
        return False

    def _is_failed_test_call(self, tc: NormalizedToolCall, s: NormalizedStep) -> bool:
        """Determina si un comando de prueba finalizó con error o fallo de aserción/ejecución."""
        if tc.status == "ERROR" or bool(tc.error) or s.status == "ERROR":
            return True
        out_err = f"{tc.raw_output or ''} {tc.error or ''}"
        if self.TEST_FAILURE_REGEX.search(out_err):
            return True
        return False

    def _detect_test_retry_churn(self, steps: List[NormalizedStep]) -> List[DetectedAntipattern]:
        """Detecta secuencias alternantes de edición y fallos en pruebas (>= 3 repeticiones)."""
        antipatterns: List[DetectedAntipattern] = []
        current_cycles: List[Tuple[int, int]] = []
        pending_edit_step: Optional[int] = None

        def flush_cycles():
            nonlocal current_cycles, pending_edit_step
            if len(current_cycles) >= 3:
                start_step = current_cycles[0][0]
                end_step = current_cycles[-1][1]
                count = len(current_cycles)
                antipatterns.append(
                    DetectedAntipattern(
                        severity="ALTA",
                        code="TEST_RETRY_CHURN",
                        title="Bucle de Parches Ciegos en Pruebas (Test Retry Churn)",
                        step_index=end_step,
                        description=(
                            f"Se detectó una secuencia de {count} ciclos alternantes de edición "
                            f"y fallos en pruebas de verificación entre los pasos {start_step} y {end_step}. "
                            f"El agente itera con micro-parches reactivos evadiendo el disyuntor de errores consecutivos."
                        ),
                        recommendation=(
                            "Detener de inmediato los micro-parches reactivos y aplicar un Stop & Read Holístico "
                            "(inspección contextual del bloque o archivo) para diagnosticar la causa raíz antes de volver a mutar."
                        ),
                    )
                )
            current_cycles = []
            pending_edit_step = None

        for s in steps:
            if s.source == "USER" or s.step_type == "USER_INPUT":
                flush_cycles()
                continue

            has_edit = False
            has_failed_test = False
            has_passed_test = False

            if s.tool_calls:
                for tc in s.tool_calls:
                    name_lower = tc.name.lower()
                    if name_lower in self.EDIT_TOOL_NAMES and tc.status != "ERROR":
                        has_edit = True

                    if self._is_test_tool_call(tc):
                        if self._is_failed_test_call(tc, s):
                            has_failed_test = True
                        else:
                            has_passed_test = True

            if has_edit:
                if pending_edit_step is None:
                    pending_edit_step = s.step_index

            if has_failed_test and not has_passed_test:
                if pending_edit_step is not None:
                    current_cycles.append((pending_edit_step, s.step_index))
                    pending_edit_step = None
                elif current_cycles:
                    prev_edit, _ = current_cycles[-1]
                    current_cycles[-1] = (prev_edit, s.step_index)
            elif has_passed_test:
                flush_cycles()

        flush_cycles()
        return antipatterns

    @classmethod
    def _detect_p0_hook_blocks(cls, steps: List[NormalizedStep]) -> List[DetectedAntipattern]:
        """Detecta bloqueos mecánicos de hooks PreToolUse y Guards P0 en Antigravity y Claude Code."""
        p0_blocks: List[DetectedAntipattern] = []
        seen_blocks: Set[Tuple[int, str]] = set()

        hook_marker_regex = re.compile(
            r"(tool call denied by pre-tool hook|hard circuit breaker activado|circuit breaker activado|guard p0:|\[pretooluse\]|pre-tool hook:|denied by pre-tool hook)",
            re.IGNORECASE,
        )

        for s in steps:
            # Recolectar textos de error o salida de herramientas en este paso
            texts_to_check: List[Tuple[str, str]] = []  # (texto, tool_name)
            if s.tool_calls:
                for tc in s.tool_calls:
                    if tc.error:
                        texts_to_check.append((tc.error, tc.name))
                    if tc.raw_output and hook_marker_regex.search(tc.raw_output):
                        texts_to_check.append((tc.raw_output, tc.name))
            elif s.step_type not in ("TOOL_OUTPUT", "GENERIC") and s.content:
                if hook_marker_regex.search(s.content):
                    texts_to_check.append((s.content, "transcript_content"))

            for text, tool_name in texts_to_check:
                if not hook_marker_regex.search(text):
                    continue

                # Determinar regla asociada según el patrón bloqueado
                rule_id = "RIGIDITY_DIRECTIVE_BOUNDARY"
                detail = "restricción dura de entorno"

                if re.search(r"circuit\s*breaker|lecturas?\s*pasivas?\s*consecutivas?|6 lecturas", text, re.IGNORECASE):
                    rule_id = "ENV_PAGED_READ_CIRCUIT_BREAKER"
                    detail = "límite de lecturas pasivas consecutivas alcanzado"
                elif re.search(r"REPL|evalua(?:r|ción)\s+en\s+línea|-c\b|-e\b|evaluador\s+inline", text, re.IGNORECASE):
                    rule_id = "ENV_PROHIBITION_REPL"
                    detail = "evaluación REPL / inline en terminal"
                elif re.search(r"reconocimiento|exfiltración|find\s+/(?!\w)|find\s+\$HOME|volcados masivos", text, re.IGNORECASE):
                    rule_id = "ENV_ANTI_RECON"
                    detail = "reconocimiento ciego del host o exfiltración"
                elif re.search(r"APIs Nativas|I/O en terminal|cat\s*>|sed\s+-i|tee\b", text, re.IGNORECASE):
                    rule_id = "ENV_NATIVE_FILE_API"
                    detail = "operación de I/O en terminal en vez de herramienta nativa"
                elif re.search(r"main|commit.*main|push.*main|Inmutabilidad de Workspace", text, re.IGNORECASE):
                    rule_id = "TRACK_IMMUTABILITY_TRACEABILITY"
                    detail = "intento de commit o push directo a main"
                elif re.search(r"TODO\.md|backlog\.md|tasks/|backlogs locales", text, re.IGNORECASE):
                    rule_id = "TRACK_NO_LOCAL_BACKLOGS"
                    detail = "creación de backlog local no canónico"
                elif re.search(r"HISTORIAL\.md|GEMINI\.md|Decisiones.*MADR", text, re.IGNORECASE):
                    rule_id = "TRACK_DECISIONS_MADR"
                    detail = "creación de registro de decisiones fuera de MADR"
                elif re.search(r"rutas externas|fuera del workspace|\.\.", text, re.IGNORECASE):
                    rule_id = "ENV_WORKSPACE"
                    detail = "acceso o inspección fuera del workspace activo"
                elif re.search(r"BypassSandbox|prefix matching|pipes|tuberías|conectores", text, re.IGNORECASE):
                    rule_id = "AGY_BYPASS_EXCLUSIVITY"
                    detail = "uso no autorizado de bypass o comandos encadenados"

                key = (s.step_index, rule_id)
                if key not in seen_blocks:
                    seen_blocks.add(key)
                    p0_blocks.append(
                        DetectedAntipattern(
                            severity="CRÍTICA",
                            code="P0_HOOK_BLOCK",
                            title="Bloqueo por Hook Determinista P0",
                            step_index=s.step_index,
                            description=(
                                f"El paso {s.step_index} ({tool_name}) fue bloqueado mecánicamente por hook P0: {detail}."
                            ),
                            recommendation=(
                                "Respetar la restricción mecánica y no reintentar a ciegas. "
                                "Aplicar síntesis de estado, la herramienta nativa correspondiente o Stop & Ask."
                            ),
                            rule_id=rule_id,
                        )
                    )

        return p0_blocks


def format_text_report(report: AuditReport, verbose: bool = False) -> str:
    """Genera una salida tabular compacta para terminal."""

    lines: List[str] = []
    lines.append("=" * 72)
    lines.append(f" INFORME DE AUDITORÍA TÉCNICA - AGENT-AUDIT")
    lines.append("=" * 72)
    lines.append(f"  Sesión ID        : {report.metadata.session_id}")
    if report.metadata.title:
        lines.append(f"  Título / Objetivo: {report.metadata.title}")
    lines.append(f"  Runtime          : {report.metadata.runtime.upper()}")
    lines.append(f"  Origen           : {report.metadata.source_path}")
    lines.append(f"  Duración Total   : {report.wall_clock_seconds:.1f} s ({report.wall_clock_seconds / 60.0:.2f} min)")
    lines.append(f"  Pasos Totales    : {report.total_steps} (Usuario: {report.user_turns}, Modelo: {report.model_turns}, Sistema: {report.system_steps})")
    lines.append(f"  Latencia Pasos   : Promedio: {report.avg_step_latency_seconds:.2f} s | Máxima: {report.max_step_latency_seconds:.2f} s")
    lines.append(f"  Tool Calls       : {report.total_tool_calls} total | {report.total_tool_errors} errores ({report.overall_tool_error_rate:.1f}%)")
    lines.append(f"  Thinking / Razon : {report.thinking_steps_count} pasos | {report.total_thinking_chars} chars (prom: {report.avg_thinking_chars:.0f} chars/paso)")
    lines.append("-" * 72)

    # Desglose de herramientas
    lines.append(" DESGLOSE DE HERRAMIENTAS:")
    lines.append(f"  {'Herramienta':<28} {'Invocaciones':<14} {'Errores':<10} {'Tasa Fallo':<12}")
    lines.append("  " + "-" * 66)
    for name, m in sorted(report.tool_metrics.items(), key=lambda x: x[1].invocations, reverse=True):
        lines.append(f"  {name:<28} {m.invocations:<14} {m.errors:<10} {m.error_rate:.1f}%")
    lines.append("-" * 72)

    # Pasos más lentos
    if report.slowest_steps:
        lines.append(" PASOS DE MAYOR LATENCIA (TOP 5):")
        for s in report.slowest_steps:
            tools_str = ", ".join(s["tools"]) if s["tools"] else "N/A"
            detail_str = f" | {s['detail']}" if "detail" in s and s["detail"] else ""
            lines.append(f"  - Paso {s['step_index']:<3} : {s['duration_seconds']:>6.1f} s | {s['type']:<18} | Tools: {tools_str}{detail_str}")
        lines.append("-" * 72)

    # Cronología detallada si verbose
    if verbose and report.steps_timeline:
        lines.append(f" CRONOLOGÍA DE PASOS ({len(report.steps_timeline)} pasos):")
        for st in report.steps_timeline:
            tools_str = ", ".join(f"{t['name']}({t['action'] or t['command'][:40]})" if isinstance(t, dict) else str(t) for t in st["tools"]) if st["tools"] else ""
            snip = f" | {st['content_snippet']}" if st["source"] == "USER" else (f" | {tools_str}" if tools_str else "")
            dur = f"{st['duration_seconds']:>6.1f}s"
            lines.append(f"  [{st['step_index']:>3}] {dur} | {st['source']:<6} | {st['type']:<16}{snip}")
        lines.append("-" * 72)

    # Antipatrones
    lines.append(f" ANTIPATRONES DETECTADOS ({len(report.antipatterns)}):")
    if not report.antipatterns:
        lines.append("  [✓] No se detectaron anomalías ni antipatrones de comportamiento.")
    else:
        for ap in report.antipatterns:
            lines.append(f"  [{ap.severity}] Paso {ap.step_index}: {ap.title} ({ap.code})")
            lines.append(f"      Detalle: {ap.description}")
            lines.append(f"      Acción : {ap.recommendation}")
    lines.append("=" * 72)

    return "\n".join(lines)


def format_markdown_report(report: AuditReport, template_path: Optional[Path] = None) -> str:
    """Genera el informe en formato Markdown utilizando la plantilla o estructura estándar."""
    lines: List[str] = []
    lines.append(f"# Informe de Auditoría Técnica: Sesión `{report.metadata.session_id}`")
    lines.append("")
    lines.append("## 1. Resumen Ejecutivo")
    lines.append("")
    if report.metadata.title:
        lines.append(f"- **Título / Objetivo:** {report.metadata.title}")
    lines.append(f"- **Runtime:** `{report.metadata.runtime}`")
    lines.append(f"- **Origen:** `{report.metadata.source_path}`")
    lines.append(f"- **Duración Wall-Clock:** {report.wall_clock_seconds:.1f} s ({report.wall_clock_seconds / 60.0:.2f} min)")
    lines.append(f"- **Pasos Totales:** {report.total_steps} (Usuario: {report.user_turns}, Modelo: {report.model_turns}, Sistema: {report.system_steps})")
    lines.append(f"- **Latencia Promedio por Paso:** {report.avg_step_latency_seconds:.2f} s")
    lines.append(f"- **Latencia Máxima:** {report.max_step_latency_seconds:.2f} s")
    lines.append(f"- **Llamadas a Herramientas:** {report.total_tool_calls} (Errores: {report.total_tool_errors}, Tasa de falla: {report.overall_tool_error_rate:.1f}%)")
    lines.append(f"- **Pasos de Pensamiento/Thinking:** {report.thinking_steps_count} (Total caracteres: {report.total_thinking_chars})")
    lines.append("")
    lines.append("## 2. Desglose de Herramientas")
    lines.append("")
    lines.append("| Herramienta | Invocaciones | Errores | Tasa de Falla (%) |")
    lines.append("| :--- | :---: | :---: | :---: |")
    for name, m in sorted(report.tool_metrics.items(), key=lambda x: x[1].invocations, reverse=True):
        lines.append(f"| `{name}` | {m.invocations} | {m.errors} | {m.error_rate:.1f}% |")
    lines.append("")
    lines.append("## 3. Pasos de Mayor Latencia (Top 5)")
    lines.append("")
    lines.append("| Paso | Duración (s) | Tipo | Herramientas Invocadas |")
    lines.append("| :---: | :---: | :--- | :--- |")
    for s in report.slowest_steps:
        tools_str = ", ".join(f"`{t}`" for t in s["tools"]) if s["tools"] else "N/A"
        detail_str = f" ({s['detail']})" if "detail" in s and s["detail"] else ""
        lines.append(f"| {s['step_index']} | {s['duration_seconds']} | `{s['type']}` | {tools_str}{detail_str} |")
    lines.append("")
    lines.append("## 4. Antipatrones y Anomalías Detectadas")
    lines.append("")
    if not report.antipatterns:
        lines.append("> [!TIP]\n> No se detectaron anomalías ni vicios de comportamiento en esta sesión.")
    else:
        lines.append("| Severidad | Paso | Antipatrón | Descripción | Acción Correctiva |")
        lines.append("| :--- | :---: | :--- | :--- | :--- |")
        for ap in report.antipatterns:
            lines.append(f"| **{ap.severity}** | {ap.step_index} | `{ap.code}` | {ap.description} | {ap.recommendation} |")
    lines.append("")
    lines.append("---")
    lines.append("*Generado automáticamente por el CLI `agent-audit` de Dotfiles-IA-Agents.*")

    return "\n".join(lines)


def format_json_report(report: AuditReport) -> str:
    """Genera una salida serializable JSON."""
    import json

    def custom_serializer(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "__dict__"):
            return asdict(obj)
        return str(obj)

    data = {
        "metadata": asdict(report.metadata),
        "metrics": {
            "total_steps": report.total_steps,
            "user_turns": report.user_turns,
            "model_turns": report.model_turns,
            "system_steps": report.system_steps,
            "wall_clock_seconds": round(report.wall_clock_seconds, 2),
            "avg_step_latency_seconds": round(report.avg_step_latency_seconds, 2),
            "max_step_latency_seconds": round(report.max_step_latency_seconds, 2),
            "total_tool_calls": report.total_tool_calls,
            "total_tool_errors": report.total_tool_errors,
            "overall_tool_error_rate": round(report.overall_tool_error_rate, 2),
            "thinking_steps_count": report.thinking_steps_count,
            "total_thinking_chars": report.total_thinking_chars,
            "avg_thinking_chars": round(report.avg_thinking_chars, 2),
        },
        "slowest_steps": report.slowest_steps,
        "tools": {name: asdict(m) for name, m in report.tool_metrics.items()},
        "antipatterns": [asdict(ap) for ap in report.antipatterns],
        "timeline": report.steps_timeline,
    }
    return json.dumps(data, indent=2, default=custom_serializer)


def format_text_metadata(metadata: ConversationMetadata) -> str:
    """Genera una salida compacta de metadatos de sesión para terminal."""
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append(" METADATOS DE SESIÓN - AGENT-AUDIT")
    lines.append("=" * 72)
    lines.append(f"  Sesión ID        : {metadata.session_id}")
    lines.append(f"  Título / Objetivo: {metadata.title or 'N/A'}")
    lines.append(f"  Runtime          : {metadata.runtime.upper()}")
    lines.append(f"  Origen           : {metadata.source_path}")
    if metadata.start_time:
        lines.append(f"  Inicio           : {metadata.start_time.isoformat()}")
    if metadata.end_time:
        lines.append(f"  Fin              : {metadata.end_time.isoformat()}")
    lines.append("=" * 72)
    return "\n".join(lines)


def format_markdown_metadata(metadata: ConversationMetadata) -> str:
    """Genera informe Markdown de metadatos de sesión."""
    lines: List[str] = []
    lines.append(f"# Metadatos de Sesión: `{metadata.session_id}`")
    lines.append("")
    lines.append(f"- **Título / Objetivo:** {metadata.title or 'N/A'}")
    lines.append(f"- **Runtime:** `{metadata.runtime}`")
    lines.append(f"- **Origen:** `{metadata.source_path}`")
    lines.append(f"- **Inicio:** {metadata.start_time.isoformat() if metadata.start_time else 'N/A'}")
    lines.append(f"- **Fin:** {metadata.end_time.isoformat() if metadata.end_time else 'N/A'}")
    lines.append("")
    lines.append("---")
    lines.append("*Generado por `agent-audit` (Dotfiles-IA-Agents).*")
    return "\n".join(lines)


def format_json_metadata(metadata: ConversationMetadata) -> str:
    """Genera JSON de metadatos de sesión."""
    import json

    def custom_serializer(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "__dict__"):
            return asdict(obj)
        return str(obj)

    return json.dumps({"metadata": asdict(metadata)}, indent=2, default=custom_serializer)


def truncate_str(text: Optional[str], max_chars: int = 1500) -> Optional[str]:
    """Acota cadenas largas para evitar desbordes de contexto en inspección de pasos."""
    if text is None:
        return None
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n... [Salida truncada: se muestran {max_chars} de {len(text)} caracteres]"


def format_args(args: Any, max_chars: int = 1000) -> str:
    """Formatea argumentos de herramientas en JSON o string acotado."""
    import json
    if not args:
        return "{}"
    if isinstance(args, dict):
        try:
            formatted = json.dumps(args, indent=2, ensure_ascii=False)
        except Exception:
            formatted = str(args)
    else:
        formatted = str(args)
    if len(formatted) > max_chars:
        return formatted[:max_chars] + f"\n... [Argumentos truncados: {max_chars}/{len(formatted)} caracteres]"
    return formatted


def _extract_step_call_ids(step: NormalizedStep) -> set:
    """Extrae los identificadores de llamada (call_id / tool_use_id) asociados a un paso."""
    ids = {str(tc.call_id) for tc in step.tool_calls if tc.call_id}

    raw = step.raw
    if isinstance(raw, dict):
        top_id = raw.get("call_id") or raw.get("tool_use_id")
        if top_id:
            ids.add(str(top_id))

        content_blocks = raw.get("content")
        if isinstance(content_blocks, list):
            for b in content_blocks:
                if isinstance(b, dict):
                    b_id = b.get("tool_use_id") or b.get("call_id")
                    if b_id:
                        ids.add(str(b_id))
    return ids


def get_failed_steps(steps: List[NormalizedStep]) -> List[NormalizedStep]:
    """Filtra y devuelve exclusivamente los pasos que arrojaron errores o excepciones en herramientas."""
    failed: List[NormalizedStep] = []
    for s in steps:
        has_tool_error = any(tc.status == "ERROR" or tc.error for tc in s.tool_calls)
        if has_tool_error:
            failed.append(s)
        elif s.status == "ERROR":
            # Si es un step de salida pura de herramienta (GENERIC/TOOL_OUTPUT),
            # evitar duplicación si el paso inmediatamente anterior ya registró el error en sus tool_calls
            if s.step_type in ("GENERIC", "TOOL_OUTPUT") and failed:
                prev = failed[-1]
                if prev.step_index == s.step_index - 1:
                    prev_failed_ids = {
                        str(tc.call_id) for tc in prev.tool_calls
                        if (tc.status == "ERROR" or tc.error) and tc.call_id
                    }
                    s_ids = _extract_step_call_ids(s)
                    if s_ids & prev_failed_ids:
                        continue
                    if not s_ids and any(tc.error == s.content for tc in prev.tool_calls):
                        continue
            failed.append(s)
    return failed


def parse_step_ranges(expression: str) -> List[int]:
    """
    Parsea una expresión de pasos y rangos numéricos y retorna una lista ordenada y deduplicada.

    Formatos soportados:
    - Pasos individuales: "5", "0"
    - Rangos con guión: "87-105"
    - Rangos con dos puntos: "87..105"
    - Listas separadas por comas: "87,88,92,100"
    - Mezcla de rangos y pasos: "1-5,87-90,105", "1..5, 87..90, 105"

    Lanza ValueError si la sintaxis es inválida, si hay valores no numéricos,
    o si en algún rango el inicio es mayor que el fin.
    """
    if not expression or not expression.strip():
        raise ValueError("La expresión de pasos o rangos no puede estar vacía.")

    parts = [p.strip() for p in expression.split(",") if p.strip()]
    if not parts:
        raise ValueError("La expresión de pasos o rangos no puede estar vacía.")

    indices = set()
    for part in parts:
        if ".." in part:
            subparts = part.split("..")
            if len(subparts) != 2:
                raise ValueError(f"Sintaxis de rango inválida: '{part}'")
            s_start, s_end = subparts[0].strip(), subparts[1].strip()
            if not (s_start.isdigit() and s_end.isdigit()):
                raise ValueError(f"Sintaxis de rango inválida: '{part}' (los límites deben ser enteros no negativos)")
            start, end = int(s_start), int(s_end)
            if start > end:
                raise ValueError(f"Rango inválido: '{part}' (el inicio {start} no puede ser mayor que el fin {end})")
            indices.update(range(start, end + 1))
        elif "-" in part:
            subparts = part.split("-")
            if len(subparts) != 2:
                raise ValueError(f"Sintaxis de rango inválida: '{part}'")
            s_start, s_end = subparts[0].strip(), subparts[1].strip()
            if not (s_start.isdigit() and s_end.isdigit()):
                raise ValueError(f"Sintaxis de rango inválida: '{part}' (los límites deben ser enteros no negativos)")
            start, end = int(s_start), int(s_end)
            if start > end:
                raise ValueError(f"Rango inválido: '{part}' (el inicio {start} no puede ser mayor que el fin {end})")
            indices.update(range(start, end + 1))
        elif part.isdigit():
            indices.add(int(part))
        else:
            raise ValueError(f"Sintaxis de paso o rango inválida: '{part}'")

    return sorted(list(indices))


def filter_steps_by_tool(
    steps: List[NormalizedStep],
    tool_name: str,
) -> List[NormalizedStep]:
    """
    Filtra y devuelve los pasos que contienen al menos una llamada a la herramienta especificada.
    Soporta coincidencias exactas o nombres normalizados sin prefijo MCP (ej. 'run_command', 'search_docs').
    """
    if not tool_name or not tool_name.strip():
        return steps

    target_tool = tool_name.strip().lower()

    def matches_tool(call_name: str) -> bool:
        cn = call_name.strip().lower()
        if cn == target_tool:
            return True
        if cn.endswith(f"_{target_tool}") or cn.endswith(f":{target_tool}"):
            return True
        return False

    return [
        s for s in steps
        if any(matches_tool(tc.name) for tc in s.tool_calls)
    ]


def format_text_step(step: Any, max_content_chars: int = 1500) -> str:
    """Genera una salida tabular acotada para un paso específico (o lista de pasos)."""
    if isinstance(step, list):
        return format_text_steps(step, max_content_chars=max_content_chars)
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append(f" DETALLE DE PASO {step.step_index} - AGENT-AUDIT")
    lines.append("=" * 72)
    lines.append(f"  Paso             : {step.step_index}")
    lines.append(f"  Fuente           : {step.source}")
    lines.append(f"  Tipo             : {step.step_type}")
    lines.append(f"  Estado           : {step.status}")
    if step.created_at:
        lines.append(f"  Timestamp        : {step.created_at.isoformat()}")
    if step.duration_seconds is not None:
        lines.append(f"  Duración         : {step.duration_seconds:.2f} s")
    if step.truncated_fields:
        lines.append(f"  Campos Truncados : {', '.join(step.truncated_fields)}")
    if step.tokens:
        tok_str = ", ".join(f"{k}: {v}" for k, v in step.tokens.items() if v)
        if tok_str:
            lines.append(f"  Tokens           : {tok_str}")
    lines.append("-" * 72)

    if step.thinking:
        lines.append(" PENSAMIENTO / THINKING:")
        t_trunc = truncate_str(step.thinking, max_content_chars)
        for t_line in (t_trunc or "").splitlines():
            lines.append(f"  {t_line}")
        lines.append("-" * 72)

    if step.content:
        lines.append(" CONTENIDO / TEXTO:")
        c_trunc = truncate_str(step.content, max_content_chars)
        for c_line in (c_trunc or "").splitlines():
            lines.append(f"  {c_line}")
        lines.append("-" * 72)

    if step.tool_calls:
        lines.append(f" LLAMADAS A HERRAMIENTAS ({len(step.tool_calls)}):")
        for i, tc in enumerate(step.tool_calls, 1):
            lines.append(f"  [{i}/{len(step.tool_calls)}] Herramienta: {tc.name} | Estado: {tc.status}")
            if tc.call_id:
                lines.append(f"      Call ID : {tc.call_id}")
            if tc.tool_action:
                lines.append(f"      Acción  : {tc.tool_action}")
            if tc.tool_summary:
                lines.append(f"      Resumen : {tc.tool_summary}")
            if tc.args:
                lines.append("      Argumentos:")
                arg_str = format_args(tc.args, max_content_chars)
                for a_line in arg_str.splitlines():
                    lines.append(f"        {a_line}")
            if tc.error:
                lines.append("      ERROR:")
                err_str = truncate_str(tc.error, max_content_chars)
                for e_line in (err_str or "").splitlines():
                    lines.append(f"        {e_line}")
            elif tc.raw_output:
                lines.append("      Salida:")
                out_str = truncate_str(tc.raw_output, max_content_chars)
                for o_line in (out_str or "").splitlines():
                    lines.append(f"        {o_line}")
        lines.append("-" * 72)
    elif not step.thinking and not step.content:
        lines.append("  (Paso sin contenido textual ni llamadas a herramientas)")
        lines.append("-" * 72)

    lines.append("=" * 72)
    return "\n".join(lines)


def format_text_steps(steps: List[NormalizedStep], max_content_chars: int = 1500) -> str:
    """Genera salida tabular acotada para una secuencia de pasos específicos."""
    if not steps:
        return "No se encontraron pasos coincidentes con los criterios de inspección."

    step_indices_str = ", ".join(str(s.step_index) for s in steps)
    plural_str = "pasos" if len(steps) != 1 else "paso"
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append(f" INSPECCIÓN DE PASOS ({len(steps)} {plural_str}) - AGENT-AUDIT")
    lines.append("=" * 72)
    lines.append(f"  Pasos incluidos : {step_indices_str}")
    lines.append("=" * 72)
    lines.append("")

    step_blocks = [format_text_step(s, max_content_chars=max_content_chars) for s in steps]
    lines.append("\n\n".join(step_blocks))
    return "\n".join(lines)


def format_markdown_step(step: Any, max_content_chars: int = 1500) -> str:
    """Genera informe Markdown acotado para un paso específico (o lista de pasos)."""
    if isinstance(step, list):
        return format_markdown_steps(step, max_content_chars=max_content_chars)
    lines: List[str] = []
    lines.append(f"# Detalle del Paso `{step.step_index}`")
    lines.append("")
    lines.append(f"- **Paso:** `{step.step_index}`")
    lines.append(f"- **Fuente:** `{step.source}`")
    lines.append(f"- **Tipo:** `{step.step_type}`")
    lines.append(f"- **Estado:** `{step.status}`")
    if step.created_at:
        lines.append(f"- **Timestamp:** `{step.created_at.isoformat()}`")
    if step.duration_seconds is not None:
        lines.append(f"- **Duración:** `{step.duration_seconds:.2f} s`")
    if step.truncated_fields:
        lines.append(f"- **Campos Truncados:** `{', '.join(step.truncated_fields)}`")
    lines.append("")

    if step.thinking:
        lines.append("## Pensamiento (Thinking)")
        lines.append("")
        lines.append(f"```\n{truncate_str(step.thinking, max_content_chars)}\n```")
        lines.append("")

    if step.content:
        lines.append("## Contenido")
        lines.append("")
        lines.append(f"```\n{truncate_str(step.content, max_content_chars)}\n```")
        lines.append("")

    if step.tool_calls:
        lines.append(f"## Llamadas a Herramientas ({len(step.tool_calls)})")
        lines.append("")
        for i, tc in enumerate(step.tool_calls, 1):
            lines.append(f"### {i}. `{tc.name}`")
            lines.append(f"- **Estado:** `{tc.status}`")
            if tc.call_id:
                lines.append(f"- **Call ID:** `{tc.call_id}`")
            if tc.tool_action:
                lines.append(f"- **Acción:** {tc.tool_action}")
            if tc.tool_summary:
                lines.append(f"- **Resumen:** {tc.tool_summary}")
            lines.append("")
            if tc.args:
                lines.append("#### Argumentos")
                lines.append("```json")
                lines.append(format_args(tc.args, max_content_chars))
                lines.append("```")
                lines.append("")
            if tc.error:
                lines.append("#### Error")
                lines.append("```")
                lines.append(truncate_str(tc.error, max_content_chars))
                lines.append("```")
                lines.append("")
            elif tc.raw_output:
                lines.append("#### Salida")
                lines.append("```")
                lines.append(truncate_str(tc.raw_output, max_content_chars))
                lines.append("```")
                lines.append("")

    lines.append("---")
    lines.append("*Inspección quirúrgica generada por `agent-audit --inspect-step`.*")
    return "\n".join(lines)


def format_markdown_steps(steps: List[NormalizedStep], max_content_chars: int = 1500) -> str:
    """Genera informe Markdown acotado para múltiples pasos específicos."""
    if not steps:
        return "# Inspección de Pasos\n\nNo se encontraron pasos coincidentes con los criterios de inspección.\n"

    lines: List[str] = []
    step_indices_str = ", ".join(str(s.step_index) for s in steps)
    plural_str = "pasos" if len(steps) != 1 else "paso"
    lines.append(f"# Inspección de Pasos ({len(steps)} {plural_str})")
    lines.append("")
    lines.append(f"- **Total de pasos inspeccionados:** `{len(steps)}`")
    lines.append(f"- **Pasos incluidos:** `{step_indices_str}`")
    lines.append("")
    lines.append("---")
    lines.append("")

    for s in steps:
        lines.append(f"## Detalle del Paso `{s.step_index}`")
        lines.append("")
        lines.append(f"- **Paso:** `{s.step_index}`")
        lines.append(f"- **Fuente:** `{s.source}`")
        lines.append(f"- **Tipo:** `{s.step_type}`")
        lines.append(f"- **Estado:** `{s.status}`")
        if s.created_at:
            lines.append(f"- **Timestamp:** `{s.created_at.isoformat()}`")
        if s.duration_seconds is not None:
            lines.append(f"- **Duración:** `{s.duration_seconds:.2f} s`")
        if s.truncated_fields:
            lines.append(f"- **Campos Truncados:** `{', '.join(s.truncated_fields)}`")
        lines.append("")

        if s.thinking:
            lines.append("### Pensamiento (Thinking)")
            lines.append("")
            lines.append(f"```\n{truncate_str(s.thinking, max_content_chars)}\n```")
            lines.append("")

        if s.content:
            lines.append("### Contenido")
            lines.append("")
            lines.append(f"```\n{truncate_str(s.content, max_content_chars)}\n```")
            lines.append("")

        if s.tool_calls:
            lines.append(f"### Llamadas a Herramientas ({len(s.tool_calls)})")
            lines.append("")
            for i, tc in enumerate(s.tool_calls, 1):
                lines.append(f"#### {i}. `{tc.name}`")
                lines.append(f"- **Estado:** `{tc.status}`")
                if tc.call_id:
                    lines.append(f"- **Call ID:** `{tc.call_id}`")
                if tc.tool_action:
                    lines.append(f"- **Acción:** {tc.tool_action}")
                if tc.tool_summary:
                    lines.append(f"- **Resumen:** {tc.tool_summary}")
                lines.append("")
                if tc.args:
                    lines.append("##### Argumentos")
                    lines.append("```json")
                    lines.append(format_args(tc.args, max_content_chars))
                    lines.append("```")
                    lines.append("")
                if tc.error:
                    lines.append("##### Error")
                    lines.append("```")
                    lines.append(truncate_str(tc.error, max_content_chars))
                    lines.append("```")
                    lines.append("")
                elif tc.raw_output:
                    lines.append("##### Salida")
                    lines.append("```")
                    lines.append(truncate_str(tc.raw_output, max_content_chars))
                    lines.append("```")
                    lines.append("")
        elif not s.thinking and not s.content:
            lines.append("*(Paso sin contenido textual ni llamadas a herramientas)*")
            lines.append("")

        lines.append("---")
        lines.append("")

    lines.append("*Inspección quirúrgica generada por `agent-audit --inspect-steps`.*")
    return "\n".join(lines)


def _step_to_dict(step: NormalizedStep, max_content_chars: int = 2000) -> Dict[str, Any]:
    """Serializa un NormalizedStep en diccionario acotando campos extensos."""
    def clean_val(v):
        if isinstance(v, str) and len(v) > max_content_chars:
            return v[:max_content_chars] + f"... [Truncado: {max_content_chars}/{len(v)} chars]"
        if isinstance(v, dict):
            return {k: clean_val(val) for k, val in v.items()}
        if isinstance(v, list):
            return [clean_val(item) for item in v]
        return v

    return {
        "step_index": step.step_index,
        "source": step.source,
        "step_type": step.step_type,
        "status": step.status,
        "created_at": step.created_at.isoformat() if step.created_at else None,
        "duration_seconds": step.duration_seconds,
        "thinking": clean_val(step.thinking),
        "content": clean_val(step.content),
        "truncated_fields": step.truncated_fields,
        "tokens": step.tokens,
        "tool_calls": [
            {
                "name": tc.name,
                "call_id": tc.call_id,
                "tool_action": tc.tool_action,
                "tool_summary": tc.tool_summary,
                "status": tc.status,
                "args": clean_val(tc.args),
                "error": clean_val(tc.error),
                "raw_output": clean_val(tc.raw_output),
            }
            for tc in step.tool_calls
        ],
    }


def format_json_step(step: Any, max_content_chars: int = 2000) -> str:
    """Genera JSON acotado para un paso específico (o lista de pasos)."""
    if isinstance(step, list):
        return format_json_steps(step, max_content_chars=max_content_chars)

    import json

    def custom_serializer(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "__dict__"):
            return asdict(obj)
        return str(obj)

    step_data = _step_to_dict(step, max_content_chars=max_content_chars)
    return json.dumps(step_data, indent=2, default=custom_serializer)


def format_json_steps(steps: List[NormalizedStep], max_content_chars: int = 2000) -> str:
    """Genera JSON acotado para una secuencia de pasos específicos."""
    import json

    def custom_serializer(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "__dict__"):
            return asdict(obj)
        return str(obj)

    data = {
        "total_steps": len(steps),
        "steps": [_step_to_dict(s, max_content_chars=max_content_chars) for s in steps],
    }
    return json.dumps(data, indent=2, default=custom_serializer)


def format_text_failed_steps(failed_steps: List[NormalizedStep], max_snippet_chars: int = 500) -> str:
    """Genera una salida tabular de pasos con errores de herramientas."""
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append(" PASOS CON ERRORES DE HERRAMIENTAS - AGENT-AUDIT")
    lines.append("=" * 72)
    if not failed_steps:
        lines.append("  [✓] No se registraron pasos con errores de herramientas en la sesión.")
        lines.append("=" * 72)
        return "\n".join(lines)

    lines.append(f"  Total de pasos con errores: {len(failed_steps)}")
    lines.append("-" * 72)
    for s in failed_steps:
        dur_str = f" ({s.duration_seconds:.1f}s)" if s.duration_seconds is not None else ""
        lines.append(f"  Paso {s.step_index:<4} | {s.source:<6} | {s.step_type:<18} | Estado: {s.status}{dur_str}")
        if s.tool_calls:
            for tc in s.tool_calls:
                err_mark = "[FALLÓ]" if (tc.status == "ERROR" or tc.error) else "[OK]"
                cmd = str(tc.args.get("CommandLine") or tc.args.get("command") or "") if isinstance(tc.args, dict) else ""
                act = tc.tool_action or tc.tool_summary or (cmd[:60] if cmd else "N/A")
                lines.append(f"    - {err_mark} Tool: {tc.name} ({act})")
                if tc.error:
                    err_clean = truncate_str(tc.error.strip(), max_snippet_chars)
                    for el in (err_clean or "").splitlines():
                        lines.append(f"        Error: {el}")
        elif s.content:
            c_clean = truncate_str(s.content.strip(), max_snippet_chars)
            for cl in (c_clean or "").splitlines():
                lines.append(f"    Detalle: {cl}")
        lines.append("-" * 72)
    lines.append("=" * 72)
    return "\n".join(lines)


def format_markdown_failed_steps(failed_steps: List[NormalizedStep], max_snippet_chars: int = 500) -> str:
    """Genera informe Markdown de pasos con errores de herramientas."""
    lines: List[str] = []
    lines.append("# Pasos con Errores de Herramientas")
    lines.append("")
    if not failed_steps:
        lines.append("> [!TIP]")
        lines.append("> No se registraron pasos con errores de herramientas en esta sesión.")
        lines.append("")
        lines.append("---")
        lines.append("*Consulta quirúrgica generada por `agent-audit --failed-steps`.*")
        return "\n".join(lines)

    lines.append(f"Total de pasos con errores detectados: **{len(failed_steps)}**")
    lines.append("")
    lines.append("| Paso | Fuente / Tipo | Herramienta | Acción / Comando | Detalle del Error |")
    lines.append("| :---: | :--- | :--- | :--- | :--- |")
    for s in failed_steps:
        if s.tool_calls:
            for tc in s.tool_calls:
                if tc.status == "ERROR" or tc.error:
                    cmd = str(tc.args.get("CommandLine") or tc.args.get("command") or "") if isinstance(tc.args, dict) else ""
                    act = tc.tool_action or tc.tool_summary or (f"`{cmd[:40]}...`" if cmd else "N/A")
                    err_desc = (tc.error or "").replace("\n", " ").strip()
                    if len(err_desc) > 80:
                        err_desc = err_desc[:77] + "..."
                    lines.append(f"| `{s.step_index}` | `{s.source}` / `{s.step_type}` | `{tc.name}` | {act} | {err_desc} |")
        elif s.content:
            err_desc = s.content.replace("\n", " ").strip()
            if len(err_desc) > 80:
                err_desc = err_desc[:77] + "..."
            lines.append(f"| `{s.step_index}` | `{s.source}` / `{s.step_type}` | N/A | N/A | {err_desc} |")
    lines.append("")
    lines.append("---")
    lines.append("*Consulta quirúrgica generada por `agent-audit --failed-steps`.*")
    return "\n".join(lines)


def format_json_failed_steps(failed_steps: List[NormalizedStep], max_snippet_chars: int = 500) -> str:
    """Genera JSON de pasos con errores de herramientas."""
    import json

    def custom_serializer(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "__dict__"):
            return asdict(obj)
        return str(obj)

    data = {
        "total_failed_steps": len(failed_steps),
        "failed_steps": [
            {
                "step_index": s.step_index,
                "source": s.source,
                "step_type": s.step_type,
                "status": s.status,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "duration_seconds": s.duration_seconds,
                "failed_tools": [
                    {
                        "name": tc.name,
                        "action": tc.tool_action or tc.tool_summary,
                        "command": tc.args.get("CommandLine") or tc.args.get("command") or "" if isinstance(tc.args, dict) else "",
                        "error": truncate_str(tc.error, max_snippet_chars),
                    }
                    for tc in s.tool_calls
                    if tc.status == "ERROR" or tc.error
                ],
                "error_snippet": truncate_str(s.content, max_snippet_chars) if not s.tool_calls else None,
            }
            for s in failed_steps
        ],
    }
    return json.dumps(data, indent=2, default=custom_serializer)


def aggregate_rules_violations(reports: List[AuditReport]) -> RulesViolationReport:
    """Consolida las violaciones por ID de regla a través de una o múltiples sesiones."""
    total_sessions = len(reports)

    ap_counts: Dict[str, int] = defaultdict(int)
    p0_counts: Dict[str, int] = defaultdict(int)
    sessions_by_rule: Dict[str, Set[str]] = defaultdict(set)
    unmapped_count = 0

    for rep in reports:
        sess_id = rep.metadata.session_id or Path(rep.metadata.source_path).name or "sesion_anonima"
        for ap in rep.antipatterns:
            if ap.rule_id:
                if ap.code == "P0_HOOK_BLOCK":
                    p0_counts[ap.rule_id] += 1
                else:
                    ap_counts[ap.rule_id] += 1
                sessions_by_rule[ap.rule_id].add(sess_id)
            else:
                unmapped_count += 1

    all_rule_ids = list(RULE_REGISTRY.keys())
    detected_extra = set(ap_counts.keys()) | set(p0_counts.keys())
    for r_id in sorted(detected_extra):
        if r_id not in RULE_REGISTRY:
            all_rule_ids.append(r_id)

    summaries: List[RuleViolationSummary] = []
    total_violations = 0

    for r_id in all_rule_ids:
        meta = RULE_REGISTRY.get(r_id, {"level": "P2", "description": "Regla de comportamiento"})
        level = meta.get("level", "P2")
        desc = meta.get("description", "")

        ap_c = ap_counts.get(r_id, 0)
        p0_c = p0_counts.get(r_id, 0)
        tot = ap_c + p0_c
        total_violations += tot

        sess_list = sorted(list(sessions_by_rule.get(r_id, set())))

        # Acción sugerida según ciclo de mejora continua (#282 / #285)
        if level == "P2":
            if tot > 0:
                action = "Candidata a promoción a P0 (violación recurrente mecanizable)"
            else:
                action = f"Candidata a bajar a P1 o eliminarse (0 violaciones en {total_sessions} ses.)"
        elif level == "P0":
            if tot > 0:
                action = "Enforcement mecánico P0 activo (bloqueos interceptados)"
            else:
                action = "Enforcement mecánico P0 en regla (0 infracciones)"
        elif "P0" in level:
            if tot > 0:
                action = "Reforzar cobertura P0 (infracciones observadas)"
            else:
                action = "Enforcement P0/P2 en regla (0 infracciones)"
        elif level == "P1":
            if tot > 0:
                action = "Revisar adherencia a procedimiento P1"
            else:
                action = "Procedimiento P1 en regla"
        else:
            action = "Regla de compilación / build en regla"

        summaries.append(
            RuleViolationSummary(
                rule_id=r_id,
                level=level,
                description=desc,
                total_violations=tot,
                sessions_count=len(sess_list),
                sessions=sess_list,
                antipattern_count=ap_c,
                p0_block_count=p0_c,
                action_suggestion=action,
            )
        )

    # Ordenar: primero los que tienen violaciones (descendente por total), luego por rule_id
    summaries.sort(key=lambda s: (-s.total_violations, s.rule_id))

    return RulesViolationReport(
        total_sessions=total_sessions,
        total_violations=total_violations,
        rule_summaries=summaries,
        unmapped_antipatterns=unmapped_count,
    )


def format_text_rules_report(report: RulesViolationReport) -> str:
    """Genera informe tabular en texto plano con métricas de violaciones por ID de regla."""
    lines: List[str] = []
    lines.append("=" * 80)
    lines.append(" INFORME DE VIOLACIONES POR ID DE REGLA - AGENT-AUDIT")
    lines.append("=" * 80)
    lines.append(f"  Sesiones analizadas   : {report.total_sessions}")
    lines.append(f"  Total de violaciones  : {report.total_violations}")
    lines.append(f"  Antipatrones sin regla: {report.unmapped_antipatterns}")
    lines.append("=" * 80)

    with_violations = [s for s in report.rule_summaries if s.total_violations > 0]
    without_violations = [s for s in report.rule_summaries if s.total_violations == 0]

    lines.append(f" REGLAS CON VIOLACIONES ({len(with_violations)}):")
    lines.append("-" * 80)
    header = f" {'ID DE REGLA':<32} {'NIVEL':<7} {'VIOL':>5} {'SES':>4} {'AP/P0':>7}  {'ACCIÓN SUGERIDA'}"
    lines.append(header)
    lines.append("-" * 80)

    if with_violations:
        for s in with_violations:
            ratio = f"{s.antipattern_count}/{s.p0_block_count}"
            lines.append(
                f" {s.rule_id:<32} {s.level:<7} {s.total_violations:>5} {s.sessions_count:>4} {ratio:>7}  {s.action_suggestion}"
            )
    else:
        lines.append("  (No se registraron violaciones en las sesiones analizadas)")

    lines.append("-" * 80)
    lines.append(f" REGLAS SIN VIOLACIONES ({len(without_violations)}):")
    lines.append("-" * 80)
    lines.append(header)
    lines.append("-" * 80)
    for s in without_violations:
        ratio = f"{s.antipattern_count}/{s.p0_block_count}"
        lines.append(
            f" {s.rule_id:<32} {s.level:<7} {s.total_violations:>5} {s.sessions_count:>4} {ratio:>7}  {s.action_suggestion}"
        )
    lines.append("=" * 80)
    lines.append("*Ciclo de mejora continua del prompt basal (ADR-0048 / #282 / #285).*")
    return "\n".join(lines)


def format_markdown_rules_report(report: RulesViolationReport) -> str:
    """Genera informe en Markdown de métricas de violaciones por ID de regla."""
    lines: List[str] = []
    lines.append("# Informe de Violaciones por ID de Regla")
    lines.append("")
    lines.append(f"- **Sesiones analizadas:** `{report.total_sessions}`")
    lines.append(f"- **Total de violaciones:** `{report.total_violations}`")
    lines.append(f"- **Antipatrones sin mapeo a regla:** `{report.unmapped_antipatterns}`")
    lines.append("")
    lines.append("---")
    lines.append("")

    with_violations = [s for s in report.rule_summaries if s.total_violations > 0]
    without_violations = [s for s in report.rule_summaries if s.total_violations == 0]

    lines.append(f"## Reglas con Violaciones ({len(with_violations)})")
    lines.append("")
    if with_violations:
        lines.append("| ID de Regla | Nivel | Violaciones | Sesiones | AP / P0 | Acción Sugerida |")
        lines.append("| :--- | :---: | :---: | :---: | :---: | :--- |")
        for s in with_violations:
            ratio = f"{s.antipattern_count} / {s.p0_block_count}"
            lines.append(
                f"| `{s.rule_id}` | `{s.level}` | {s.total_violations} | {s.sessions_count} | {ratio} | {s.action_suggestion} |"
            )
    else:
        lines.append("> No se detectaron violaciones de reglas en las sesiones analizadas.")
    lines.append("")

    lines.append(f"## Reglas sin Violaciones ({len(without_violations)})")
    lines.append("")
    lines.append("| ID de Regla | Nivel | Violaciones | Sesiones | AP / P0 | Acción Sugerida |")
    lines.append("| :--- | :---: | :---: | :---: | :---: | :--- |")
    for s in without_violations:
        ratio = f"{s.antipattern_count} / {s.p0_block_count}"
        lines.append(
            f"| `{s.rule_id}` | `{s.level}` | 0 | 0 | {ratio} | {s.action_suggestion} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("*Ciclo de mejora continua del prompt basal (ADR-0048 / #282 / #285).*")
    return "\n".join(lines)


def format_json_rules_report(report: RulesViolationReport) -> str:
    """Genera representación serializada JSON de las métricas de violación por ID de regla."""
    def custom_serializer(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "__dict__"):
            return asdict(obj)
        return str(obj)

    return json.dumps(asdict(report), indent=2, ensure_ascii=False, default=custom_serializer)


def discover_session_files(target: Path, runtime_hint: str = "auto") -> List[Tuple[Any, Path]]:
    """Descubre recursivamente archivos de sesión o transcripción en target."""
    from adapters import ADAPTERS, get_adapter

    if not target.is_dir():
        if target.is_file():
            try:
                ad = get_adapter(target, runtime_hint=runtime_hint)
                return [(ad, target)]
            except Exception:
                return []
        return []

    discovered: List[Tuple[Any, Path]] = []
    seen: Set[Path] = set()

    # 1. Antigravity: transcript.jsonl
    for p in sorted(target.glob("**/transcript.jsonl")):
        res = p.resolve()
        if p.is_file() and res not in seen:
            try:
                ad = get_adapter(p, runtime_hint="antigravity")
                seen.add(res)
                discovered.append((ad, p))
            except Exception:
                pass

    # 2. Claude Code y otros archivos .jsonl / .json
    for ext in ("*.jsonl", "*.json"):
        for p in sorted(target.glob(f"**/{ext}")):
            res = p.resolve()
            if p.is_file() and res not in seen:
                if p.name in ("transcript_full.jsonl", "config.json", "settings.json", "package.json", "hooks.json"):
                    continue
                for ad_cls in ADAPTERS:
                    ad = ad_cls()
                    if ad.detect(p):
                        seen.add(res)
                        discovered.append((ad, p))
                        break

    return discovered



