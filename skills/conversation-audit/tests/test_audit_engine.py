#!/usr/bin/env python3
"""
Pruebas unitarias para el motor de auditoría de conversaciones y detección
del antipatrón TERMINAL_REPL_LOOP en agent-audit.
Ref: Issue #157.
"""

import contextlib
import io
import sys
import unittest
from datetime import datetime
from pathlib import Path

# Asegurar importación de audit_engine y adaptadores
CURRENT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = CURRENT_DIR.parent
SCRIPTS_DIR = SKILL_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from adapters.base import ConversationMetadata, NormalizedStep, NormalizedToolCall
from audit_engine import (
    AuditEngine,
    DetectedAntipattern,
    filter_steps_by_tool,
    format_json_steps,
    format_markdown_steps,
    format_text_steps,
    parse_step_ranges,
)


class TestInlineEvalDetection(unittest.TestCase):
    """Pruebas para AuditEngine.check_inline_eval."""

    def test_positive_eval_commands(self):
        """Verifica que diversos comandos de evaluación en línea sean identificados con su runtime."""
        cases = [
            ('python3 -c "import re; print(1)"', "python3"),
            ("python -c 'print(1)'", "python"),
            ('python3.11 -c "x = 1"', "python3.11"),
            ('python3.12 -c "x = 1"', "python3.12"),
            ('/usr/bin/python3 -c "print(1)"', "python3"),
            ('/usr/local/bin/python -c "print(1)"', "python"),
            ('sudo python3 -c "print(1)"', "python3"),
            ('env FOO=1 python3 -c "print(1)"', "python3"),
            ('python3 -u -c "print(1)"', "python3"),
            ('python3 -O -c "print(1)"', "python3"),
            ('node -e "console.log(1)"', "node"),
            ('node --eval "console.log(1)"', "node"),
            ('/usr/bin/node -e "process.exit(0)"', "node"),
            ("nodejs -e 'console.log(process.version)'", "nodejs"),
            ("ruby -e 'puts 1'", "ruby"),
            ("/usr/bin/ruby -e 'puts 1'", "ruby"),
            ("perl -e 'print 1'", "perl"),
            ("/usr/bin/perl -e 'print 1'", "perl"),
        ]
        for cmd, expected_rt in cases:
            with self.subTest(cmd=cmd):
                is_eval, rt = AuditEngine.check_inline_eval(cmd)
                self.assertTrue(is_eval, f"Fallo al detectar evaluación inline en: {cmd}")
                self.assertEqual(rt, expected_rt)

    def test_negative_standard_cli_commands(self):
        """Verifica que comandos CLI atómicos estándar NO disparen falsos positivos."""
        cases = [
            "python3 script.py",
            "python3 -m unittest discover -s tests",
            "python3 -m pytest tests/",
            "python3 script.py -c config.json",
            "python script.py --eval mode",
            "node server.js",
            "node dist/main.js -e production",
            "ruby app.rb",
            "perl script.pl",
            "git status",
            "git commit -m 'feat: python3 -c implementation'",
            "git diff",
            "echo 'python3 -c \"print(1)\"'",
            "cat test.py",
            "grep -rn 'python3 -c' .",
            "which python3",
            "find . -name '*.py'",
            "pytest tests/",
            "npm test",
            "cargo test",
            "docker run -it alpine sh",
        ]
        for cmd in cases:
            with self.subTest(cmd=cmd):
                is_eval, rt = AuditEngine.check_inline_eval(cmd)
                self.assertFalse(is_eval, f"Falso positivo detectado para comando estándar: {cmd}")
                self.assertEqual(rt, "")


class TestTerminalReplLoopAntipattern(unittest.TestCase):
    """Pruebas para la detección del antipatrón TERMINAL_REPL_LOOP en AuditEngine."""

    def setUp(self):
        self.engine = AuditEngine()
        self.metadata = ConversationMetadata(
            session_id="test-session-157",
            runtime="antigravity",
            source_path="/tmp/transcript.jsonl",
        )

    def _make_step(self, step_index: int, tool_name: str, command: str) -> NormalizedStep:
        return NormalizedStep(
            step_index=step_index,
            source="MODEL",
            step_type="PLANNER_RESPONSE",
            tool_calls=[
                NormalizedToolCall(
                    name=tool_name,
                    args={"CommandLine": command},
                    status="DONE",
                )
            ],
            status="DONE",
        )

    def test_consecutive_inline_eval_loop(self):
        """Detecta bucle de 3 o más evaluaciones consecutivas con argumentos variantes."""
        steps = [
            self._make_step(1, "run_command", 'python3 -c "import re; print(1)"'),
            self._make_step(2, "run_command", 'python3 -c "import re; print(2)"'),
            self._make_step(3, "run_command", 'python3 -c "import re; print(3)"'),
        ]
        report = self.engine.analyze(self.metadata, steps)
        repl_loops = [ap for ap in report.antipatterns if ap.code == "TERMINAL_REPL_LOOP"]
        self.assertEqual(len(repl_loops), 1)
        ap = repl_loops[0]
        self.assertEqual(ap.severity, "ALTA")
        self.assertEqual(ap.title, "Bucle REPL Iterativo en Terminal")
        self.assertEqual(ap.step_index, 3)
        self.assertIn("3 ejecuciones", ap.description)
        self.assertIn("scratch", ap.recommendation)
        self.assertIn("tests unitarios", ap.recommendation)

    def test_high_density_window_loop(self):
        """Detecta alta densidad en ventana corta (ej. 3 evaluaciones en ventana de 5 llamadas)."""
        steps = [
            self._make_step(1, "run_command", 'python3 -c "print(1)"'),
            NormalizedStep(
                step_index=2,
                source="MODEL",
                step_type="PLANNER_RESPONSE",
                tool_calls=[NormalizedToolCall(name="view_file", args={"AbsolutePath": "/tmp/a.py"}, status="DONE")],
            ),
            self._make_step(3, "run_command", 'python3 -c "print(2)"'),
            self._make_step(4, "run_command", 'python3 -c "print(3)"'),
            NormalizedStep(
                step_index=5,
                source="MODEL",
                step_type="PLANNER_RESPONSE",
                tool_calls=[NormalizedToolCall(name="view_file", args={"AbsolutePath": "/tmp/b.py"}, status="DONE")],
            ),
        ]
        report = self.engine.analyze(self.metadata, steps)
        repl_loops = [ap for ap in report.antipatterns if ap.code == "TERMINAL_REPL_LOOP"]
        self.assertEqual(len(repl_loops), 1)
        self.assertEqual(repl_loops[0].step_index, 4)
        self.assertIn("3 ejecuciones", repl_loops[0].description)

    def test_no_false_positive_infrequent_eval(self):
        """Comandos aislados o en cantidad menor al umbral (ej. 2) no disparan el antipatrón."""
        steps = [
            self._make_step(1, "run_command", 'python3 -c "print(1)"'),
            NormalizedStep(
                step_index=2,
                source="MODEL",
                step_type="PLANNER_RESPONSE",
                tool_calls=[NormalizedToolCall(name="view_file", args={"AbsolutePath": "/tmp/a.py"}, status="DONE")],
            ),
            self._make_step(3, "run_command", 'python3 -c "print(2)"'),
        ]
        report = self.engine.analyze(self.metadata, steps)
        repl_loops = [ap for ap in report.antipatterns if ap.code == "TERMINAL_REPL_LOOP"]
        self.assertEqual(len(repl_loops), 0)

    def test_no_false_positive_distant_eval_calls(self):
        """Evaluaciones espaciadas por muchos pasos no forman un bucle REPL."""
        steps = [
            self._make_step(1, "run_command", 'python3 -c "print(1)"'),
        ]
        # 10 pasos normales intercalados
        for i in range(2, 12):
            steps.append(
                NormalizedStep(
                    step_index=i,
                    source="MODEL",
                    step_type="PLANNER_RESPONSE",
                    tool_calls=[NormalizedToolCall(name="view_file", args={"AbsolutePath": f"/tmp/{i}.py"}, status="DONE")],
                )
            )
        steps.append(self._make_step(12, "run_command", 'python3 -c "print(2)"'))
        for i in range(13, 23):
            steps.append(
                NormalizedStep(
                    step_index=i,
                    source="MODEL",
                    step_type="PLANNER_RESPONSE",
                    tool_calls=[NormalizedToolCall(name="view_file", args={"AbsolutePath": f"/tmp/{i}.py"}, status="DONE")],
                )
            )
        steps.append(self._make_step(23, "run_command", 'python3 -c "print(3)"'))

        report = self.engine.analyze(self.metadata, steps)
        repl_loops = [ap for ap in report.antipatterns if ap.code == "TERMINAL_REPL_LOOP"]
        self.assertEqual(len(repl_loops), 0)

    def test_multiple_bursts_detected_separately(self):
        """Múltiples ráfagas separadas generan eventos de antipatrón diferenciados."""
        steps = [
            # Ráfaga 1: 3 llamadas python3
            self._make_step(1, "run_command", 'python3 -c "print(1)"'),
            self._make_step(2, "run_command", 'python3 -c "print(2)"'),
            self._make_step(3, "run_command", 'python3 -c "print(3)"'),
        ]
        # Separador de 10 pasos normales
        for i in range(4, 14):
            steps.append(
                NormalizedStep(
                    step_index=i,
                    source="MODEL",
                    step_type="PLANNER_RESPONSE",
                    tool_calls=[NormalizedToolCall(name="view_file", args={"AbsolutePath": f"/tmp/{i}.py"}, status="DONE")],
                )
            )
        # Ráfaga 2: 3 llamadas node -e
        steps.extend([
            self._make_step(14, "run_command", 'node -e "console.log(1)"'),
            self._make_step(15, "run_command", 'node -e "console.log(2)"'),
            self._make_step(16, "run_command", 'node -e "console.log(3)"'),
        ])

        report = self.engine.analyze(self.metadata, steps)
        repl_loops = [ap for ap in report.antipatterns if ap.code == "TERMINAL_REPL_LOOP"]
        self.assertEqual(len(repl_loops), 2)
        self.assertIn("python3", repl_loops[0].description)
        self.assertIn("node", repl_loops[1].description)

    def test_claude_adapter_bash_compatibility(self):
        """Verifica compatibilidad con el tool 'Bash' y argumento 'command' (Claude Code)."""
        steps = [
            NormalizedStep(
                step_index=1,
                source="MODEL",
                step_type="PLANNER_RESPONSE",
                tool_calls=[
                    NormalizedToolCall(
                        name="Bash",
                        args={"command": 'python3 -c "import os; print(os.name)"'},
                        status="DONE",
                    )
                ],
            ),
            NormalizedStep(
                step_index=2,
                source="MODEL",
                step_type="PLANNER_RESPONSE",
                tool_calls=[
                    NormalizedToolCall(
                        name="Bash",
                        args={"command": 'python3 -c "import sys; print(sys.version)"'},
                        status="DONE",
                    )
                ],
            ),
            NormalizedStep(
                step_index=3,
                source="MODEL",
                step_type="PLANNER_RESPONSE",
                tool_calls=[
                    NormalizedToolCall(
                        name="Bash",
                        args={"command": 'python3 -c "import platform; print(platform.system())"'},
                        status="DONE",
                    )
                ],
            ),
        ]
        report = self.engine.analyze(self.metadata, steps)
        repl_loops = [ap for ap in report.antipatterns if ap.code == "TERMINAL_REPL_LOOP"]
        self.assertEqual(len(repl_loops), 1)
        self.assertEqual(repl_loops[0].step_index, 3)


