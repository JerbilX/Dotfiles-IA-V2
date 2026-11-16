#!/usr/bin/env python3
"""
Pruebas unitarias para ClaudeAdapter y validación de clasificación de tool_result.
Ref: Issue #268.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Asegurar importación de scripts del skill
CURRENT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = CURRENT_DIR.parent
SCRIPTS_DIR = SKILL_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from adapters.claude import ClaudeAdapter
from audit_engine import AuditEngine


class TestClaudeAdapterToolResult(unittest.TestCase):
    """Pruebas de normalización de tool_result y turnos de usuario en ClaudeAdapter."""

    def setUp(self):
        self.adapter = ClaudeAdapter()
        self.engine = AuditEngine()

    def test_real_user_text_message_classified_as_user(self):
        """Los mensajes reales del usuario (texto o bloques de texto) se clasifican como USER / USER_INPUT."""
        events = [
            {
                "role": "user",
                "content": "Por favor revisa el archivo main.py",
                "timestamp": "2026-11-06T00:00:00Z",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "¿Qué encontraste en la búsqueda?"}
                ],
                "timestamp": "2026-11-06T00:00:10Z",
            },
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")
            f_path = Path(f.name)

        try:
            steps = self.adapter.parse(f_path)
            self.assertEqual(len(steps), 2)
            for s in steps:
                self.assertEqual(s.source, "USER")
                self.assertEqual(s.step_type, "USER_INPUT")
            self.assertEqual(steps[0].content, "Por favor revisa el archivo main.py")
            self.assertEqual(steps[1].content, "¿Qué encontraste en la búsqueda?")
        finally:
            f_path.unlink(missing_ok=True)

    def test_tool_result_classified_as_system_and_tool_output(self):
        """Un evento con role: 'user' formado solo por bloques tool_result no se normaliza como USER_INPUT."""
        events = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_01",
                        "name": "view_file",
                        "input": {"AbsolutePath": "/workspace/main.py", "StartLine": 1, "EndLine": 20},
                    }
                ],
                "timestamp": "2026-11-06T00:00:01Z",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_01",
                        "content": "def main():\n    pass\n",
                        "is_error": False,
                    }
                ],
                "timestamp": "2026-11-06T00:00:02Z",
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_02",
                        "name": "run_command",
                        "input": {"CommandLine": "false"},
                    }
                ],
                "timestamp": "2026-11-06T00:00:03Z",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_02",
                        "content": "Command failed with exit code 1",
                        "is_error": True,
                    }
                ],
                "timestamp": "2026-11-06T00:00:04Z",
            },
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")
            f_path = Path(f.name)

        try:
            steps = self.adapter.parse(f_path)
            self.assertEqual(len(steps), 4)

            # Paso 0: llamada a herramienta (MODEL / PLANNER_RESPONSE)
            self.assertEqual(steps[0].source, "MODEL")
            self.assertEqual(steps[0].step_type, "PLANNER_RESPONSE")
            self.assertEqual(len(steps[0].tool_calls), 1)
            self.assertEqual(steps[0].tool_calls[0].status, "DONE")
            self.assertEqual(steps[0].tool_calls[0].raw_output, "def main():\n    pass\n")

            # Paso 1: tool_result normalizado como SYSTEM / TOOL_OUTPUT, no USER_INPUT
            self.assertEqual(steps[1].source, "SYSTEM")
            self.assertEqual(steps[1].step_type, "TOOL_OUTPUT")
            self.assertEqual(steps[1].status, "DONE")
            self.assertIn("def main()", steps[1].content or "")

            # Paso 2: segunda llamada a herramienta
            self.assertEqual(steps[2].source, "MODEL")
            self.assertEqual(steps[2].tool_calls[0].status, "ERROR")

            # Paso 3: tool_result con error
            self.assertEqual(steps[3].source, "SYSTEM")
            self.assertEqual(steps[3].step_type, "TOOL_OUTPUT")
            self.assertEqual(steps[3].status, "ERROR")
            self.assertIn("Command failed", steps[3].content or "")
        finally:
            f_path.unlink(missing_ok=True)

    def test_tool_result_list_content_extracted_cleanly_and_deduped(self):
        """tc.error y tc.raw_output extraen texto limpio de content en lista y get_failed_steps no duplica."""
        from audit_engine import get_failed_steps

        events = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_list_01",
                        "name": "run_command",
                        "input": {"CommandLine": "make test"},
                    }
                ],
                "timestamp": "2026-11-06T00:00:01Z",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_list_01",
                        "content": [
                            {"type": "text", "text": "Error: Command failed with exit code 2"},
                            {"type": "text", "text": "Details: missing dependency"},
                        ],
                        "is_error": True,
                    }
                ],
                "timestamp": "2026-11-06T00:00:02Z",
            },
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")
            f_path = Path(f.name)

        try:
            steps = self.adapter.parse(f_path)
            self.assertEqual(len(steps), 2)

            # Verificar que tc.error no es str(lista) sino el texto extraído
            model_tc = steps[0].tool_calls[0]
            self.assertEqual(model_tc.status, "ERROR")
            expected_err = "Error: Command failed with exit code 2\nDetails: missing dependency"
            self.assertEqual(model_tc.error, expected_err)
            self.assertNotIn("[{'type':", model_tc.error)

            # Verificar deduplicación en get_failed_steps
            failed = get_failed_steps(steps)
            self.assertEqual(len(failed), 1)
            self.assertEqual(failed[0].step_index, 0)
        finally:
            f_path.unlink(missing_ok=True)

    def test_parallel_tool_results_failed_steps_dedup(self):
        """Llamadas en paralelo en un mismo evento no duplican errores en get_failed_steps."""
        from audit_engine import get_failed_steps

        events = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_p1",
                        "name": "view_file",
                        "input": {"AbsolutePath": "/a.txt"},
                    },
                    {
                        "type": "tool_use",
                        "id": "toolu_p2",
                        "name": "run_command",
                        "input": {"CommandLine": "exit 1"},
                    },
                ],
                "timestamp": "2026-11-06T00:00:01Z",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_p1",
                        "content": "file contents",
                        "is_error": False,
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_p2",
                        "content": "failed execution",
                        "is_error": True,
                    },
                ],
                "timestamp": "2026-11-06T00:00:02Z",
            },
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")
            f_path = Path(f.name)

        try:
            steps = self.adapter.parse(f_path)
            self.assertEqual(len(steps), 2)
            tool_output_step = steps[1]
            self.assertEqual(tool_output_step.status, "ERROR")
            self.assertIn("file contents", tool_output_step.content or "")
            self.assertIn("failed execution", tool_output_step.content or "")

            # get_failed_steps debe retornar solo el paso 0
            failed = get_failed_steps(steps)
            self.assertEqual(len(failed), 1)
            self.assertEqual(failed[0].step_index, 0)
        finally:
            f_path.unlink(missing_ok=True)

    def test_read_only_loop_and_user_turns_with_claude_code_fixture(self):
        """Fixture con eventos planos ({"role", "content"})."""
        self._assert_read_only_loop_fixture(nested=False)

    def test_read_only_loop_and_user_turns_with_real_claude_code_format(self):
        """Fixture con el formato JSONL real de Claude Code ({"type", "message": {...}, "timestamp"})."""
        self._assert_read_only_loop_fixture(nested=True)

    @staticmethod
    def _to_claude_code_record(ev):
        """Envuelve un evento plano en el formato JSONL real de Claude Code."""
        msg = {k: v for k, v in ev.items() if k != "timestamp"}
        return {"type": ev["role"], "message": msg, "timestamp": ev["timestamp"], "uuid": "u"}

    def _assert_read_only_loop_fixture(self, nested):
        """
        Test E2E con fixture de Claude Code:
        5 lecturas pasivas consecutivas intercaladas con sus respectivos tool_result
        deben disparar el antipatrón READ_ONLY_LOOP, y user_turns debe reflejar
        únicamente los mensajes de texto del usuario.
        """
        events = [
            # 1. Turno de usuario real inicial
            {
                "role": "user",
                "content": "Por favor investiga el error en el módulo de autenticación.",
                "timestamp": "2026-11-06T00:00:00Z",
            },
            # 2. Lectura 1: View
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "View",
                        "input": {"file_path": "/app/auth.py", "view_range": [1, 50]},
                    }
                ],
                "timestamp": "2026-11-06T00:00:02Z",
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "import sys\n..."}],
                "timestamp": "2026-11-06T00:00:03Z",
            },
            # 3. Lectura 2: Grep
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t2",
                        "name": "Grep",
                        "input": {"pattern": "def login", "path": "/app"},
                    }
                ],
                "timestamp": "2026-11-06T00:00:05Z",
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "t2", "content": "auth.py:10: def login():"}],
                "timestamp": "2026-11-06T00:00:06Z",
            },
            # 4. Lectura 3: Glob
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t3",
                        "name": "Glob",
                        "input": {"pattern": "*.py"},
                    }
                ],
                "timestamp": "2026-11-06T00:00:08Z",
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "t3", "content": "auth.py\nutils.py"}],
                "timestamp": "2026-11-06T00:00:09Z",
            },
            # 5. Lectura 4: View
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t4",
                        "name": "View",
                        "input": {"file_path": "/app/utils.py", "view_range": [1, 40]},
                    }
                ],
                "timestamp": "2026-11-06T00:00:11Z",
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "t4", "content": "def hash(): ..."}],
                "timestamp": "2026-11-06T00:00:12Z",
            },
            # 6. Lectura 5: Read
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t5",
                        "name": "Read",
                        "input": {"file_path": "/app/config.py"},
                    }
                ],
                "timestamp": "2026-11-06T00:00:14Z",
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "t5", "content": "SECRET_KEY = 123"}],
                "timestamp": "2026-11-06T00:00:15Z",
            },
            # 7. Turno de usuario real final
            {
                "role": "user",
                "content": "¿Pudiste encontrar la causa del fallo?",
                "timestamp": "2026-11-06T00:00:20Z",
            },
        ]

        if nested:
            events = [self._to_claude_code_record(ev) for ev in events]
            # Registros sin mensaje presentes en transcripts reales: deben descartarse
            events.insert(0, {"type": "file-history-snapshot", "messageId": "m0", "snapshot": {}})
            events.append({"type": "summary", "summary": "Investigación de auth", "leafUuid": "u"})

        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")
            f_path = Path(f.name)

        try:
            steps = self.adapter.parse(f_path)
            meta = self.adapter.extract_metadata(f_path, steps)
            fast_meta = self.adapter.fast_extract_metadata(f_path)
            self.assertIn("investiga el error", (fast_meta.title or "").lower())
            report = self.engine.analyze(meta, steps)

            # Verificaciones de turnos
            # Solo 2 mensajes reales del usuario
            self.assertEqual(report.user_turns, 2, f"Esperado 2 user_turns pero se obtuvo {report.user_turns}")
            # 5 respuestas del modelo
            self.assertEqual(report.model_turns, 5, f"Esperado 5 model_turns pero se obtuvo {report.model_turns}")
            # 5 pasos system (tool_output)
            self.assertEqual(report.system_steps, 5, f"Esperado 5 system_steps pero se obtuvo {report.system_steps}")

            # Verificación de detección de READ_ONLY_LOOP
            read_loop_antipatterns = [ap for ap in report.antipatterns if ap.code == "READ_ONLY_LOOP"]
            self.assertTrue(
                len(read_loop_antipatterns) >= 1,
                "Se esperaba la detección de READ_ONLY_LOOP ante 5 lecturas consecutivas de Claude Code"
            )
            # Título extraído del prompt real de usuario
            self.assertIn("investiga el error", (meta.title or "").lower())
        finally:
            f_path.unlink(missing_ok=True)


class TestClaudeAdapterMessageMerge(unittest.TestCase):
    """Fusión de bloques de una misma respuesta del modelo (Ref: Issue #275)."""

    def setUp(self):
        self.adapter = ClaudeAdapter()
        self.engine = AuditEngine()

    def test_split_response_counts_as_single_model_turn(self):
        """Una respuesta partida en 3 líneas con el mismo message.id cuenta como 1 model_turn sin duplicar tokens."""
        usage = {"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 1000}

        def assistant_line(block, ts):
            return {
                "type": "assistant",
                "timestamp": ts,
                "uuid": ts,
                "message": {"id": "msg_01", "role": "assistant", "content": [block], "usage": usage},
            }

        records = [
            {"type": "user", "timestamp": "2026-11-06T00:00:00Z", "uuid": "u0",
             "message": {"role": "user", "content": "Lee main.py"}},
            assistant_line({"type": "thinking", "thinking": "Debo leer el archivo."}, "2026-11-06T00:00:01Z"),
            assistant_line({"type": "text", "text": "Leo el archivo."}, "2026-11-06T00:00:05Z"),
            assistant_line({"type": "tool_use", "id": "t1", "name": "Read",
                            "input": {"file_path": "main.py"}}, "2026-11-06T00:00:06Z"),
            {"type": "user", "timestamp": "2026-11-06T00:00:07Z", "uuid": "u1",
             "message": {"role": "user", "content": [
                 {"type": "tool_result", "tool_use_id": "t1", "content": "print('hi')"}]}},
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")
            f_path = Path(f.name)

        try:
            steps = self.adapter.parse(f_path)
            self.assertEqual(len(steps), 3)
            model = steps[1]
            self.assertEqual(model.source, "MODEL")
            self.assertEqual(model.thinking, "Debo leer el archivo.")
            self.assertEqual(model.content, "Leo el archivo.")
            self.assertEqual([tc.name for tc in model.tool_calls], ["Read"])
            self.assertEqual(model.tokens, {"input": 100, "output": 50, "cache_read": 1000})
            self.assertEqual(model.duration_seconds, 6.0)
            self.assertEqual(sum(s.tokens.get("output", 0) for s in steps), 50)

            meta = self.adapter.extract_metadata(f_path, steps)
            report = self.engine.analyze(meta, steps)
            self.assertEqual(report.model_turns, 1)
            self.assertEqual(report.system_steps, 1)
        finally:
            f_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
