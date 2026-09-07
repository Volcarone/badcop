# Contributing

BadCop is a standard-library-only Python project. Keep it that way: a dependency needs a very good reason.

- `python -m unittest discover -s tests` must pass, and new logic needs tests next to the existing ones in `tests/`.
- Business logic lives in `src/badcop/`; the CLI in `cli.py` should stay a thin layer over it.
- Never send email from tests. Use `DryRunMailer` or mock `smtplib.SMTP`.
- Reminder copy changes: keep the defaults firm but courteous. Nothing that reads as a threat, nothing that mentions consequences the user's contract might not allow.
- Open an issue before large changes (new commands, a web UI, integrations) so the scope stays small.
