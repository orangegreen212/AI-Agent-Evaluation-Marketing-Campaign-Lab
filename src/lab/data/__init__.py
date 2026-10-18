"""Phase 1: CSV validation and deterministic analytics."""
from .analytics import Analysis, DataNotAnalyzableError, MetricResult, MetricStatus, Totals, analyze_csv, compute_group_metrics
from .validation import IssueCode, IssueSeverity, ValidationIssue, ValidationResult, validate_csv
