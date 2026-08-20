from __future__ import annotations

import io
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from steady_memory.adapters import handle_mcp_request, make_http_handler
from steady_memory.archive import ConflictError, PermissionDenied, ValidationError
from steady_memory.migrations import initialize_archive
from steady_memory.tools import READ, METRICS_WRITE, SteadyTools


class SteadyMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "vault"
        initialize_archive(self.root, name="Synthetic Tester")
        profile = self.root / "data" / "profile.json"
        data = json.loads(profile.read_text(encoding="utf-8"))
        data["height_cm"] = 170
        profile.write_text(json.dumps(data), encoding="utf-8")
        self.tools = SteadyTools(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_initialization_and_validation(self) -> None:
        result = self.tools.call("validate_archive")["result"]
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["schema"]["current"], 1)

    def test_record_weight_is_atomic_idempotent_and_calculates_bmi(self) -> None:
        first = self.tools.call("record_weight", {"date": "2026-01-02", "weight_kg": 70, "condition": "morning"})["result"]
        self.assertEqual(set(first["changed_files"]), {"data/weight.csv", "records/2026/01/2026-01-02.md"})
        row = (self.root / "data" / "weight.csv").read_text(encoding="utf-8")
        self.assertIn("24.22", row)
        duplicate = self.tools.call("record_weight", {"date": "2026-01-02", "weight_kg": 70})["result"]
        self.assertTrue(duplicate["duplicate"])
        with self.assertRaises(ConflictError):
            self.tools.call("record_weight", {"date": "2026-01-02", "weight_kg": 69})

    def test_scopes_and_read_only(self) -> None:
        reader = SteadyTools(self.root, read_only=True)
        self.assertEqual({item["annotations"]["scope"] for item in reader.definitions}, {READ})
        with self.assertRaises(PermissionDenied):
            reader.call("record_weight", {"date": "2026-01-01", "weight_kg": 70})
        metrics = SteadyTools(self.root, scopes={READ, METRICS_WRITE})
        self.assertNotIn("append_long_term_memory", {item["name"] for item in metrics.definitions})

    def test_long_term_memory_needs_confirmation(self) -> None:
        with self.assertRaises(PermissionDenied):
            self.tools.call("append_long_term_memory", {"category": "health", "content": "synthetic fact", "confirmed_stable": False})

    def test_long_term_memory_exact_patch(self) -> None:
        self.tools.call("append_long_term_memory", {"category": "health", "content": "synthetic old fact", "confirmed_stable": True})
        self.tools.call("patch_long_term_memory", {"category": "health", "old_text": "synthetic old fact", "new_text": "synthetic corrected fact"})
        content = (self.root / "memory" / "health.md").read_text(encoding="utf-8")
        self.assertIn("synthetic corrected fact", content)

    def test_context_includes_active_plan_and_trust_notice(self) -> None:
        plans = self.root / "plans"
        plans.mkdir()
        (plans / "active.json").write_text('{"status":"active"}', encoding="utf-8")
        context = self.tools.call("get_context", {"topic": "health", "as_of": "2026-01-03", "recent_days": 0})["result"]
        self.assertEqual(context["plans"][0]["path"], "plans/active.json")
        self.assertIn("untrusted", context["notice"])

    def test_index_search_rebuilds_automatically(self) -> None:
        self.tools.call("record_daily_event", {"date": "2026-01-02", "section": "Events", "content": "synthetic park walk"})
        result = self.tools.call("search_records", {"query": "park walk"})["result"]
        self.assertEqual(result["results"][0]["path"], "records/2026/01/2026-01-02.md")

    def test_mcp_exposes_structured_contract(self) -> None:
        response = handle_mcp_request(self.tools, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertIn("tools", response["result"])

    def test_http_requires_valid_bearer_token(self) -> None:
        token = "synthetic-secret"
        handler = make_http_handler(self.tools, token)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        import threading
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/api/tools")
            try:
                urllib.request.urlopen(request, timeout=2)
                self.fail("unauthenticated request unexpectedly succeeded")
            except urllib.error.HTTPError as exc:
                self.assertEqual(exc.code, 401)
                exc.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_argument_schema_rejects_wrong_types_and_unknown_fields(self) -> None:
        with self.assertRaises(ValidationError):
            self.tools.call("get_weight_trend", {"days": "seven"})
        with self.assertRaises(ValidationError):
            self.tools.call("record_weight", {"date": "2026-01-01", "weight_kg": 70, "guess": True})

    def test_sensitive_credentials_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            self.tools.call("record_daily_event", {"date": "2026-01-01", "section": "Events", "content": "-----BEGIN PRIVATE KEY-----"})

    def test_backup_must_be_outside_vault_and_verifies(self) -> None:
        with self.assertRaises(ValidationError):
            self.tools.call("backup_archive", {"output_path": str(self.root / "bad.zip")})
        output = Path(self.temp.name) / "good.zip"
        self.tools.call("backup_archive", {"output_path": str(output)})
        verified = self.tools.call("verify_backup", {"backup_path": str(output)})["result"]
        self.assertTrue(verified["valid"])

    def test_asset_import_is_hash_idempotent(self) -> None:
        source = Path(self.temp.name) / "synthetic.txt"
        source.write_text("synthetic media fixture", encoding="utf-8")
        arguments = {"date": "2026-01-01", "category": "journal", "source_path": str(source)}
        first = self.tools.call("record_asset", arguments)["result"]
        second = self.tools.call("record_asset", arguments)["result"]
        self.assertTrue(first["changed_files"])
        self.assertTrue(second["duplicate"])


if __name__ == "__main__":
    unittest.main()
