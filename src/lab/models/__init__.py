"""Phase 2: model adapters (LM Studio / OpenAI-compatible cloud) and the advisor runner."""
from .adapter import (
    Completion, DataOrigin, FailureKind, ModelAdapter, ModelCallError, OpenAICompatAdapter, enforce_transfer_policy,
)
from .advisor import PROMPT_VERSION, AdvisorResult, advise, build_messages, to_run_record
from .config import ModelEndpoint, load_endpoints
from .advisor_v3 import MANDATORY_OVERALL, PROMPT_VERSION_V3, advise_v3, build_messages_v3