class TestUnpaginatedFileReadAntipattern(unittest.TestCase):
    """Pruebas para la detección del antipatrón UNPAGINATED_FILE_READ en AuditEngine."""

    def setUp(self):
        self.engine = AuditEngine()
        self.metadata = ConversationMetadata(
            session_id="test-session-178",
            runtime="antigravity",
            source_path="/tmp/transcript.jsonl",
        )

    def _make_step(self, step_index: int, tool_name: str, args: dict) -> NormalizedStep:
        return NormalizedStep(
            step_index=step_index,
            source="MODEL",
            step_type="PLANNER_RESPONSE",
            tool_calls=[
                NormalizedToolCall(
                    name=tool_name,
                    args=args,
                    status="DONE",
                )
            ],
            status="DONE",
        )

    def test_unpaginated_view_file_without_delimiters(self):
        """Detecta llamada a view_file sin delimitadores StartLine/EndLine."""
        steps = [
            self._make_step(1, "view_file", {"AbsolutePath": "/workspace/main.py"}),
        ]
        report = self.engine.analyze(self.metadata, steps)
        unpaginated = [ap for ap in report.antipatterns if ap.code == "UNPAGINATED_FILE_READ"]
        self.assertEqual(len(unpaginated), 1)
        ap = unpaginated[0]
        self.assertEqual(ap.severity, "ALTA")
        self.assertEqual(ap.title, "Lectura No Paginada de Archivo")
        self.assertEqual(ap.step_index, 1)
        self.assertIn("sin especificar delimitadores de paginación", ap.description)
        self.assertIn("grep_search", ap.recommendation)
        self.assertIn("StartLine y EndLine", ap.recommendation)

    def test_partial_delimiters_start_only(self):
        """Detecta llamada a view_file con solo StartLine sin delimitar EndLine."""
        steps = [
            self._make_step(1, "view_file", {"AbsolutePath": "/workspace/main.py", "StartLine": 50}),
        ]
        report = self.engine.analyze(self.metadata, steps)
        unpaginated = [ap for ap in report.antipatterns if ap.code == "UNPAGINATED_FILE_READ"]
        self.assertEqual(len(unpaginated), 1)
        ap = unpaginated[0]
        self.assertIn("sin especificar EndLine", ap.description)

    def test_partial_delimiters_end_only(self):
        """Detecta llamada a view_file con solo EndLine sin delimitar StartLine."""
        steps = [
            self._make_step(1, "view_file", {"AbsolutePath": "/workspace/main.py", "EndLine": 300}),
        ]
        report = self.engine.analyze(self.metadata, steps)
        unpaginated = [ap for ap in report.antipatterns if ap.code == "UNPAGINATED_FILE_READ"]
        self.assertEqual(len(unpaginated), 1)
        ap = unpaginated[0]
        self.assertIn("sin especificar StartLine", ap.description)

    def test_excessive_line_range_detected(self):
        """Detecta rango de líneas que supera el umbral configurable (350 - 1 = 349 > 200)."""
        steps = [
            self._make_step(1, "view_file", {"AbsolutePath": "/workspace/main.py", "StartLine": 1, "EndLine": 350}),
        ]
        report = self.engine.analyze(self.metadata, steps)
        unpaginated = [ap for ap in report.antipatterns if ap.code == "UNPAGINATED_FILE_READ"]
        self.assertEqual(len(unpaginated), 1)
        ap = unpaginated[0]
        self.assertEqual(ap.severity, "ALTA")
        self.assertIn("rango de 349 líneas", ap.description)
        self.assertIn("superando el umbral configurable de 200 líneas", ap.description)

    def test_acceptable_line_range_not_flagged(self):
        """Lecturas dentro del umbral (<= 200 líneas) no disparan el antipatrón."""
        steps = [
            self._make_step(1, "view_file", {"AbsolutePath": "/workspace/main.py", "StartLine": 1, "EndLine": 200}),
            self._make_step(2, "view_file", {"AbsolutePath": "/workspace/main.py", "StartLine": 50, "EndLine": 120}),
        ]
        report = self.engine.analyze(self.metadata, steps)
        unpaginated = [ap for ap in report.antipatterns if ap.code == "UNPAGINATED_FILE_READ"]
        self.assertEqual(len(unpaginated), 0)

    def test_exact_threshold_boundary(self):
        """Diferencia de exactamente 200 no dispara; 201 sí dispara."""
        # StartLine=1, EndLine=201 -> diff = 200 <= 200 (OK)
        steps_ok = [
            self._make_step(1, "view_file", {"AbsolutePath": "/workspace/main.py", "StartLine": 1, "EndLine": 201}),
        ]
        report_ok = self.engine.analyze(self.metadata, steps_ok)
        self.assertEqual(len([ap for ap in report_ok.antipatterns if ap.code == "UNPAGINATED_FILE_READ"]), 0)

        # StartLine=1, EndLine=202 -> diff = 201 > 200 (Antipatrón)
        steps_over = [
            self._make_step(1, "view_file", {"AbsolutePath": "/workspace/main.py", "StartLine": 1, "EndLine": 202}),
        ]
        report_over = self.engine.analyze(self.metadata, steps_over)
        self.assertEqual(len([ap for ap in report_over.antipatterns if ap.code == "UNPAGINATED_FILE_READ"]), 1)

    def test_custom_configurable_threshold(self):
        """Verifica que el umbral de líneas sea configurable a través de file_lines_threshold."""
        custom_engine = AuditEngine(file_lines_threshold=50)
        steps = [
            self._make_step(1, "view_file", {"AbsolutePath": "/workspace/main.py", "StartLine": 1, "EndLine": 80}),
        ]
        report = custom_engine.analyze(self.metadata, steps)
        unpaginated = [ap for ap in report.antipatterns if ap.code == "UNPAGINATED_FILE_READ"]
        self.assertEqual(len(unpaginated), 1)
        self.assertIn("superando el umbral configurable de 50 líneas", unpaginated[0].description)

    def test_claude_adapter_view_range(self):
        """Verifica compatibilidad con el formato view_range de Claude Code."""
        steps_over = [
            self._make_step(1, "View", {"file_path": "/workspace/main.ts", "view_range": [1, 500]}),
        ]
        report_over = self.engine.analyze(self.metadata, steps_over)
        self.assertEqual(len([ap for ap in report_over.antipatterns if ap.code == "UNPAGINATED_FILE_READ"]), 1)

        steps_ok = [
            self._make_step(1, "View", {"file_path": "/workspace/main.ts", "view_range": [1, 100]}),
        ]
        report_ok = self.engine.analyze(self.metadata, steps_ok)
        self.assertEqual(len([ap for ap in report_ok.antipatterns if ap.code == "UNPAGINATED_FILE_READ"]), 0)

    def test_binary_files_ignored(self):
        """Archivos binarios o imágenes (ej. .png, .jpg, .pdf) no requieren paginación y se ignoran."""
        steps = [
            self._make_step(1, "view_file", {"AbsolutePath": "/workspace/assets/logo.png"}),
            self._make_step(2, "view_file", {"AbsolutePath": "/workspace/docs/manual.pdf"}),
            self._make_step(3, "View", {"file_path": "/workspace/assets/photo.jpg"}),
        ]
        report = self.engine.analyze(self.metadata, steps)
        unpaginated = [ap for ap in report.antipatterns if ap.code == "UNPAGINATED_FILE_READ"]
        self.assertEqual(len(unpaginated), 0)

    def test_non_read_tools_ignored(self):
        """Otras herramientas sin función de lectura de archivos no son evaluadas."""
        steps = [
            self._make_step(1, "run_command", {"CommandLine": "ls -la"}),
            self._make_step(2, "grep_search", {"Query": "pattern", "SearchPath": "/workspace"}),
        ]
        report = self.engine.analyze(self.metadata, steps)
        unpaginated = [ap for ap in report.antipatterns if ap.code == "UNPAGINATED_FILE_READ"]
        self.assertEqual(len(unpaginated), 0)


