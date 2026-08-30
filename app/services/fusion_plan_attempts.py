"""Durable, non-authoritative records for Fusion Segment Plan responses."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Any
from uuid import uuid4


class FusionPlanRecoveryRequired(RuntimeError):
    """Signal that completed planning work requires creator review."""

    status = "waiting_for_review"

    def __init__(self, message: str, *, attempt_id: str, findings: list[dict]):
        super().__init__(message)
        self.attempt_id = attempt_id
        self.findings = findings

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "attempt_id": self.attempt_id,
            "message": str(self),
            "findings": self.findings,
        }


class FusionPlanAttemptStore:
    """Persist bounded planning evidence with atomic local writes."""

    RESPONSE_EXCERPT_LIMIT = 4000

    def __init__(self, directory: Path) -> None:
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        *,
        raw_response: str,
        input_fingerprint: str,
        provider: str = "",
        model: str = "",
        kind: str = "generation",
        parent_attempt_id: str = "",
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        response = str(raw_response or "")
        attempt = {
            "attempt_id": uuid4().hex,
            "kind": kind,
            "parent_attempt_id": parent_attempt_id,
            "input_fingerprint": str(input_fingerprint or ""),
            "provider": str(provider or ""),
            "model": str(model or ""),
            "received_characters": len(response),
            "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(),
            "response_excerpt": response[-self.RESPONSE_EXCERPT_LIMIT :],
            "status": "received",
            "findings": [],
            "created_at": now,
            "updated_at": now,
        }
        self._write(attempt)
        return attempt

    def update(self, attempt_id: str, **changes: Any) -> dict[str, Any]:
        attempt = self.read(attempt_id)
        attempt.update(changes)
        attempt["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write(attempt)
        return attempt

    def read(self, attempt_id: str) -> dict[str, Any]:
        with self._path(attempt_id).open(encoding="utf-8") as handle:
            return json.load(handle)

    def list_attempts(self) -> list[dict[str, Any]]:
        attempts = []
        for path in self._directory.glob("*.json"):
            try:
                with path.open(encoding="utf-8") as handle:
                    attempts.append(json.load(handle))
            except (OSError, json.JSONDecodeError):
                continue
        return sorted(attempts, key=lambda item: str(item.get("created_at") or ""))

    def _path(self, attempt_id: str) -> Path:
        if not str(attempt_id).isalnum():
            raise ValueError("invalid Fusion Plan Attempt id")
        return self._directory / f"{attempt_id}.json"

    def _write(self, attempt: dict[str, Any]) -> None:
        path = self._path(str(attempt["attempt_id"]))
        temporary = path.with_name(f"{path.stem}.{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(attempt, handle, ensure_ascii=False, indent=2)
            for retry in range(5):
                try:
                    temporary.replace(path)
                    return
                except PermissionError:
                    if retry == 4:
                        raise
                    time.sleep(0.01)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
