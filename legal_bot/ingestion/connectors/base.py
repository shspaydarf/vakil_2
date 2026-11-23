# -*- coding: utf-8 -*-
"""Connector contract. Concrete source parsers must be fixture-testable."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable
from ..models import CandidateDocument, DiscoveryBatch
from ..policy import ConnectorPolicy

@dataclass(frozen=True)
class SourceDefinition:
    source_id: str
    source_name: str
    base_url: str
    allowed_hosts: frozenset[str]
    source_role: str

class SourceConnector(ABC):
    definition: SourceDefinition

    def __init__(self, policy: ConnectorPolicy | None = None):
        self.policy = policy or ConnectorPolicy()

    @abstractmethod
    def discover_from_html(self, html: str, page_url: str, *, category: str) -> Iterable[CandidateDocument]:
        """Parse saved HTML only; must not perform network I/O or write corpus data."""

    def make_batch(self, category: str, candidates: Iterable[CandidateDocument], *, pages_seen: int = 1) -> DiscoveryBatch:
        items = list(candidates)[:self.policy.max_candidates]
        return DiscoveryBatch(source_id=self.definition.source_id, category=category,
                              candidates=items, pages_seen=min(pages_seen, self.policy.max_pages))