class TestAgentAuditCli(unittest.TestCase):
    """Pruebas de integración E2E para el CLI agent-audit con TERMINAL_REPL_LOOP."""

    @classmethod
    def setUpClass(cls):
        import importlib.machinery
        import importlib.util
        cli_path = SKILL_ROOT / "bin" / "agent-audit"
        loader = importlib.machinery.SourceFileLoader("agent_audit_cli", str(cli_path))
        spec = importlib.util.spec_from_loader("agent_audit_cli", loader)
        cls.agent_audit = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.agent_audit)

    def test_cli_detects_repl_loop_and_fails_on_antipattern(self):
        import contextlib
        import io
        import json
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            transcript_file = Path(tmpdir) / "transcript.jsonl"
            lines = [
                {"step_index": 0, "source": "USER", "type": "USER_INPUT", "content": "test"},
                {
                    "step_index": 1,
                    "source": "MODEL",
                    "type": "PLANNER_RESPONSE",
                    "tool_calls": [{"name": "run_command", "args": {"CommandLine": 'python3 -c "print(1)"'}}],
                },
                {
                    "step_index": 2,
                    "source": "MODEL",
                    "type": "PLANNER_RESPONSE",
                    "tool_calls": [{"name": "run_command", "args": {"CommandLine": 'python3 -c "print(2)"'}}],
                },
                {
                    "step_index": 3,
                    "source": "MODEL",
                    "type": "PLANNER_RESPONSE",
                    "tool_calls": [{"name": "run_command", "args": {"CommandLine": 'python3 -c "print(3)"'}}],
                },
            ]
            with open(transcript_file, "w", encoding="utf-8") as f:
                for line in lines:
                    f.write(json.dumps(line) + "\n")

            test_argv = ["agent-audit", str(transcript_file), "--fail-on-antipattern"]
            buf_out, buf_err = io.StringIO(), io.StringIO()
            with patch("sys.argv", test_argv):
                with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                    code = self.agent_audit.main()
                self.assertEqual(code, 2)
                self.assertIn("TERMINAL_REPL_LOOP", buf_out.getvalue())

    def test_cli_detects_unpaginated_file_read_and_threshold_flag(self):
        """El CLI detecta UNPAGINATED_FILE_READ y respeta --threshold-file-lines."""
        import contextlib
        import io
        import json
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            transcript_file = Path(tmpdir) / "transcript.jsonl"
            lines = [
                {"step_index": 0, "source": "USER", "type": "USER_INPUT", "content": "test"},
                {
                    "step_index": 1,
                    "source": "MODEL",
                    "type": "PLANNER_RESPONSE",
                    "tool_calls": [{"name": "view_file", "args": {"AbsolutePath": "/workspace/main.py", "StartLine": 1, "EndLine": 80}}],
                },
            ]
            with open(transcript_file, "w", encoding="utf-8") as f:
                for line in lines:
                    f.write(json.dumps(line) + "\n")

            # Con umbral default (200), 80 líneas no dispara fallo
            test_argv_default = ["agent-audit", str(transcript_file), "--fail-on-antipattern"]
            buf_out_default, buf_err_default = io.StringIO(), io.StringIO()
            with patch("sys.argv", test_argv_default):
                with contextlib.redirect_stdout(buf_out_default), contextlib.redirect_stderr(buf_err_default):
                    code = self.agent_audit.main()
                self.assertEqual(code, 0)
                self.assertIn("INFORME DE AUDITORÍA TÉCNICA", buf_out_default.getvalue())

            # Con umbral --threshold-file-lines 50, 80 líneas dispara antipatrón ALTA -> código 2
            test_argv_custom = ["agent-audit", str(transcript_file), "--threshold-file-lines", "50", "--fail-on-antipattern"]
            buf_out_custom, buf_err_custom = io.StringIO(), io.StringIO()
            with patch("sys.argv", test_argv_custom):
                with contextlib.redirect_stdout(buf_out_custom), contextlib.redirect_stderr(buf_err_custom):
                    code = self.agent_audit.main()
                self.assertEqual(code, 2)
                self.assertIn("UNPAGINATED_FILE_READ", buf_out_custom.getvalue())


