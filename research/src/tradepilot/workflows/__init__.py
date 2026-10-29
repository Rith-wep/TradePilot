"""Application workflows that compose TradePilot domain packages."""

from tradepilot.workflows.real_data_readiness import verify_candidate_pipeline

__all__ = ["verify_candidate_pipeline"]
