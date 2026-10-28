"""Canonical deterministic accounting report identity."""

from tradepilot.accounting.models import AccountingContent, AccountingReport
from tradepilot.reporting.canonical import canonical_json_bytes, sha256_hex


def accounting_report_id(content: AccountingContent) -> str:
    return sha256_hex(canonical_json_bytes(content))


def build_accounting_report(content: AccountingContent) -> AccountingReport:
    return AccountingReport(accounting_report_id(content), content)