class TestStepInspectionAndFailedSteps(unittest.TestCase):
    """Pruebas unitarias para las funcionalidades quirúrgicas --inspect-step y --failed-steps."""

    def setUp(self):
        self.step_with_error = NormalizedStep(
            step_index=5,
            source="MODEL",
            step_type="PLANNER_RESPONSE",
            created_at=datetime(2026, 10, 29, 12, 0, 0),
            duration_seconds=3.5,
            thinking="Analizando si el comando existe...",
            content="Voy a ejecutar el comando.",
            tool_calls=[
                NormalizedToolCall(
                    name="run_command",
                    args={"CommandLine": "git-prune-gone --sync"},
                    tool_action="Pruning branches",
                    tool_summary="Prune branches",
                    status="ERROR",
                    error="Command not found: git-prune-gone",
                )
            ],
            status="ERROR",
        )

        self.step_ok = NormalizedStep(
            step_index=1,
            source="MODEL",
            step_type="PLANNER_RESPONSE",
            created_at=datetime(2026, 10, 29, 11, 59, 0),
            duration_seconds=1.2,
            content="Lectura de estado completada.",
            tool_calls=[
                NormalizedToolCall(
                    name="run_command",
                    args={"CommandLine": "git status"},
                    tool_action="Checking git status",
                    status="DONE",
                    raw_output="On branch main\nnothing to commit",
                )
            ],
            status="DONE",
        )

    def test_format_step_text_markdown_json(self):
        from audit_engine import format_json_step, format_markdown_step, format_text_step
        import json

        # Texto
        text_out = format_text_step(self.step_with_error)
        self.assertIn("DETALLE DE PASO 5", text_out)
        self.assertIn("run_command", text_out)
        self.assertIn("Command not found: git-prune-gone", text_out)
        self.assertIn("PENSAMIENTO / THINKING:", text_out)

        # Markdown
        md_out = format_markdown_step(self.step_with_error)
        self.assertIn("# Detalle del Paso `5`", md_out)
        self.assertIn("`run_command`", md_out)
        self.assertIn("Command not found: git-prune-gone", md_out)
        self.assertIn("## Pensamiento (Thinking)", md_out)

        # JSON
        json_out = format_json_step(self.step_with_error)
        data = json.loads(json_out)
        self.assertEqual(data["step_index"], 5)
        self.assertEqual(data["status"], "ERROR")
        self.assertEqual(len(data["tool_calls"]), 1)
        self.assertEqual(data["tool_calls"][0]["error"], "Command not found: git-prune-gone")

    def test_format_step_truncates_large_fields(self):
        from audit_engine import format_markdown_step, format_text_step

        huge_step = NormalizedStep(
            step_index=10,
            source="MODEL",
            step_type="PLANNER_RESPONSE",
            content="A" * 3000,
            tool_calls=[
                NormalizedToolCall(
                    name="run_command",
                    args={"CommandLine": "cat huge_file.log"},
                    raw_output="B" * 5000,
                    status="DONE",
                )
            ],
            status="DONE",
        )
        text_out = format_text_step(huge_step, max_content_chars=500)
        self.assertIn("[Salida truncada: se muestran 500 de 5000 caracteres]", text_out)
        self.assertIn("[Salida truncada: se muestran 500 de 3000 caracteres]", text_out)

        md_out = format_markdown_step(huge_step, max_content_chars=500)
        self.assertIn("[Salida truncada: se muestran 500 de 5000 caracteres]", md_out)

    def test_get_failed_steps_filtering_and_deduplication(self):
        from audit_engine import get_failed_steps

        # Paso 1: OK
        # Paso 2: Tool call con ERROR
        # Paso 3: GENERIC output step con el mismo error duplicado (Antigravity)
        steps = [
            self.step_ok,
            self.step_with_error,
            NormalizedStep(
                step_index=6,
                source="SYSTEM",
                step_type="GENERIC",
                content="Command not found: git-prune-gone",
                status="ERROR",
            ),
        ]
        failed = get_failed_steps(steps)
        # Debe incluir solo el paso 5 (el tool call con error), deduplicando el paso 6
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].step_index, 5)

    def test_get_failed_steps_dedup_parallel_tool_calls(self):
        from audit_engine import get_failed_steps

        # Paso 1: Modelo llama a 2 herramientas en paralelo (tool_1 ok, tool_2 error)
        step_model = NormalizedStep(
            step_index=1,
            source="MODEL",
            step_type="PLANNER_RESPONSE",
            status="DONE",
            tool_calls=[
                NormalizedToolCall(
                    name="view_file",
                    call_id="call_01",
                    status="DONE",
                    raw_output="content of file",
                ),
                NormalizedToolCall(
                    name="run_command",
                    call_id="call_02",
                    status="ERROR",
                    error="command failed with exit code 1",
                ),
            ],
        )

        # Paso 2: TOOL_OUTPUT con las respuestas unificadas (s.content une ambas)
        # s.content no coincide con ningún tc.error individual
        step_output = NormalizedStep(
            step_index=2,
            source="SYSTEM",
            step_type="TOOL_OUTPUT",
            content="content of file\ncommand failed with exit code 1",
            status="ERROR",
            raw={
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_01",
                        "content": "content of file",
                        "is_error": False,
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_02",
                        "content": "command failed with exit code 1",
                        "is_error": True,
                    },
                ],
            },
        )

        steps = [step_model, step_output]
        failed = get_failed_steps(steps)
        # Debe deduplicar por call_id/tool_use_id y retornar solo el paso 1
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].step_index, 1)

    def test_get_failed_steps_dedup_list_content_tool_result(self):
        from audit_engine import get_failed_steps

        step_model = NormalizedStep(
            step_index=3,
            source="MODEL",
            step_type="PLANNER_RESPONSE",
            status="DONE",
            tool_calls=[
                NormalizedToolCall(
                    name="run_command",
                    call_id="call_list_01",
                    status="ERROR",
                    error="Error text from block\nSecond line",
                ),
            ],
        )

        step_output = NormalizedStep(
            step_index=4,
            source="SYSTEM",
            step_type="TOOL_OUTPUT",
            content="Error text from block\nSecond line",
            status="ERROR",
            raw={
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_list_01",
                        "content": [
                            {"type": "text", "text": "Error text from block"},
                            {"type": "text", "text": "Second line"},
                        ],
                        "is_error": True,
                    },
                ],
            },
        )

        steps = [step_model, step_output]
        failed = get_failed_steps(steps)
        # Deduplica basándose en call_id/tool_use_id
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].step_index, 3)

    def test_format_failed_steps_text_markdown_json(self):
        from audit_engine import (
            format_json_failed_steps,
            format_markdown_failed_steps,
            format_text_failed_steps,
        )
        import json

        failed_steps = [self.step_with_error]

        # Texto con fallos
        txt_out = format_text_failed_steps(failed_steps)
        self.assertIn("Total de pasos con errores: 1", txt_out)
        self.assertIn("Paso 5", txt_out)
        self.assertIn("Command not found: git-prune-gone", txt_out)

        # Markdown con fallos
        md_out = format_markdown_failed_steps(failed_steps)
        self.assertIn("Total de pasos con errores detectados: **1**", md_out)
        self.assertIn("`run_command`", md_out)

        # JSON con fallos
        json_out = format_json_failed_steps(failed_steps)
        data = json.loads(json_out)
        self.assertEqual(data["total_failed_steps"], 1)
        self.assertEqual(len(data["failed_steps"]), 1)
        self.assertEqual(data["failed_steps"][0]["failed_tools"][0]["name"], "run_command")

        # Texto sin fallos
        clean_txt = format_text_failed_steps([])
        self.assertIn("No se registraron pasos con errores de herramientas", clean_txt)

        # Markdown sin fallos
        clean_md = format_markdown_failed_steps([])
        self.assertIn("No se registraron pasos con errores de herramientas", clean_md)

    def test_cli_inspect_step_flag(self):
        import json
        import tempfile
        from unittest.mock import patch
        import importlib.machinery
        import importlib.util

        cli_path = SKILL_ROOT / "bin" / "agent-audit"
        loader = importlib.machinery.SourceFileLoader("agent_audit_cli_test", str(cli_path))
        spec = importlib.util.spec_from_loader("agent_audit_cli_test", loader)
        cli_mod = importlib.util.module_from_spec(spec)
        loader.exec_module(cli_mod)

        with tempfile.TemporaryDirectory() as tmpdir:
            transcript_file = Path(tmpdir) / "transcript.jsonl"
            lines = [
                {"step_index": 0, "source": "USER", "type": "USER_INPUT", "content": "hola"},
                {
                    "step_index": 1,
                    "source": "MODEL",
                    "type": "PLANNER_RESPONSE",
                    "tool_calls": [{"name": "run_command", "args": {"CommandLine": "ls"}}],
                },
            ]
            with open(transcript_file, "w", encoding="utf-8") as f:
                for line in lines:
                    f.write(json.dumps(line) + "\n")

            # Paso existente (0 y 1)
            buf_out1, buf_err1 = io.StringIO(), io.StringIO()
            with patch("sys.argv", ["agent-audit", str(transcript_file), "--inspect-step", "1"]):
                with contextlib.redirect_stdout(buf_out1), contextlib.redirect_stderr(buf_err1):
                    code = cli_mod.main()
                self.assertEqual(code, 0)
                self.assertIn("DETALLE DE PASO 1", buf_out1.getvalue())

            # Paso inexistente (999) -> código 1
            buf_out999, buf_err999 = io.StringIO(), io.StringIO()
            with patch("sys.argv", ["agent-audit", str(transcript_file), "--inspect-step", "999"]):
                with contextlib.redirect_stdout(buf_out999), contextlib.redirect_stderr(buf_err999):
                    code = cli_mod.main()
                self.assertEqual(code, 1)
                self.assertIn("No se encontró el paso 999", buf_err999.getvalue())

    def test_cli_failed_steps_flag(self):
        import contextlib
        import io
        import json
        import tempfile
        from unittest.mock import patch
        import importlib.machinery
        import importlib.util

        cli_path = SKILL_ROOT / "bin" / "agent-audit"
        loader = importlib.machinery.SourceFileLoader("agent_audit_cli_test_failed", str(cli_path))
        spec = importlib.util.spec_from_loader("agent_audit_cli_test_failed", loader)
        cli_mod = importlib.util.module_from_spec(spec)
        loader.exec_module(cli_mod)

        with tempfile.TemporaryDirectory() as tmpdir:
            transcript_file = Path(tmpdir) / "transcript.jsonl"
            lines = [
                {"step_index": 0, "source": "USER", "type": "USER_INPUT", "content": "hola"},
                {
                    "step_index": 1,
                    "source": "MODEL",
                    "type": "PLANNER_RESPONSE",
                    "status": "ERROR",
                    "tool_calls": [{"name": "run_command", "args": {"CommandLine": "false"}}],
                },
                {
                    "step_index": 2,
                    "source": "SYSTEM",
                    "type": "GENERIC",
                    "status": "ERROR",
                    "content": "The command exited with code 1",
                },
            ]
            with open(transcript_file, "w", encoding="utf-8") as f:
                for line in lines:
                    f.write(json.dumps(line) + "\n")

            buf_out, buf_err = io.StringIO(), io.StringIO()
            with patch("sys.argv", ["agent-audit", str(transcript_file), "--failed-steps", "--format", "json"]):
                with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                    code = cli_mod.main()
                self.assertEqual(code, 0)
                res_data = json.loads(buf_out.getvalue())
                self.assertEqual(res_data.get("total_failed_steps"), 1)


