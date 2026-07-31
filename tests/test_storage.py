import json
import sqlite3

from src.config import Settings
from src.schemas import (
    AuditStorage,
    DecisionAction,
    DecisionRecord,
    ResponseSource,
    RiskLevel,
    ScopeStatus,
)
from src.storage import AuditRepository


def decision() -> DecisionRecord:
    return DecisionRecord(
        ticket_id="00000000-0000-0000-0000-000000000001",
        session_id="session-1",
        action=DecisionAction.AUTO_REPLY,
        response_source=ResponseSource.RAG_LLM,
        risk_level=RiskLevel.LOW,
        scope_status=ScopeStatus.IN_SCOPE,
        redacted_text="Письмо не приходит на [EMAIL_1]",
        answer="Проверьте папку спам.",
        citations=["kb-reset-email-missing"],
        audit_storage=AuditStorage.UNAVAILABLE,
    )


def test_sqlite_audit_saves_indexed_fields(test_config: Settings) -> None:
    saved = AuditRepository(test_config).save(decision())

    assert saved.audit_storage == AuditStorage.PRIMARY_SQLITE
    with sqlite3.connect(test_config.primary_audit_path) as connection:
        row = connection.execute(
            "SELECT ticket_id, action, response_source, risk_level, scope_status FROM audit_events"
        ).fetchone()

    assert row == (
        "00000000-0000-0000-0000-000000000001",
        "AUTO_REPLY",
        "RAG_LLM",
        "LOW",
        "IN_SCOPE",
    )


def test_jsonl_backup_used_when_primary_fails(test_config: Settings) -> None:
    class BackupOnlyAuditRepository(AuditRepository):
        def _save_sqlite(self, record: DecisionRecord) -> None:
            raise OSError("sqlite unavailable")

    saved = BackupOnlyAuditRepository(test_config).save(decision())

    assert saved.audit_storage == AuditStorage.BACKUP_JSONL
    payload = json.loads(test_config.backup_audit_path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["redacted_text"] == "Письмо не приходит на [EMAIL_1]"
    assert "primary_audit_unavailable" in payload["degradation_events"]
