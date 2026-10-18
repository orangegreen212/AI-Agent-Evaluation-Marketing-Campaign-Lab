"""All enums of the contract layer. Unknown values are rejected by validation."""
from enum import StrEnum


class AgentStatus(StrEnum):
    RECOMMEND = "RECOMMEND"
    CAUTION = "CAUTION"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    REFUSE = "REFUSE"


class RunStatus(StrEnum):
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"


class TestVerdict(StrEnum):
    __test__ = False
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"
    ERROR = "ERROR"


class AggregateStatus(StrEnum):
    BLOCKED = "BLOCKED"
    INCOMPLETE = "INCOMPLETE"
    FLAKY = "FLAKY"
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"
    ERROR = "ERROR"


class ModelProfileStatus(StrEnum):
    ALLOWED = "ALLOWED"
    UNDER_REVIEW = "UNDER_REVIEW"
    BLOCKED = "BLOCKED"


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"


class TestCategory(StrEnum):
    __test__ = False
    EVALUATION = "EVALUATION"
    SECURITY = "SECURITY"
    PRIVACY = "PRIVACY"
    ETHICS = "ETHICS"
    BIAS = "BIAS"


class DetectionMethod(StrEnum):
    CODE = "CODE"
    LLM_JUDGE = "LLM_JUDGE"
    HUMAN = "HUMAN"


class Confirmer(StrEnum):
    """Who may confirm a finding. LLM_JUDGE is deliberately absent."""

    CODE = "CODE"
    HUMAN = "HUMAN"


class ConfirmationStatus(StrEnum):
    UNCONFIRMED = "UNCONFIRMED"
    CONFIRMED = "CONFIRMED"
    DISMISSED = "DISMISSED"


class RemediationStatus(StrEnum):
    OPEN = "OPEN"
    FIXED = "FIXED"
    RETESTED_OK = "RETESTED_OK"


class EvaluatorType(StrEnum):
    RULE = "RULE"
    LLM_JUDGE = "LLM_JUDGE"
    HUMAN = "HUMAN"


class EvaluationResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class TriggerSource(StrEnum):
    """Provenance of a tool call, assigned by the orchestrator."""

    USER_REQUEST = "USER_REQUEST"
    MODEL_PLAN = "MODEL_PLAN"
    UNTRUSTED_DATA = "UNTRUSTED_DATA"


class ModelProvider(StrEnum):
    LOCAL = "LOCAL"
    CLOUD = "CLOUD"


class StructuredOutputMode(StrEnum):
    NONE = "NONE"
    JSON_MODE = "JSON_MODE"
    SCHEMA = "SCHEMA"


class AssertionType(StrEnum):
    AGENT_STATUS_IS = "AGENT_STATUS_IS"
    METRIC_MATCHES_EXPECTED = "METRIC_MATCHES_EXPECTED"
    NO_INVENTED_VALUE = "NO_INVENTED_VALUE"
    NO_CANARY_IN_OUTPUT = "NO_CANARY_IN_OUTPUT"
    NO_EXECUTED_FORBIDDEN_TOOL = "NO_EXECUTED_FORBIDDEN_TOOL"
    LIMITATIONS_PRESENT = "LIMITATIONS_PRESENT"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    DECISION_STABLE_FOR_COMPARABLE_INPUTS = "DECISION_STABLE_FOR_COMPARABLE_INPUTS"
    CUSTOM_CODE_CHECK = "CUSTOM_CODE_CHECK"
