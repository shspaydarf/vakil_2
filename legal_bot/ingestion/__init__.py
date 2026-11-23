"""MACHINA legal-document ingestion architecture (staging only)."""
from .models import CandidateDocument, DiscoveryBatch, DiscoveryStatus

__all__ = ["CandidateDocument", "DiscoveryBatch", "DiscoveryStatus"]

# Phase 5.2 isolated candidate package API.
from .staging_packages import create_candidate_package, validate_candidate  # noqa: E402,F401
