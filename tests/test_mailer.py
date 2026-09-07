import os
import smtplib
import unittest
from unittest import mock

import helpers
from badcop.mailer import DryRunMailer, Message, SendError, SmtpMailer, build_email


class BuildEmailTests(unittest.TestCase):
    def test_headers_and_body(self):
        cfg = helpers.make_config()
        email = build_email(Message(to="ap@acme.example", subject="Hi", body="Body\n", headers={"X-Test": "1"}), cfg)
        self.assertEqual(email["From"], '"Accounts, Test Studio" <accounts@test.example>')  # comma forces RFC quoting
        self.assertEqual(email["To"], "ap@acme.example")
        self.assertEqual(email["Reply-To"], "me@test.example")
        self.assertEqual(email["Subject"], "Hi")
        self.assertTrue(email["Message-ID"].endswith("@test.example>"))
        self.assertEqual(email["X-Test"], "1")
        self.assertEqual(email.get_content(), "Body\n")


class DryRunMailerTests(unittest.TestCase):
    def test_records_without_sending(self):
        cfg = helpers.make_config()
        m = DryRunMailer()
        mid = m.send(Message(to="a@b.c", subject="s", body="b"), cfg)
        self.assertEqual(len(m.sent), 1)
        self.assertEqual(m.sent[0]["Message-ID"], mid)


class SmtpMailerTests(unittest.TestCase):
    def setUp(self):
        self.cfg = helpers.make_config()
        self.msg = Message(to="a@b.c", subject="s", body="b")

    def test_sends_with_starttls_and_login(self):
        os.environ["TEST_SMTP_PW"] = "pw"
        try:
            with mock.patch("badcop.mailer.smtplib.SMTP") as SMTP:
                smtp = SMTP.return_value.__enter__.return_value
                mid = SmtpMailer().send(self.msg, self.cfg)
                SMTP.assert_called_once_with("smtp.test.example", 2525, timeout=30)
                smtp.starttls.assert_called_once()
                smtp.login.assert_called_once_with("user", "pw")
                sent = smtp.send_message.call_args.args[0]
                self.assertEqual(sent["Message-ID"], mid)
        finally:
            del os.environ["TEST_SMTP_PW"]

    def test_no_tls_no_login_when_not_configured(self):
        cfg = helpers.make_config(smtp={"starttls": False, "username": ""})
        with mock.patch("badcop.mailer.smtplib.SMTP") as SMTP:
            smtp = SMTP.return_value.__enter__.return_value
            SmtpMailer().send(self.msg, cfg)
            smtp.starttls.assert_not_called()
            smtp.login.assert_not_called()

    def test_missing_password_is_a_send_error(self):
        os.environ.pop("TEST_SMTP_PW", None)
        with mock.patch("badcop.mailer.smtplib.SMTP"):
            with self.assertRaisesRegex(SendError, "TEST_SMTP_PW"):
                SmtpMailer().send(self.msg, self.cfg)

    def test_smtp_failures_are_send_errors(self):
        os.environ["TEST_SMTP_PW"] = "pw"
        try:
            for exc in (smtplib.SMTPAuthenticationError(535, b"bad"), ConnectionRefusedError("nope")):
                with self.subTest(exc=exc), mock.patch("badcop.mailer.smtplib.SMTP") as SMTP:
                    SMTP.return_value.__enter__.return_value.send_message.side_effect = exc
                    with self.assertRaisesRegex(SendError, "SMTP error sending to a@b.c"):
                        SmtpMailer().send(self.msg, self.cfg)
        finally:
            del os.environ["TEST_SMTP_PW"]


if __name__ == "__main__":
    unittest.main()