class TestSubagentPromptConsistency(unittest.TestCase):
    """Pruebas de consistencia para el modo de auditoría en background vía subagente."""

    def test_subagent_prompt_template_exists_and_valid(self):
        template_file = SKILL_ROOT / "templates" / "subagent_prompt.md"
        self.assertTrue(template_file.is_file(), f"No se encontró {template_file}")
        content = template_file.read_text(encoding="utf-8")
        self.assertIn("agent-audit {{TARGET_SESSION}} --format markdown", content)
        self.assertIn("CONSECUTIVE_TOOL_ERRORS", content)
        self.assertIn("REPETITIVE_TOOL_LOOP", content)
        self.assertIn("TERMINAL_REPL_LOOP", content)
        self.assertIn("CONTEXT_TRUNCATION", content)
        self.assertIn("UNPAGINATED_FILE_READ", content)
        self.assertIn("Diagnóstico Ejecutivo Consolidado", content)
        self.assertIn("Veredicto de Antipatrones", content)

    def test_subagent_prompt_contains_strict_shielding_rules(self):
        """Verifica que el prompt del subagente prohíba comandos ajenos y delimite presupuesto."""
        template_file = SKILL_ROOT / "templates" / "subagent_prompt.md"
        content = template_file.read_text(encoding="utf-8")
        # Prohibición explícita de herramientas no autorizadas
        self.assertIn("PROHIBIDO TAXATIVAMENTE", content)
        self.assertIn("python3", content)
        self.assertIn("bash", content)
        self.assertIn("grep", content)
        # Presupuesto acotado
        self.assertIn("Tool Budget", content)
        self.assertIn("2 a 3 invocaciones de herramientas", content)
        self.assertIn("--failed-steps", content)
        self.assertIn("--inspect-step", content)
        # Disyuntor autónomo
        self.assertIn("Stop & Synthesize", content)
        self.assertIn("Circuit Breaker", content)

    def test_skill_docs_cover_subagent_mode_and_shielding(self):
        skill_file = SKILL_ROOT / "SKILL.md"
        content = skill_file.read_text(encoding="utf-8")
        self.assertIn("## 5. Modo de Auditoría Desacoplada en Background vía Subagente", content)
        self.assertIn("templates/subagent_prompt.md", content)
        self.assertIn('"TypeName": "self"', content)
        self.assertIn('"Model": "flash"', content)
        self.assertIn("--inspect-step <N>", content)
        self.assertIn("--failed-steps", content)
        self.assertIn("Stop & Synthesize", content)
        self.assertIn("máximo 3 tool calls", content)

    def test_markdown_report_matches_subagent_expectations(self):
        from audit_engine import AuditReport, format_markdown_report

        metadata = ConversationMetadata(
            session_id="test-session-123",
            title="Test Session",
            runtime="antigravity",
            source_path="/tmp/test",
            start_time=datetime(2026, 10, 29, 10, 0, 0),
            end_time=datetime(2026, 10, 29, 10, 5, 0),
        )
        report = AuditReport(
            metadata=metadata,
            total_steps=10,
            user_turns=2,
            model_turns=5,
            system_steps=3,
            wall_clock_seconds=300.0,
            avg_step_latency_seconds=30.0,
            max_step_latency_seconds=45.0,
        )
        md = format_markdown_report(report)
        self.assertIn("## 1. Resumen Ejecutivo", md)
        self.assertIn("## 2. Desglose de Herramientas", md)
        self.assertIn("## 3. Pasos de Mayor Latencia", md)
        self.assertIn("## 4. Antipatrones y Anomalías Detectadas", md)


