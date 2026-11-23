"""Read-only discovery connectors for public legal sources."""
from .base import SourceConnector, SourceDefinition
from .ekhtebar import EkhtebarUnityRulingsConnector
from .majles_rc import MajlesResearchCenterConnector
from .official_candidates import DoticRegulationsConnector, OfficialGazetteConnector, JudiciaryPortalConnector
from .qavanin import QavaninConnector

__all__ = ["SourceConnector", "SourceDefinition", "EkhtebarUnityRulingsConnector", "MajlesResearchCenterConnector",
           "DoticRegulationsConnector", "OfficialGazetteConnector", "JudiciaryPortalConnector", "QavaninConnector"]
