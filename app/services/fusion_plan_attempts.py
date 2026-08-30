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
        project_id: str = "",
        version_id: str = "",
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        response = str(raw_response or "")
        attempt_id = uuid4().hex
        raw_response_ref = self._write_payload(
            attempt_id, name="raw-response.txt", payload=response
        )
        attempt = {
            "attempt_id": attempt_id,
            "kind": kind,
            "parent_attempt_id": parent_attempt_id,
            "project_id": str(project_id or ""),
            "version_id": str(version_id or ""),
            "input_fingerprint": str(input_fingerprint or ""),
            "provider": str(provider or ""),
            "model": str(model or ""),
            "received_characters": len(response),
            "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(),
            "response_excerpt": response[-self.RESPONSE_EXCERPT_LIMIT :],
            "raw_response_ref": raw_response_ref,
            "recovery_payload_ref": "",
            "status": "received",
            "findings": [],
            "created_at": now,
            "updated_at": now,
        }
        self._write(attempt)
        return attempt

    def save_recovery_payload(self, attempt_id: str, payload: Any) -> dict[str, Any]:
        """Persist a complete creator-editable candidate outside the attempt summary."""
        reference = self._write_payload(
            attempt_id, name="recovery-payload.json", payload=payload
        )
        return self.update(attempt_id, recovery_payload_ref=reference)

    def read_recovery_payload(self, attempt_id: str) -> Any:
        attempt = self.read(attempt_id)
        reference = str(attempt.get("recovery_payload_ref") or "")
        if reference:
            path = self._checked_payload_path(reference)
            with path.open(encoding="utf-8") as handle:
                return json.load(handle)
        raw_path = self._checked_payload_path(str(attempt.get("raw_response_ref") or ""))
        return raw_path.read_text(encoding="utf-8")

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

    def _write_payload(self, attempt_id: str, *, name: str, payload: Any) -> str:
        if not str(attempt_id).isalnum():
            raise ValueError("invalid Fusion Plan Attempt id")
        directory = self._directory / "payloads" / str(attempt_id)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / Path(name).name
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            if isinstance(payload, str) and target.suffix == ".txt":
                temporary.write_text(payload, encoding="utf-8")
            else:
                with temporary.open("w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return str(target.relative_to(self._directory))

    def _checked_payload_path(self, reference: str) -> Path:
        if not reference:
            raise ValueError("Fusion Plan Attempt has no recovery payload")
        path = (self._directory / reference).resolve()
        root = self._directory.resolve()
        if path != root and root not in path.parents:
            raise ValueError("invalid Fusion Plan Attempt payload reference")
        if not path.is_file():
            raise ValueError("Fusion Plan Attempt payload is unavailable")
        return path

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
