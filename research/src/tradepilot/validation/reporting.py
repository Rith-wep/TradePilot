"""Canonical deterministic validation-report identity."""

from tradepilot.reporting.canonical import canonical_json_bytes, sha256_hex
from tradepilot.validation.models import ValidationContent, ValidationReport


def validation_report_id(content: ValidationContent) -> str:
    return sha256_hex(canonical_json_bytes(content))


def build_validation_report(content: ValidationContent) -> ValidationReport:
    return ValidationReport(validation_report_id(content), content)
