"""CLI demo for the support pipeline in mock mode."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from src.config import Settings
from src.demo_components import build_demo_pipeline
from src.schemas import TicketInput


SCENARIOS = [
    ("happy_path_with_email", "Normal / Mock success"),
    ("high_risk", "Normal / Mock success"),
    ("llm_timeout", "Simulate LLM timeout"),
    ("out_of_scope", "Normal / Mock success"),
    ("uncertain_request", "Normal / Mock success"),
]


def load_demo_tickets() -> dict[str, str]:
    records = json.loads(Path("data/demo_tickets.json").read_text(encoding="utf-8"))
    return {record["scenario"]: record["text"] for record in records}


def safe_trace(decision) -> dict[str, object]:
    return {
        "ticket_id": str(decision.ticket_id),
        "action": decision.action.value,
        "response_source": decision.response_source.value,
        "redacted_text": decision.redacted_text,
        "pii_detected": decision.pii_detected,
        "pii_types": decision.pii_types,
        "scope_status": decision.scope_status.value,
        "risk_level": decision.risk_level.value,
        "matched_risk_rules": decision.matched_risk_rules,
        "retrieved_document_ids": decision.retrieved_document_ids,
        "template_id": decision.template_id,
        "fallback_reason": decision.fallback_reason.value if decision.fallback_reason else None,
        "degradation_events": decision.degradation_events,
        "audit_storage": decision.audit_storage.value,
        "llm_used": decision.llm_used,
        "llm_attempts": decision.llm_attempts,
        "token_usage": decision.token_usage,
        "estimated_cost_usd": decision.estimated_cost_usd,
    }


def main() -> None:
    audit_dir = Path(tempfile.gettempdir()) / "support_ai_demo_audit"
    config = Settings(
        openrouter_api_key="",
        primary_audit_path=audit_dir / "audit.db",
        backup_audit_path=audit_dir / "backup" / "audit_backup.jsonl",
    )
    tickets = load_demo_tickets()

    for scenario, mode in SCENARIOS:
        pipeline = build_demo_pipeline(mode, config)
        decision = pipeline.process(
            TicketInput(
                session_id=f"demo-{scenario}",
                channel="cli",
                text=tickets[scenario],
            )
        )
        print(f"\n=== {scenario} ===")
        print(json.dumps(safe_trace(decision), ensure_ascii=False, indent=2))
        print(f"answer: {decision.answer}")


if __name__ == "__main__":
    main()
