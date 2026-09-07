"""Configuration loading and validation (badcop.toml)."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path


class ConfigError(ValueError):
    """The configuration file is missing, malformed, or inconsistent."""


@dataclass(frozen=True)
class Step:
    """One rung of the reminder ladder, relative to the due date."""
    name: str
    offset_days: int
    apply_late_fee: bool = False
    notify_owner: bool = False  # send this step to the owner instead of the client


DEFAULT_STEPS = (
    Step("courtesy", -3),
    Step("friendly", 1),
    Step("firm", 7),
    Step("final", 14, apply_late_fee=True),
    Step("escalate", 30, notify_owner=True),
)


@dataclass
class Config:
    sender_name: str
    sender_email: str
    reply_to: str
    owner_email: str
    owner_name: str = ""
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password_env: str = "BADCOP_SMTP_PASSWORD"
    smtp_starttls: bool = True
    currency: str = "USD"
    net_days: int = 14
    grace_days: int = 3
    late_fee_pct: Decimal = Decimal("0")
    late_fee_flat: Decimal = Decimal("0")
    catch_up: bool = False
    templates_dir: Path = Path("templates")
    steps: list[Step] = field(default_factory=lambda: list(DEFAULT_STEPS))

    @property
    def smtp_password(self) -> str | None:
        return os.environ.get(self.smtp_password_env) if self.smtp_password_env else None


def _decimal(section: dict, key: str, default: str, where: str) -> Decimal:
    raw = section.get(key, default)
    try:
        value = Decimal(str(raw))
    except InvalidOperation as e:
        raise ConfigError(f"[{where}].{key} must be a number, got {raw!r}") from e
    if value < 0:
        raise ConfigError(f"[{where}].{key} must not be negative")
    return value


def _int(section: dict, key: str, default: int | None, where: str) -> int:
    raw = section.get(key, default)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ConfigError(f"[{where}].{key} must be an integer, got {raw!r}")
    return raw


def parse_config(data: dict, base_dir: Path) -> Config:
    sender, smtp = data.get("sender", {}), data.get("smtp", {})
    terms, behaviour = data.get("terms", {}), data.get("behaviour", {})
    for key in ("name", "email"):
        if not str(sender.get(key, "")).strip():
            raise ConfigError(f"[sender].{key} is required")
    if "@" not in sender["email"]:
        raise ConfigError("[sender].email is not an email address")

    raw_steps = data.get("steps")
    if raw_steps is None:
        steps = list(DEFAULT_STEPS)
    else:
        steps = []
        for i, s in enumerate(raw_steps):
            steps.append(Step(name=str(s.get("name") or f"step{i + 1}"), offset_days=_int(s, "offset_days", None, "steps"),
                              apply_late_fee=bool(s.get("apply_late_fee", False)),
                              notify_owner=bool(s.get("notify_owner", False))))
    if not steps:
        raise ConfigError("at least one [[steps]] entry is required")
    names = [s.name for s in steps]
    if len(set(names)) != len(names):
        raise ConfigError(f"step names must be unique: {names}")
    steps.sort(key=lambda s: s.offset_days)

    reply_to = str(sender.get("reply_to") or sender["email"])
    owner_email = str(sender.get("owner_email") or reply_to)
    templates_dir = Path(str(behaviour.get("templates_dir", "templates")))
    if not templates_dir.is_absolute():
        templates_dir = base_dir / templates_dir

    return Config(
        sender_name=str(sender["name"]).strip(), sender_email=str(sender["email"]).strip(),
        reply_to=reply_to, owner_email=owner_email, owner_name=str(sender.get("owner_name", "")),
        smtp_host=str(smtp.get("host", "localhost")), smtp_port=_int(smtp, "port", 587, "smtp"),
        smtp_username=str(smtp.get("username", "")), smtp_password_env=str(smtp.get("password_env", "BADCOP_SMTP_PASSWORD")),
        smtp_starttls=bool(smtp.get("starttls", True)),
        currency=str(terms.get("currency", "USD")).upper(), net_days=_int(terms, "net_days", 14, "terms"),
        grace_days=_int(terms, "grace_days", 3, "terms"),
        late_fee_pct=_decimal(terms, "late_fee_pct", "0", "terms"), late_fee_flat=_decimal(terms, "late_fee_flat", "0", "terms"),
        catch_up=bool(behaviour.get("catch_up", False)), templates_dir=templates_dir, steps=steps,
    )


def load_config(path: Path) -> Config:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ConfigError(f"config file not found: {path} (run `badcop init` to create one)") from e
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: invalid TOML: {e}") from e
    return parse_config(data, path.resolve().parent)
