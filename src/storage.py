"""Primary SQLite and backup JSONL audit storage."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.config import Settings, settings
from src.exceptions import AuditUnavailableError
from src.schemas import AuditStorage, DecisionRecord


class AuditRepository:
    def __init__(self, config: Settings = settings) -> None:
        self.config = config

    def save(self, record: DecisionRecord) -> DecisionRecord:
        try:
            primary_record = record.model_copy(update={"audit_storage": AuditStorage.PRIMARY_SQLITE})
            self._save_sqlite(primary_record)
            return primary_record
        except Exception as primary_error:
            try:
                degradation_events = list(record.degradation_events)
                if "primary_audit_unavailable" not in degradation_events:
                    degradation_events.append("primary_audit_unavailable")
                backup_record = record.model_copy(
                    update={
                        "audit_storage": AuditStorage.BACKUP_JSONL,
                        "degradation_events": degradation_events,
                    }
                )
                self._save_jsonl(backup_record)
                return backup_record
            except Exception as backup_error:
                raise AuditUnavailableError("All audit storages are unavailable.") from backup_error

    def _save_sqlite(self, record: DecisionRecord) -> None:
        path = self.config.primary_audit_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    ticket_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    response_source TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    scope_status TEXT NOT NULL,
                    fallback_reason TEXT,
                    audit_storage TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_ticket_id ON audit_events(ticket_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_session_id ON audit_events(session_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_events(created_at)"
            )
            payload = record.model_dump(mode="json")
            connection.execute(
                """
                INSERT INTO audit_events (
                    event_id,
                    ticket_id,
                    session_id,
                    action,
                    response_source,
                    risk_level,
                    scope_status,
                    fallback_reason,
                    audit_storage,
                    created_at,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(record.event_id),
                    str(record.ticket_id),
                    record.session_id,
                    record.action.value,
                    record.response_source.value,
                    record.risk_level.value,
                    record.scope_status.value,
                    record.fallback_reason.value if record.fallback_reason else None,
                    record.audit_storage.value,
                    record.created_at.isoformat(),
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            connection.commit()

    def _save_jsonl(self, record: DecisionRecord) -> None:
        path = self.config.backup_audit_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = record.model_dump(mode="json")
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")
