#!/usr/bin/env python3
"""
Tests unitarios para el reporte de violaciones por ID de regla y detección de
bloqueos de hooks deterministas P0 en Antigravity y Claude Code (#282 / #285).
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys
skill_root = Path(__file__).resolve().parent.parent
scripts_path = skill_root / "scripts"
if str(scripts_path) not in sys.path:
    sys.path.insert(0, str(scripts_path))

from adapters.antigravity import AntigravityAdapter
from adapters.claude import ClaudeAdapter
from audit_engine import (
    ANTIPATTERN_RULE_MAP,
    RULE_REGISTRY,
    AuditEngine,
    DetectedAntipattern,
    aggregate_rules_violations,
    format_json_rules_report,
    format_markdown_rules_report,
    format_text_rules_report,
)


class TestRulesViolationReport(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agent_audit_rules_test_"))
        self.engine = AuditEngine()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_antipattern_rule_id_auto_mapping(self):
        """Verifica que cada antipatrón se mapee automáticamente a su regla canónica."""
        ap_read = DetectedAntipattern(
            severity="ALTA",
            code="UNPAGINATED_FILE_READ",
            title="Lectura No Paginada",
            step_index=1,
            description="Lectura masiva",
            recommendation="Acotar paginado",
        )
        self.assertEqual(ap_read.rule_id, "ENV_PAGED_READ_CIRCUIT_BREAKER")

        ap_repl = DetectedAntipattern(
            severity="ALTA",
            code="TERMINAL_REPL_LOOP",
            title="REPL inline",
            step_index=2,
            description="python -c",
            recommendation="No usar REPL",
        )
        self.assertEqual(ap_repl.rule_id, "ENV_PROHIBITION_REPL")

        ap_comp = DetectedAntipattern(
            severity="BAJA",
            code="COMPLACENCY_DETECTED",
            title="Complacencia",
            step_index=3,
            description="tienes toda la razon",
            recommendation="Mantener tono asertivo",
        )
        self.assertEqual(ap_comp.rule_id, "CRIT_ZERO_COMPLACENCY")

        ap_pipe = DetectedAntipattern(
            severity="MEDIA",
            code="TERMINAL_PIPELINING",
            title="Pipelining",
            step_index=4,
            description="comando && comando",
            recommendation="Usar llamadas atomicas",
        )
        self.assertEqual(ap_pipe.rule_id, "AGY_BYPASS_EXCLUSIVITY")

    def test_antigravity_p0_hook_block_and_antipatterns(self):
        """Valida detección de antipatrones y bloqueos P0 en transcript de Antigravity."""
        transcript_file = self.temp_dir / "transcript.jsonl"
        lines = [
            # Paso 0: Prompt del usuario
            {
                "step_index": 0,
                "source": "USER",
                "type": "USER_INPUT",
                "created_at": "2026-11-08T10:00:00Z",
                "content": "<USER_REQUEST>Prueba de auditoria de reglas</USER_REQUEST>",
            },
            # Paso 1: Lectura masiva no paginada (UNPAGINATED_FILE_READ -> ENV_PAGED_READ_CIRCUIT_BREAKER)
            {
                "step_index": 1,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "created_at": "2026-11-08T10:00:02Z",
                "tool_calls": [
                    {
                        "name": "view_file",
                        "args": {"AbsolutePath": "/workspace/large_file.txt"},
                    }
                ],
            },
            {
                "step_index": 2,
                "source": "SYSTEM",
                "type": "GENERIC",
                "status": "DONE",
                "content": "Line 1\nLine 2\nLine 300",
            },
            # Paso 3: Complacencia (COMPLACENCY_DETECTED -> CRIT_ZERO_COMPLACENCY)
            {
                "step_index": 3,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "created_at": "2026-11-08T10:00:05Z",
                "content": "Tienes toda la razón, procederé de inmediato con los cambios.",
            },
            # Paso 4: Bloqueo mecánico por Hard Circuit Breaker P0 (P0_HOOK_BLOCK -> ENV_PAGED_READ_CIRCUIT_BREAKER)
            {
                "step_index": 4,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "created_at": "2026-11-08T10:00:10Z",
                "tool_calls": [
                    {
                        "name": "view_file",
                        "args": {"AbsolutePath": "/workspace/other.txt", "StartLine": 1, "EndLine": 50},
                    }
                ],
            },
            {
                "step_index": 5,
                "source": "SYSTEM",
                "type": "GENERIC",
                "status": "ERROR",
                "content": "Encountered error in tool execution: tool call denied by pre-tool hook: Hard Circuit Breaker Activado: Has alcanzado el límite de 6 lecturas pasivas consecutivas ('view_file'). Detente y sintetiza.",
            },
            # Paso 6: Bloqueo mecánico por Guard P0 de REPL (P0_HOOK_BLOCK -> ENV_PROHIBITION_REPL)
            {
                "step_index": 6,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "created_at": "2026-11-08T10:00:15Z",
                "tool_calls": [
                    {
                        "name": "run_command",
                        "args": {"CommandLine": "python3 -c 'print(1)'"},
                    }
                ],
            },
            {
                "step_index": 7,
                "source": "SYSTEM",
                "type": "GENERIC",
                "status": "ERROR",
                "content": "tool call denied by pre-tool hook: Guard P0: REPL detectado. Prohibido evaluar en línea o subshells.",
            },
        ]

        with open(transcript_file, "w", encoding="utf-8") as f:
            for l in lines:
                f.write(json.dumps(l) + "\n")

        adapter = AntigravityAdapter()
        steps = adapter.parse(transcript_file)
        metadata = adapter.extract_metadata(transcript_file, steps)
        report = self.engine.analyze(metadata, steps)

        rules_report = aggregate_rules_violations([report])
        self.assertEqual(rules_report.total_sessions, 1)

        summary_by_rule = {s.rule_id: s for s in rules_report.rule_summaries}

        # ENV_PAGED_READ_CIRCUIT_BREAKER: 1 antipatrón (UNPAGINATED_FILE_READ) + 1 bloqueo P0
        self.assertIn("ENV_PAGED_READ_CIRCUIT_BREAKER", summary_by_rule)
        cb_summary = summary_by_rule["ENV_PAGED_READ_CIRCUIT_BREAKER"]
        self.assertEqual(cb_summary.total_violations, 2)
        self.assertEqual(cb_summary.antipattern_count, 1)
        self.assertEqual(cb_summary.p0_block_count, 1)
        self.assertIn("Enforcement mecánico P0 activo", cb_summary.action_suggestion)

        # CRIT_ZERO_COMPLACENCY: 1 antipatrón
        self.assertIn("CRIT_ZERO_COMPLACENCY", summary_by_rule)
        comp_summary = summary_by_rule["CRIT_ZERO_COMPLACENCY"]
        self.assertEqual(comp_summary.total_violations, 1)
        self.assertEqual(comp_summary.antipattern_count, 1)
        self.assertIn("Candidata a promoción a P0", comp_summary.action_suggestion)

        # ENV_PROHIBITION_REPL: 1 bloqueo P0
        self.assertIn("ENV_PROHIBITION_REPL", summary_by_rule)
        repl_summary = summary_by_rule["ENV_PROHIBITION_REPL"]
        self.assertEqual(repl_summary.total_violations, 1)
        self.assertEqual(repl_summary.p0_block_count, 1)

    def test_claude_adapter_p0_hook_block(self):
        """Valida detección de bloqueos P0 en formato de sesión de Claude Code."""
        session_file = self.temp_dir / "claude_session.json"
        data = [
            {
                "role": "user",
                "timestamp": "2026-11-08T11:00:00Z",
                "content": [{"type": "text", "text": "Hacer commit en main"}],
            },
            {
                "role": "assistant",
                "timestamp": "2026-11-08T11:00:05Z",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool_main_commit",
                        "name": "Bash",
                        "input": {"command": "git commit -m 'direct to main'"},
                    }
                ],
            },
            {
                "role": "user",
                "timestamp": "2026-11-08T11:00:06Z",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool_main_commit",
                        "is_error": True,
                        "content": "[PreToolUse] Guard P0: Prohibido commit o push directo a main. Usar ramas efimeras.",
                    }
                ],
            },
        ]

        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

        adapter = ClaudeAdapter()
        steps = adapter.parse(session_file)
        metadata = adapter.extract_metadata(session_file, steps)
        report = self.engine.analyze(metadata, steps)

        rules_report = aggregate_rules_violations([report])
        summary_by_rule = {s.rule_id: s for s in rules_report.rule_summaries}

        self.assertIn("TRACK_IMMUTABILITY_TRACEABILITY", summary_by_rule)
        git_summary = summary_by_rule["TRACK_IMMUTABILITY_TRACEABILITY"]
        self.assertEqual(git_summary.total_violations, 1)
        self.assertEqual(git_summary.p0_block_count, 1)
        self.assertIn("Reforzar cobertura P0", git_summary.action_suggestion)

    def test_multi_session_aggregation_and_lifecycle_suggestions(self):
        """Verifica la agregación de múltiples sesiones y las sugerencias de ciclo de vida."""
        rep1 = self.engine.analyze(
            metadata=AntigravityAdapter().extract_metadata(self.temp_dir / "s1", []),
            steps=[],
        )
        rep1.metadata.session_id = "sesion-1"
        rep1.antipatterns = [
            DetectedAntipattern(
                severity="BAJA",
                code="COMPLACENCY_DETECTED",
                title="Complacencia",
                step_index=2,
                description="frase complaciente",
                recommendation="evitar disculpas",
            )
        ]

        rep2 = self.engine.analyze(
            metadata=AntigravityAdapter().extract_metadata(self.temp_dir / "s2", []),
            steps=[],
        )
        rep2.metadata.session_id = "sesion-2"
        rep2.antipatterns = [
            DetectedAntipattern(
                severity="BAJA",
                code="COMPLACENCY_DETECTED",
                title="Complacencia",
                step_index=5,
                description="frase complaciente",
                recommendation="evitar disculpas",
            ),
            DetectedAntipattern(
                severity="CRÍTICA",
                code="P0_HOOK_BLOCK",
                title="Bloqueo P0",
                step_index=8,
                description="Bloqueo circuit breaker",
                recommendation="detenerse",
                rule_id="ENV_PAGED_READ_CIRCUIT_BREAKER",
            ),
        ]

        rules_report = aggregate_rules_violations([rep1, rep2])
        self.assertEqual(rules_report.total_sessions, 2)
        self.assertEqual(rules_report.total_violations, 3)

        summary_by_rule = {s.rule_id: s for s in rules_report.rule_summaries}

        # CRIT_ZERO_COMPLACENCY aparece en 2 sesiones con 2 violaciones -> candidato a P0
        comp = summary_by_rule["CRIT_ZERO_COMPLACENCY"]
        self.assertEqual(comp.total_violations, 2)
        self.assertEqual(comp.sessions_count, 2)
        self.assertIn("sesion-1", comp.sessions)
        self.assertIn("sesion-2", comp.sessions)
        self.assertIn("Candidata a promoción a P0", comp.action_suggestion)

        # Regla P2 sin violaciones (ej. ENG_PROPORTIONALITY_MBR) -> candidata a bajar a P1 o eliminarse
        mbr = summary_by_rule["ENG_PROPORTIONALITY_MBR"]
        self.assertEqual(mbr.total_violations, 0)
        self.assertIn("Candidata a bajar a P1 o eliminarse", mbr.action_suggestion)

    def test_report_formats(self):
        """Valida que los formateadores texto, markdown y json generen salidas consistentes."""
        rep = self.engine.analyze(
            metadata=AntigravityAdapter().extract_metadata(self.temp_dir / "s", []),
            steps=[],
        )
        rep.antipatterns = [
            DetectedAntipattern(
                severity="ALTA",
                code="UNPAGINATED_FILE_READ",
                title="Lectura No Paginada",
                step_index=1,
                description="lectura masiva",
                recommendation="paginar",
            )
        ]
        rules_report = aggregate_rules_violations([rep])

        text_out = format_text_rules_report(rules_report)
        self.assertIn("INFORME DE VIOLACIONES POR ID DE REGLA", text_out)
        self.assertIn("ENV_PAGED_READ_CIRCUIT_BREAKER", text_out)

        md_out = format_markdown_rules_report(rules_report)
        self.assertIn("# Informe de Violaciones por ID de Regla", md_out)
        self.assertIn("`ENV_PAGED_READ_CIRCUIT_BREAKER`", md_out)

        json_out = format_json_rules_report(rules_report)
        parsed = json.loads(json_out)
        self.assertEqual(parsed["total_sessions"], 1)
        self.assertEqual(parsed["total_violations"], 1)
        self.assertTrue(any(s["rule_id"] == "ENV_PAGED_READ_CIRCUIT_BREAKER" for s in parsed["rule_summaries"]))

    def test_cli_rules_report_execution(self):
        """Ejecuta el CLI agent-audit con --rules y valida la salida estándar."""
        transcript_file = self.temp_dir / "transcript.jsonl"
        lines = [
            {
                "step_index": 0,
                "source": "USER",
                "type": "USER_INPUT",
                "content": "<USER_REQUEST>CLI test</USER_REQUEST>",
            },
            {
                "step_index": 1,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "content": "Tienes toda la razón, mil disculpas.",
            },
        ]
        with open(transcript_file, "w", encoding="utf-8") as f:
            for l in lines:
                f.write(json.dumps(l) + "\n")

        cli_bin = skill_root / "bin" / "agent-audit"
        cmd = [sys.executable, str(cli_bin), str(transcript_file), "--rules"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("INFORME DE VIOLACIONES POR ID DE REGLA", res.stdout)
        self.assertIn("CRIT_ZERO_COMPLACENCY", res.stdout)

        # Prueba con flag --json
        cmd_json = [sys.executable, str(cli_bin), str(transcript_file), "--rules", "--json"]
        res_json = subprocess.run(cmd_json, capture_output=True, text=True)
        self.assertEqual(res_json.returncode, 0)
        data = json.loads(res_json.stdout)
        self.assertEqual(data["total_sessions"], 1)
        self.assertEqual(data["total_violations"], 1)

    def test_discover_session_files_in_directory(self):
        """Valida que discover_session_files localice múltiples sesiones en un directorio."""
        sub1 = self.temp_dir / "sess1"
        sub2 = self.temp_dir / "sess2"
        sub1.mkdir()
        sub2.mkdir()

        t1 = sub1 / "transcript.jsonl"
        t2 = sub2 / "transcript.jsonl"
        for t in (t1, t2):
            with open(t, "w", encoding="utf-8") as f:
                f.write(json.dumps({"step_index": 0, "source": "USER", "type": "USER_INPUT", "content": "hi"}) + "\n")

        cli_bin = skill_root / "bin" / "agent-audit"
        cmd = [sys.executable, str(cli_bin), str(self.temp_dir), "--rules", "--json"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res_json := res.stdout)
        self.assertEqual(json.loads(res_json)["total_sessions"], 2)


if __name__ == "__main__":
    unittest.main()

