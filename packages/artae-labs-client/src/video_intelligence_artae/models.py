from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LabsModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class LabsIndex(LabsModel):
    id: str
    name: str
    description: str | None = None
    video_count: int = 0
    shot_count: int = 0


class UploadTarget(LabsModel):
    upload_url: str
    upload_key: str
    expires_in_seconds: int


class LabsVideo(LabsModel):
    id: str
    index_id: str
    status: str
    status_progress: int = 0
    title: str | None = None
    error_message: str | None = None
    shot_count: int = 0


class SearchHit(LabsModel):
    shot_id: str
    video_id: str
    shot_index: int
    time_start: float
    time_end: float
    duration_s: float
    similarity: float
    summary: str | None = None
    moment_type: str | None = None
    transcript_chunk: str | None = None
    audio_description: str | None = None
    semantic_events: list[dict[str, Any]] | None = None


class SearchResponse(LabsModel):
    query: str
    count: int
    latency_ms: int
    results: list[SearchHit] = Field(default_factory=list)
