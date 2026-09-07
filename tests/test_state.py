import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import helpers  # noqa: F401
from badcop.state import State


class StateTests(unittest.TestCase):
    def test_missing_file_is_empty(self):
        self.assertEqual(State.load(Path("/nonexistent/state.json")).data, {})

    def test_record_and_query(self):
        s = State()
        self.assertFalse(s.has_sent("INV-1", "firm"))
        when = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
        s.record_sent("INV-1", "firm", "<abc@x>", when)
        self.assertTrue(s.has_sent("INV-1", "firm"))
        self.assertFalse(s.has_sent("INV-1", "final"))
        self.assertEqual(s.sent_steps("INV-1"), ["firm"])
        self.assertEqual(s.data["INV-1"]["sent"][0], {"step": "firm", "sent_at": when.isoformat(), "message_id": "<abc@x>"})
        self.assertIsNone(s.data["INV-1"]["last_error"])

    def test_error_then_success_clears_error(self):
        s = State()
        s.record_error("INV-1", "boom")
        self.assertEqual(s.data["INV-1"]["last_error"], "boom")
        s.record_sent("INV-1", "firm", "<id>")
        self.assertIsNone(s.data["INV-1"]["last_error"])

    def test_round_trip_and_atomic_write(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            s = State()
            s.record_sent("INV-1", "firm", "<id>")
            s.save(path)
            self.assertFalse(path.with_suffix(".json.tmp").exists())
            self.assertTrue(State.load(path).has_sent("INV-1", "firm"))
            self.assertEqual(json.loads(path.read_text())["INV-1"]["sent"][0]["step"], "firm")

    def test_corrupt_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            path.write_text("{not json")
            with self.assertRaisesRegex(ValueError, "corrupt state file"):
                State.load(path)


if __name__ == "__main__":
    unittest.main()