class TestStepRangesAndToolFiltering(unittest.TestCase):
    """Pruebas unitarias para la inspección de rangos de pasos y filtros avanzados."""

    def test_parse_step_ranges_valid(self):
        """Verifica el parsing de números simples, rangos (guión y doble punto), listas y combinaciones."""
        self.assertEqual(parse_step_ranges("5"), [5])
        self.assertEqual(parse_step_ranges("0"), [0])
        self.assertEqual(parse_step_ranges("87-90"), [87, 88, 89, 90])
        self.assertEqual(parse_step_ranges("87..90"), [87, 88, 89, 90])
        self.assertEqual(parse_step_ranges("87,88,92,100"), [87, 88, 92, 100])
        self.assertEqual(parse_step_ranges("1-5,87-90,105"), [1, 2, 3, 4, 5, 87, 88, 89, 90, 105])
        self.assertEqual(parse_step_ranges("1..3, 87..88, 90"), [1, 2, 3, 87, 88, 90])
        self.assertEqual(parse_step_ranges("0-2, 5"), [0, 1, 2, 5])
        # Deduplicación y ordenamiento
        self.assertEqual(parse_step_ranges("1-3, 2, 3-4"), [1, 2, 3, 4])
        self.assertEqual(parse_step_ranges("87-87"), [87])

    def test_parse_step_ranges_invalid(self):
        """Verifica que sintaxis inválidas o rangos invertidos disparen ValueError."""
        invalid_cases = [
            "",
            "   ",
            ",",
            "abc",
            "1-a",
            "1..z",
            "10-5",
            "10..5",
            "-5",
            "5-",
            "1-2-3",
            "1..2..3",
        ]
        for expr in invalid_cases:
            with self.subTest(expr=expr):
                with self.assertRaises(ValueError):
                    parse_step_ranges(expr)

    def test_filter_steps_by_tool(self):
        """Verifica el filtrado de pasos por herramienta exacta, normalizada o MCP."""
        step1 = NormalizedStep(
            step_index=1,
            source="MODEL",
            step_type="PLANNER_RESPONSE",
            tool_calls=[NormalizedToolCall(name="run_command", args={"CommandLine": "ls"})],
        )
        step2 = NormalizedStep(
            step_index=2,
            source="MODEL",
            step_type="PLANNER_RESPONSE",
            tool_calls=[NormalizedToolCall(name="view_file", args={"AbsolutePath": "/a"})],
        )
        step3 = NormalizedStep(
            step_index=3,
            source="MODEL",
            step_type="PLANNER_RESPONSE",
            tool_calls=[
                NormalizedToolCall(name="run_command", args={"CommandLine": "pwd"}),
                NormalizedToolCall(name="mcp_gemini-api-docs_gemini_search_docs", args={"query": "test"}),
            ],
        )
        steps = [step1, step2, step3]

        # run_command -> pasos 1 y 3
        res_rc = filter_steps_by_tool(steps, "run_command")
        self.assertEqual([s.step_index for s in res_rc], [1, 3])

        # Case-insensitive
        res_rc_upper = filter_steps_by_tool(steps, "RUN_COMMAND")
        self.assertEqual([s.step_index for s in res_rc_upper], [1, 3])

        # view_file -> paso 2
        res_vf = filter_steps_by_tool(steps, "view_file")
        self.assertEqual([s.step_index for s in res_vf], [2])

        # MCP tool con sufijo normalizado
        res_mcp = filter_steps_by_tool(steps, "gemini_search_docs")
        self.assertEqual([s.step_index for s in res_mcp], [3])

        # Herramienta inexistente -> vacío
        res_none = filter_steps_by_tool(steps, "nonexistent_tool")
        self.assertEqual(res_none, [])

        # Herramienta vacía -> devuelve todos
        self.assertEqual(filter_steps_by_tool(steps, ""), steps)

    def test_format_steps_text_markdown_json(self):
        """Verifica la generación de formatos text, markdown y json para múltiples pasos."""
        import json
        from audit_engine import format_json_step, format_markdown_step, format_text_step

        step1 = NormalizedStep(
            step_index=1,
            source="MODEL",
            step_type="PLANNER_RESPONSE",
            content="Paso 1 completado",
            tool_calls=[
                NormalizedToolCall(
                    name="run_command",
                    args={"CommandLine": "git status"},
                    status="DONE",
                    raw_output="clean",
                )
            ],
            status="DONE",
        )
        step2 = NormalizedStep(
            step_index=2,
            source="MODEL",
            step_type="PLANNER_RESPONSE",
            content="Paso 2 completado",
            tool_calls=[
                NormalizedToolCall(
                    name="replace_file_content",
                    args={"TargetFile": "/foo.py"},
                    status="DONE",
                )
            ],
            status="DONE",
        )
        steps = [step1, step2]

        # Text
        txt = format_text_steps(steps)
        self.assertIn("INSPECCIÓN DE PASOS (2 pasos)", txt)
        self.assertIn("Pasos incluidos : 1, 2", txt)
        self.assertIn("DETALLE DE PASO 1", txt)
        self.assertIn("DETALLE DE PASO 2", txt)

        # Markdown
        md = format_markdown_steps(steps)
        self.assertIn("# Inspección de Pasos (2 pasos)", md)
        self.assertIn("- **Pasos incluidos:** `1, 2`", md)
        self.assertIn("## Detalle del Paso `1`", md)
        self.assertIn("## Detalle del Paso `2`", md)
        self.assertIn("`agent-audit --inspect-steps`", md)

        # JSON
        js = format_json_steps(steps)
        data = json.loads(js)
        self.assertEqual(data["total_steps"], 2)
        self.assertEqual(len(data["steps"]), 2)
        self.assertEqual(data["steps"][0]["step_index"], 1)
        self.assertEqual(data["steps"][1]["step_index"], 2)

        # Invocación polimórfica (pasando lista a format_*_step)
        self.assertEqual(format_text_step(steps), txt)
        self.assertEqual(format_markdown_step(steps), md)
        self.assertEqual(format_json_step(steps), js)

        # Manejo de listas vacías
        self.assertIn("No se encontraron pasos", format_text_steps([]))
        self.assertIn("No se encontraron pasos", format_markdown_steps([]))
        empty_js = json.loads(format_json_steps([]))
        self.assertEqual(empty_js["total_steps"], 0)
        self.assertEqual(empty_js["steps"], [])

    def test_cli_inspect_steps_and_filter_tool(self):
        """Verifica la ejecución de agent-audit con --inspect-steps y --filter-tool."""
        import json
        import tempfile
        from unittest.mock import patch
        import importlib.machinery
        import importlib.util

        cli_path = SKILL_ROOT / "bin" / "agent-audit"
        loader = importlib.machinery.SourceFileLoader("agent_audit_cli_steps_test", str(cli_path))
        spec = importlib.util.spec_from_loader("agent_audit_cli_steps_test", loader)
        cli_mod = importlib.util.module_from_spec(spec)
        loader.exec_module(cli_mod)

        with tempfile.TemporaryDirectory() as tmpdir:
            transcript_file = Path(tmpdir) / "transcript.jsonl"
            lines = [
                {"step_index": 0, "source": "USER", "type": "USER_INPUT", "content": "iniciar"},
                {
                    "step_index": 1,
                    "source": "MODEL",
                    "type": "PLANNER_RESPONSE",
                    "tool_calls": [{"name": "run_command", "args": {"CommandLine": "ls"}}],
                },
                {
                    "step_index": 2,
                    "source": "MODEL",
                    "type": "PLANNER_RESPONSE",
                    "tool_calls": [{"name": "view_file", "args": {"AbsolutePath": "/a"}}],
                },
                {
                    "step_index": 3,
                    "source": "MODEL",
                    "type": "PLANNER_RESPONSE",
                    "tool_calls": [{"name": "run_command", "args": {"CommandLine": "pwd"}}],
                },
            ]
            with open(transcript_file, "w", encoding="utf-8") as f:
                for line in lines:
                    f.write(json.dumps(line) + "\n")

            import contextlib
            import io

            # 1. Rango numérico con --inspect-steps
            buf_out1, buf_err1 = io.StringIO(), io.StringIO()
            with patch("sys.argv", ["agent-audit", str(transcript_file), "--inspect-steps", "1-2"]):
                with contextlib.redirect_stdout(buf_out1), contextlib.redirect_stderr(buf_err1):
                    code = cli_mod.main()
                self.assertEqual(code, 0)
                self.assertIn("DETALLE DE PASO 1", buf_out1.getvalue())
                self.assertIn("DETALLE DE PASO 2", buf_out1.getvalue())

            # 2. Rango con sintaxis doble punto '..'
            buf_out2, buf_err2 = io.StringIO(), io.StringIO()
            with patch("sys.argv", ["agent-audit", str(transcript_file), "--inspect-steps", "1..3", "--format", "json"]):
                with contextlib.redirect_stdout(buf_out2), contextlib.redirect_stderr(buf_err2):
                    code = cli_mod.main()
                self.assertEqual(code, 0)
                res_json = json.loads(buf_out2.getvalue())
                self.assertIn("steps", res_json)
                self.assertEqual(len(res_json["steps"]), 3)

            # 3. Flexibilidad de --inspect-step aceptando rangos
            buf_out3, buf_err3 = io.StringIO(), io.StringIO()
            with patch("sys.argv", ["agent-audit", str(transcript_file), "--inspect-step", "1-2"]):
                with contextlib.redirect_stdout(buf_out3), contextlib.redirect_stderr(buf_err3):
                    code = cli_mod.main()
                self.assertEqual(code, 0)
                self.assertIn("DETALLE DE PASO 1", buf_out3.getvalue())

            # 4. Combinación de rango con --filter-tool
            buf_out4, buf_err4 = io.StringIO(), io.StringIO()
            with patch("sys.argv", ["agent-audit", str(transcript_file), "--inspect-steps", "1-3", "--filter-tool", "run_command"]):
                with contextlib.redirect_stdout(buf_out4), contextlib.redirect_stderr(buf_err4):
                    code = cli_mod.main()
                self.assertEqual(code, 0)
                self.assertIn("run_command", buf_out4.getvalue())

            # 5. --filter-tool aislado
            buf_out5, buf_err5 = io.StringIO(), io.StringIO()
            with patch("sys.argv", ["agent-audit", str(transcript_file), "--filter-tool", "run_command", "--format", "markdown"]):
                with contextlib.redirect_stdout(buf_out5), contextlib.redirect_stderr(buf_err5):
                    code = cli_mod.main()
                self.assertEqual(code, 0)
                self.assertIn("run_command", buf_out5.getvalue())

            # 6. --filter-tool sin coincidencias -> salida 1
            buf_out6, buf_err6 = io.StringIO(), io.StringIO()
            with patch("sys.argv", ["agent-audit", str(transcript_file), "--filter-tool", "nonexistent"]):
                with contextlib.redirect_stdout(buf_out6), contextlib.redirect_stderr(buf_err6):
                    code = cli_mod.main()
                self.assertEqual(code, 1)

            # 7. Sintaxis de rango inválida -> salida 1
            buf_out7, buf_err7 = io.StringIO(), io.StringIO()
            with patch("sys.argv", ["agent-audit", str(transcript_file), "--inspect-steps", "invalid-range"]):
                with contextlib.redirect_stdout(buf_out7), contextlib.redirect_stderr(buf_err7):
                    code = cli_mod.main()
                self.assertEqual(code, 1)

    def test_read_only_loop_detection(self):
        engine = AuditEngine()
        meta = ConversationMetadata(session_id="test-ro", runtime="antigravity", source_path=Path("/dummy"))
        steps = [
            NormalizedStep(step_index=0, source="USER", step_type="USER_INPUT", content="start"),
            NormalizedStep(step_index=1, source="MODEL", step_type="PLANNER_RESPONSE", tool_calls=[NormalizedToolCall(name="view_file", args={"AbsolutePath": "/a.lua", "StartLine": 1, "EndLine": 50})]),
            NormalizedStep(step_index=2, source="MODEL", step_type="PLANNER_RESPONSE", tool_calls=[NormalizedToolCall(name="view_file", args={"AbsolutePath": "/b.lua", "StartLine": 1, "EndLine": 50})]),
            NormalizedStep(step_index=3, source="MODEL", step_type="PLANNER_RESPONSE", tool_calls=[NormalizedToolCall(name="grep_search", args={"Query": "foo", "SearchPath": "/c.lua"})]),
            NormalizedStep(step_index=4, source="MODEL", step_type="PLANNER_RESPONSE", tool_calls=[NormalizedToolCall(name="find_by_name", args={"Pattern": "*.lua", "SearchDirectory": "/dir"})]),
        ]
        rep = engine.analyze(meta, steps)
        ro_antipatterns = [ap for ap in rep.antipatterns if ap.code == "READ_ONLY_LOOP"]
        self.assertEqual(len(ro_antipatterns), 1)
        self.assertEqual(ro_antipatterns[0].step_index, 4)

    def test_ping_pong_tool_loop_detection(self):
        engine = AuditEngine()
        meta = ConversationMetadata(session_id="test-pp", runtime="antigravity", source_path=Path("/dummy"))
        steps = [
            NormalizedStep(step_index=0, source="USER", step_type="USER_INPUT", content="start"),
            NormalizedStep(step_index=1, source="MODEL", step_type="PLANNER_RESPONSE", tool_calls=[NormalizedToolCall(name="view_file", args={"AbsolutePath": "/a.lua", "StartLine": 1, "EndLine": 50})]),
            NormalizedStep(step_index=2, source="MODEL", step_type="PLANNER_RESPONSE", tool_calls=[NormalizedToolCall(name="view_file", args={"AbsolutePath": "/b.lua", "StartLine": 1, "EndLine": 50})]),
            NormalizedStep(step_index=3, source="MODEL", step_type="PLANNER_RESPONSE", tool_calls=[NormalizedToolCall(name="view_file", args={"AbsolutePath": "/a.lua", "StartLine": 51, "EndLine": 100})]),
            NormalizedStep(step_index=4, source="MODEL", step_type="PLANNER_RESPONSE", tool_calls=[NormalizedToolCall(name="view_file", args={"AbsolutePath": "/b.lua", "StartLine": 51, "EndLine": 100})]),
        ]
        rep = engine.analyze(meta, steps)
        pp_antipatterns = [ap for ap in rep.antipatterns if ap.code == "PING_PONG_TOOL_LOOP"]
        self.assertEqual(len(pp_antipatterns), 1)
        self.assertEqual(pp_antipatterns[0].step_index, 4)


