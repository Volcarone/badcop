import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import helpers
from badcop.config import DEFAULT_STEPS, ConfigError, load_config, parse_config


class ParseConfigTests(unittest.TestCase):
    def test_full_config_parses(self):
        cfg = helpers.make_config()
        self.assertEqual(cfg.sender_email, "accounts@test.example")
        self.assertEqual(cfg.reply_to, "me@test.example")
        self.assertEqual(cfg.owner_email, "owner@test.example")
        self.assertEqual(cfg.smtp_port, 2525)
        self.assertEqual(cfg.late_fee_pct, Decimal("1.5"))
        self.assertEqual([s.name for s in cfg.steps], ["courtesy", "friendly", "firm", "final", "escalate"])
        self.assertTrue(cfg.steps[3].apply_late_fee)
        self.assertTrue(cfg.steps[4].notify_owner)

    def test_minimal_config_uses_defaults(self):
        cfg = parse_config({"sender": {"name": "A", "email": "a@b.c"}}, Path("/base"))
        self.assertEqual(cfg.reply_to, "a@b.c")
        self.assertEqual(cfg.owner_email, "a@b.c")
        self.assertEqual(cfg.net_days, 14)
        self.assertEqual(cfg.late_fee_pct, Decimal("0"))
        self.assertEqual(cfg.steps, list(DEFAULT_STEPS))
        self.assertEqual(cfg.templates_dir, Path("/base/templates"))

    def test_absolute_templates_dir_is_kept(self):
        cfg = helpers.make_config(behaviour={"templates_dir": "/abs/tpl"})
        self.assertEqual(cfg.templates_dir, Path("/abs/tpl"))

    def test_missing_sender_fields(self):
        with self.assertRaises(ConfigError):
            parse_config({"sender": {"name": "A"}}, Path("."))
        with self.assertRaises(ConfigError):
            parse_config({"sender": {"name": "", "email": "a@b.c"}}, Path("."))
        with self.assertRaises(ConfigError):
            parse_config({"sender": {"name": "A", "email": "not-an-email"}}, Path("."))

    def test_steps_are_sorted_by_offset(self):
        cfg = helpers.make_config(steps=[{"offset_days": 7, "name": "b"}, {"offset_days": -1, "name": "a"}])
        self.assertEqual([s.name for s in cfg.steps], ["a", "b"])

    def test_step_validation(self):
        with self.assertRaises(ConfigError):
            helpers.make_config(steps=[])
        with self.assertRaises(ConfigError):
            helpers.make_config(steps=[{"offset_days": "soon", "name": "x"}])
        with self.assertRaises(ConfigError):
            helpers.make_config(steps=[{"offset_days": 1, "name": "x"}, {"offset_days": 2, "name": "x"}])
        cfg = helpers.make_config(steps=[{"offset_days": 1}, {"offset_days": 2}])
        self.assertEqual([s.name for s in cfg.steps], ["step1", "step2"])

    def test_numeric_validation(self):
        with self.assertRaises(ConfigError):
            helpers.make_config(terms={"late_fee_pct": "lots"})
        with self.assertRaises(ConfigError):
            helpers.make_config(terms={"late_fee_pct": -1})
        with self.assertRaises(ConfigError):
            helpers.make_config(terms={"net_days": 1.5})
        with self.assertRaises(ConfigError):
            helpers.make_config(smtp={"port": True})

    def test_smtp_password_comes_from_environment(self):
        cfg = helpers.make_config()
        os.environ.pop("TEST_SMTP_PW", None)
        self.assertIsNone(cfg.smtp_password)
        os.environ["TEST_SMTP_PW"] = "secret"
        try:
            self.assertEqual(cfg.smtp_password, "secret")
        finally:
            del os.environ["TEST_SMTP_PW"]


class LoadConfigTests(unittest.TestCase):
    def test_load_from_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "badcop.toml"
            p.write_text('[sender]\nname="A"\nemail="a@b.c"\n[[steps]]\noffset_days=1\nname="one"\n')
            cfg = load_config(p)
            self.assertEqual(cfg.steps[0].name, "one")
            self.assertEqual(cfg.templates_dir, Path(d).resolve() / "templates")

    def test_missing_file(self):
        with self.assertRaises(ConfigError):
            load_config(Path("/nonexistent/badcop.toml"))

    def test_invalid_toml(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "badcop.toml"
            p.write_text("[sender\nname=")
            with self.assertRaises(ConfigError):
                load_config(p)


if __name__ == "__main__":
    unittest.main()
