"""Application workflows that compose TradePilot domain packages."""

from tradepilot.workflows.real_data_readiness import verify_candidate_pipeline
from tradepilot.workflows.research_run import (
    CandidateResearch,
    build_candidate_research_run,
    evaluate_candidate_research,
)

__all__ = [
    "CandidateResearch",
    "build_candidate_research_run",
    "evaluate_candidate_research",
    "verify_candidate_pipeline",
]