class TestAntigravityOutputPairing(unittest.TestCase):
    """Regresión #237: emparejamiento llamada→salida sin IDs y con pasos de salida faltantes."""

    def _parse(self, records):
        import json
        import tempfile
        from adapters.antigravity import AntigravityAdapter

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "transcript.jsonl"
            with open(path, "w", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r) + "\n")
            return {s.step_index: s for s in AntigravityAdapter().parse(path)}

    @staticmethod
    def _call(idx, name):
        return {"step_index": idx, "source": "MODEL", "type": "PLANNER_RESPONSE",
                "tool_calls": [{"name": name, "args": {}}]}

    @staticmethod
    def _out(idx, content):
        return {"step_index": idx, "source": "MODEL", "type": "GENERIC", "content": content}

    def test_missing_output_step_does_not_shift_later_pairs(self):
        # Reproduce el transcript real: falta el paso 78 (salida del 77).
        records = [
            self._call(75, "call_mcp_tool"), self._out(76, "salida-75"),
            self._call(77, "view_file"),
            self._call(79, "view_file"), self._out(80, "salida-79"),
            self._call(81, "grep_search"), self._out(82, "salida-81"),
        ]
        steps = self._parse(records)
        self.assertEqual(steps[75].tool_calls[0].raw_output, "salida-75")
        self.assertIsNone(steps[77].tool_calls[0].raw_output)
        self.assertEqual(steps[79].tool_calls[0].raw_output, "salida-79")
        self.assertEqual(steps[81].tool_calls[0].raw_output, "salida-81")

    def test_unordered_records_pair_by_step_index(self):
        records = [self._out(2, "salida-1"), self._call(1, "view_file")]
        steps = self._parse(records)
        self.assertEqual(steps[1].tool_calls[0].raw_output, "salida-1")

    def test_parallel_calls_in_one_step_pair_in_order(self):
        records = [
            {"step_index": 1, "source": "MODEL", "type": "PLANNER_RESPONSE",
             "tool_calls": [{"name": "view_file", "args": {}}, {"name": "grep_search", "args": {}}]},
            self._out(2, "a"), self._out(3, "b"),
        ]
        steps = self._parse(records)
        self.assertEqual([tc.raw_output for tc in steps[1].tool_calls], ["a", "b"])


