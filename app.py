"""Streamlit proof of concept for the support pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - import smoke without optional UI dependency
    st = None

from src.app_factory import build_app_pipeline, build_runtime_collections
from src.config import Settings
from src.demo_components import DEMO_MODES
from src.schemas import (
    AuditStorage,
    DecisionAction,
    DecisionRecord,
    FallbackReason,
    ResponseSource,
    TicketInput,
)
from src.storage import AuditRepository


def create_pipeline(mode_label: str, config: Settings, collections):
    return build_app_pipeline(mode_label, config, collections)


if st is not None:

    @st.cache_resource
    def get_config() -> Settings:
        return Settings()

    @st.cache_resource
    def get_collections(_config: Settings):
        return build_runtime_collections(_config)

else:

    def get_config() -> Settings:
        return Settings()

    def get_collections(config: Settings):
        return build_runtime_collections(config)


def load_demo_tickets() -> list[dict[str, str]]:
    path = Path("data/demo_tickets.json")
    return json.loads(path.read_text(encoding="utf-8"))


def save_feedback_decision(
    decision: DecisionRecord,
    helped: bool,
    config: Settings,
) -> DecisionRecord:
    if helped:
        feedback = decision.model_copy(
            update={
                "resolved_without_operator": True,
                "event_id": uuid4(),
                "decision_id": uuid4(),
                "degradation_events": [*decision.degradation_events, "user_feedback_helped"],
                "audit_storage": AuditStorage.UNAVAILABLE,
            }
        )
    else:
        feedback = DecisionRecord(
            ticket_id=decision.ticket_id,
            session_id=decision.session_id,
            action=DecisionAction.OPERATOR_REVIEW,
            response_source=ResponseSource.OPERATOR,
            risk_level=decision.risk_level,
            scope_status=decision.scope_status,
            fallback_reason=FallbackReason.USER_NOT_HELPED,
            redacted_text=decision.redacted_text,
            pii_detected=decision.pii_detected,
            pii_types=decision.pii_types,
            scope_positive_score=decision.scope_positive_score,
            scope_negative_score=decision.scope_negative_score,
            scope_margin=decision.scope_margin,
            matched_risk_rules=decision.matched_risk_rules,
            retrieval_top_score=decision.retrieval_top_score,
            retrieval_margin=decision.retrieval_margin,
            retrieved_document_ids=decision.retrieved_document_ids,
            answer="Передам обращение специалисту.",
            template_id=decision.template_id,
            llm_used=decision.llm_used,
            llm_attempts=decision.llm_attempts,
            llm_latency_seconds=decision.llm_latency_seconds,
            token_usage=decision.token_usage,
            estimated_cost_usd=decision.estimated_cost_usd,
            resolved_without_operator=False,
            degradation_events=[*decision.degradation_events, "user_not_helped"],
            audit_storage=AuditStorage.UNAVAILABLE,
        )
    return AuditRepository(config).save(feedback)


def trace_items(decision: DecisionRecord) -> dict[str, object]:
    return {
        "ticket_id": str(decision.ticket_id),
        "redacted_text": decision.redacted_text,
        "pii_detected": decision.pii_detected,
        "pii_types": decision.pii_types,
        "scope_status": decision.scope_status.value,
        "positive_scope_score": decision.scope_positive_score,
        "negative_scope_score": decision.scope_negative_score,
        "scope_margin": decision.scope_margin,
        "risk_level": decision.risk_level.value,
        "matched_risk_rules": decision.matched_risk_rules,
        "retrieval_top_score": decision.retrieval_top_score,
        "retrieval_margin": decision.retrieval_margin,
        "retrieved_document_ids": decision.retrieved_document_ids,
        "llm_used": decision.llm_used,
        "llm_attempts": decision.llm_attempts,
        "response_source": decision.response_source.value,
        "template_id": decision.template_id,
        "fallback_reason": decision.fallback_reason.value if decision.fallback_reason else None,
        "degradation_events": decision.degradation_events,
        "audit_storage": decision.audit_storage.value,
        "processing_latency": decision.processing_latency_seconds,
        "llm_latency": decision.llm_latency_seconds,
        "token_usage": decision.token_usage,
        "estimated_cost": decision.estimated_cost_usd,
    }


def main() -> None:
    if st is None:
        raise RuntimeError("Streamlit is not installed. Install requirements.txt to run the UI.")

    st.set_page_config(page_title="Support AI PoC", layout="wide")
    st.title("Support AI PoC")

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "last_decision" not in st.session_state:
        st.session_state.last_decision = None
    if "had_uncertain_without_context" not in st.session_state:
        st.session_state.had_uncertain_without_context = False

    config = get_config()
    collections = get_collections(config)
    mode = st.sidebar.selectbox("Demo mode", list(DEMO_MODES))
    st.sidebar.caption(
        f"retrieval={config.retrieval_score_threshold}, "
        f"template={config.template_score_threshold}, "
        f"scope+={config.scope_positive_threshold}, "
        f"scope-={config.scope_negative_threshold}"
    )
    tickets = load_demo_tickets()
    selected_ticket = st.sidebar.selectbox(
        "Demo ticket",
        tickets,
        format_func=lambda item: item["scenario"],
    )
    if st.sidebar.button("Use demo ticket"):
        st.session_state.pending_text = selected_ticket["text"]

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    user_text = st.chat_input("Опишите проблему")
    if "pending_text" in st.session_state:
        user_text = st.session_state.pop("pending_text")

    if user_text:
        st.session_state.messages.append({"role": "user", "content": user_text})
        with st.chat_message("user"):
            st.write(user_text)

        pipeline = create_pipeline(mode, config, collections)
        decision = pipeline.process(TicketInput(session_id="streamlit-session", channel="web", text=user_text))

        if (
            decision.action == DecisionAction.CLARIFICATION_REQUEST
            and st.session_state.had_uncertain_without_context
        ):
            decision = DecisionRecord(
                ticket_id=decision.ticket_id,
                session_id=decision.session_id,
                action=DecisionAction.OPERATOR_REVIEW,
                response_source=ResponseSource.OPERATOR,
                risk_level=decision.risk_level,
                scope_status=decision.scope_status,
                fallback_reason=FallbackReason.SCOPE_UNCERTAIN,
                redacted_text=decision.redacted_text,
                pii_detected=decision.pii_detected,
                pii_types=decision.pii_types,
                scope_positive_score=decision.scope_positive_score,
                scope_negative_score=decision.scope_negative_score,
                scope_margin=decision.scope_margin,
                matched_risk_rules=decision.matched_risk_rules,
                answer="Передам обращение оператору для уточнения.",
                degradation_events=[*decision.degradation_events, "repeated_uncertain_request"],
                audit_storage=AuditStorage.UNAVAILABLE,
            )
            decision = AuditRepository(config).save(decision)
        elif decision.action == DecisionAction.CLARIFICATION_REQUEST:
            st.session_state.had_uncertain_without_context = True

        assistant_text = decision.answer or ""
        st.session_state.messages.append({"role": "assistant", "content": assistant_text})
        st.session_state.last_decision = decision
        with st.chat_message("assistant"):
            st.write(assistant_text)

    decision = st.session_state.last_decision
    with st.sidebar:
        st.subheader("Decision Trace")
        if decision:
            st.json(trace_items(decision))
        else:
            st.caption("No decision yet.")

    if decision and decision.action in {DecisionAction.AUTO_REPLY, DecisionAction.TEMPLATE_RESPONSE}:
        st.write("Помогло решить проблему?")
        col_yes, col_no = st.columns(2)
        if col_yes.button("Да"):
            saved = save_feedback_decision(decision, helped=True, config=config)
            st.session_state.last_decision = saved
            st.success("Спасибо, отметили обращение как решённое.")
        if col_no.button("Нет"):
            saved = save_feedback_decision(decision, helped=False, config=config)
            st.session_state.last_decision = saved
            st.info("Передам обращение специалисту.")


if __name__ == "__main__":
    main()
