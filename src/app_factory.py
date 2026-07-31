"""Application dependency factory for Streamlit and local runs."""

from __future__ import annotations

from src.answer_validator import AnswerValidator
from src.config import Settings
from src.demo_components import (
    DEMO_MODES,
    DemoLLMClient,
    PrimaryAuditFailureRepository,
    AllAuditFailureRepository,
)
from src.llm_client import OpenRouterClient
from src.pii import PIIMaskingService
from src.pipeline import SupportPipeline
from src.retrieval import KnowledgeRetriever
from src.risk import RiskService
from src.scope import ScopeGate
from src.storage import AuditRepository
from src.templates import TemplateRetriever
from src.vector_store import (
    KNOWLEDGE_COLLECTION,
    SCOPE_COLLECTION,
    TEMPLATE_COLLECTION,
    create_persistent_client,
    populate_all,
)


def build_runtime_collections(config: Settings):
    client = create_persistent_client(config)
    return populate_all(client)


def build_app_pipeline(mode_label: str, config: Settings, collections) -> SupportPipeline:
    mode = DEMO_MODES[mode_label]
    if mode_label == "Normal / Mock success" and config.openrouter_api_key:
        llm_client = OpenRouterClient(config)
    else:
        llm_client = DemoLLMClient(mode.llm_responses)

    if mode.audit_mode == "primary_failure":
        audit_repository = PrimaryAuditFailureRepository(config)
    elif mode.audit_mode == "all_failure":
        audit_repository = AllAuditFailureRepository(config)
    else:
        audit_repository = AuditRepository(config)

    return SupportPipeline(
        pii_service=PIIMaskingService(),
        scope_gate=ScopeGate(collections[SCOPE_COLLECTION], config),
        risk_service=RiskService(),
        knowledge_retriever=KnowledgeRetriever(collections[KNOWLEDGE_COLLECTION], config),
        template_retriever=TemplateRetriever(collections[TEMPLATE_COLLECTION], config),
        llm_client=llm_client,
        answer_validator=AnswerValidator(),
        audit_repository=audit_repository,
        config=config,
    )
