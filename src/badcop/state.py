"""Send log. Guarantees a step is never sent twice for the same invoice."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class State:
    def __init__(self, data: dict | None = None) -> None:
        self.data: dict[str, dict] = data or {}

    @classmethod
    def load(cls, path: Path) -> "State":
        if not path.exists():
            return cls()
        try:
            return cls(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}: corrupt state file: {e}") from e

    def save(self, path: Path) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)

    def _entry(self, invoice_id: str) -> dict:
        return self.data.setdefault(invoice_id, {"sent": [], "last_error": None})

    def has_sent(self, invoice_id: str, step: str) -> bool:
        return any(s["step"] == step for s in self.data.get(invoice_id, {}).get("sent", []))

    def sent_steps(self, invoice_id: str) -> list[str]:
        return [s["step"] for s in self.data.get(invoice_id, {}).get("sent", [])]

    def record_sent(self, invoice_id: str, step: str, message_id: str, when: datetime | None = None) -> None:
        entry = self._entry(invoice_id)
        entry["sent"].append({"step": step, "sent_at": (when or datetime.now(timezone.utc)).isoformat(),
                              "message_id": message_id})
        entry["last_error"] = None

    def record_error(self, invoice_id: str, error: str) -> None:
        self._entry(invoice_id)["last_error"] = error
