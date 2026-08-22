"""Artae Labs integration for the AI video intelligence platform."""

from video_intelligence_artae.client import ArtaeLabsClient
from video_intelligence_artae.config import ArtaeLabsSettings
from video_intelligence_artae.models import LabsIndex, LabsVideo, SearchHit, SearchResponse

__all__ = [
    "ArtaeLabsClient",
    "ArtaeLabsSettings",
    "LabsIndex",
    "LabsVideo",
    "SearchHit",
    "SearchResponse",
]

__version__ = "0.2.0"