class TestTranscriptTruncationSeverity(unittest.TestCase):
    """Regresión #237: truncated_fields es recorte del registro, no pérdida de contexto."""

    def test_truncated_fields_reported_as_low_severity(self):
        step = NormalizedStep(step_index=74, source="MODEL", step_type="GENERIC",
                              content="x", truncated_fields=["content"])
        found = [a for a in AuditEngine()._detect_antipatterns([step]) if a.code == "CONTEXT_TRUNCATION"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, "BAJA")
        self.assertIn("no evidencia pérdida de contexto", found[0].description)


class TestTestRetryChurnAntipattern(unittest.TestCase):
    """Pruebas unitarias para la detección del antipatrón TEST_RETRY_CHURN."""

    def _make_edit_step(self, step_index: int, target_file: str = "main.py") -> NormalizedStep:
        return NormalizedStep(
            step_index=step_index,
            source="MODEL",
            step_type="PLANNER_RESPONSE",
            tool_calls=[
                NormalizedToolCall(
                    name="replace_file_content",
                    args={"TargetFile": target_file, "ReplacementContent": "foo"},
                    status="DONE",
                )
            ],
        )

    def _make_test_step(
        self,
        step_index: int,
        cmd: str = "python3 -m unittest discover",
        status: str = "ERROR",
        error: str = "AssertionError: 1 != 2",
    ) -> NormalizedStep:
        return NormalizedStep(
            step_index=step_index,
            source="MODEL",
            step_type="PLANNER_RESPONSE",
            status=status,
            tool_calls=[
                NormalizedToolCall(
                    name="run_command",
                    args={"CommandLine": cmd},
                    status=status,
                    error=error if status == "ERROR" else None,
                )
            ],
        )

    def test_three_failed_cycles_triggers_antipattern(self):
        """Verifica que 3 ciclos de edición + test fallido detecten TEST_RETRY_CHURN."""
        steps = [
            self._make_edit_step(1),
            self._make_test_step(2),
            self._make_edit_step(3),
            self._make_test_step(4),
            self._make_edit_step(5),
            self._make_test_step(6),
        ]
        engine = AuditEngine()
        antipatterns = engine._detect_antipatterns(steps)
        churn = [a for a in antipatterns if a.code == "TEST_RETRY_CHURN"]
        self.assertEqual(len(churn), 1)
        self.assertEqual(churn[0].severity, "ALTA")
        self.assertEqual(churn[0].step_index, 6)
        self.assertIn("3 ciclos alternantes", churn[0].description)
        self.assertIn("entre los pasos 1 y 6", churn[0].description)
        self.assertIn("Stop & Read Holístico", churn[0].recommendation)

    def test_two_failed_cycles_does_not_trigger(self):
        """Verifica que menos de 3 ciclos de edición + test fallido no disparen el antipatrón."""
        steps = [
            self._make_edit_step(1),
            self._make_test_step(2),
            self._make_edit_step(3),
            self._make_test_step(4),
        ]
        engine = AuditEngine()
        antipatterns = engine._detect_antipatterns(steps)
        churn = [a for a in antipatterns if a.code == "TEST_RETRY_CHURN"]
        self.assertEqual(len(churn), 0)

    def test_intermediate_read_steps_do_not_break_churn(self):
        """Verifica que lecturas intermedias de código o error no interrumpan la detección."""
        read_step_1 = NormalizedStep(
            step_index=3,
            source="MODEL",
            step_type="PLANNER_RESPONSE",
            tool_calls=[
                NormalizedToolCall(
                    name="view_file",
                    args={"AbsolutePath": "main.py", "StartLine": 1, "EndLine": 30},
                    status="DONE",
                )
            ],
        )
        read_step_2 = NormalizedStep(
            step_index=6,
            source="MODEL",
            step_type="PLANNER_RESPONSE",
            tool_calls=[
                NormalizedToolCall(
                    name="grep_search",
                    args={"SearchPath": "main.py", "Query": "foo"},
                    status="DONE",
                )
            ],
        )
        steps = [
            self._make_edit_step(1),
            self._make_test_step(2),
            read_step_1,
            self._make_edit_step(4),
            self._make_test_step(5),
            read_step_2,
            self._make_edit_step(7),
            self._make_test_step(8),
        ]
        engine = AuditEngine()
        antipatterns = engine._detect_antipatterns(steps)
        churn = [a for a in antipatterns if a.code == "TEST_RETRY_CHURN"]
        self.assertEqual(len(churn), 1)
        self.assertEqual(churn[0].step_index, 8)
        self.assertIn("entre los pasos 1 y 8", churn[0].description)

    def test_passing_test_resets_churn_when_under_threshold(self):
        """Verifica que un test exitoso antes de alcanzar 3 fallos reinicie el contador."""
        steps = [
            self._make_edit_step(1),
            self._make_test_step(2, status="ERROR"),
            self._make_edit_step(3),
            self._make_test_step(4, status="ERROR"),
            self._make_edit_step(5),
            self._make_test_step(6, status="DONE", error=""),
        ]
        engine = AuditEngine()
        antipatterns = engine._detect_antipatterns(steps)
        churn = [a for a in antipatterns if a.code == "TEST_RETRY_CHURN"]
        self.assertEqual(len(churn), 0)

    def test_passing_test_flushes_churn_when_ge_three(self):
        """Verifica que si tras >= 3 fallos se pasa el test, el antipatrón se registre debidamente."""
        steps = [
            self._make_edit_step(1),
            self._make_test_step(2, status="ERROR"),
            self._make_edit_step(3),
            self._make_test_step(4, status="ERROR"),
            self._make_edit_step(5),
            self._make_test_step(6, status="ERROR"),
            self._make_edit_step(7),
            self._make_test_step(8, status="DONE", error=""),
        ]
        engine = AuditEngine()
        antipatterns = engine._detect_antipatterns(steps)
        churn = [a for a in antipatterns if a.code == "TEST_RETRY_CHURN"]
        self.assertEqual(len(churn), 1)
        self.assertEqual(churn[0].step_index, 6)
        self.assertIn("entre los pasos 1 y 6", churn[0].description)

    def test_busted_lua_test_command_detected(self):
        """Verifica la detección con comandos de test específicos (ej. busted en Lua)."""
        steps = [
            self._make_edit_step(1, target_file="journal.lua"),
            self._make_test_step(2, cmd="busted test_journal.lua"),
            self._make_edit_step(3, target_file="journal.lua"),
            self._make_test_step(4, cmd="lua test_journal.lua"),
            self._make_edit_step(5, target_file="journal.lua"),
            self._make_test_step(6, cmd="./build.sh check"),
        ]
        engine = AuditEngine()
        antipatterns = engine._detect_antipatterns(steps)
        churn = [a for a in antipatterns if a.code == "TEST_RETRY_CHURN"]
        self.assertEqual(len(churn), 1)
        self.assertEqual(churn[0].severity, "ALTA")


if __name__ == "__main__":
    unittest.main()


