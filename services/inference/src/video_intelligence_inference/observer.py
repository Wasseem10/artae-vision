"""Overlapping visual-window sampling and asynchronous VLM observation."""

from __future__ import annotations

import base64
import json
import logging
import math
import queue
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal, Protocol

import cv2
import httpx
import numpy as np
from pydantic import BaseModel, Field, ValidationError, model_validator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ObservationWindow:
    """A chronological contact sheet ready for semantic analysis."""

    sequence: int
    started_at: float
    ended_at: float
    sheet: np.ndarray


class SceneBoundingBox(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def inside_frame(self) -> SceneBoundingBox:
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("Scene bounding box must stay inside the frame")
        return self


class SceneObservation(BaseModel):
    stable_key: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=160)
    kind: Literal["region", "equipment", "display", "tracked_entity", "other"] = "other"
    bounding_box: SceneBoundingBox
    description: str = Field(default="", max_length=1000)
    state: str = Field(default="observed", min_length=1, max_length=160)
    confidence: float = Field(ge=0, le=1)
    attributes: dict[str, object] = Field(default_factory=dict)
    relationships: list[dict[str, object]] = Field(default_factory=list, max_length=20)


class ObserverDecision(BaseModel):
    """Validated structured output returned by a vision-language model."""

    triggered: bool
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = Field(min_length=1, max_length=1000)
    first_frame: int | None = Field(default=None, ge=1)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    scene_observations: list[SceneObservation] = Field(default_factory=list, max_length=50)


class VisionObserverProvider(Protocol):
    """Small provider boundary shared by cloud and no-key implementations."""

    @property
    def name(self) -> str: ...

    def analyze(self, window: ObservationWindow, rule: str) -> ObserverDecision: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class ObserverSnapshot:
    """Thread-safe status copied into the live preview overlay."""

    state: str
    sequence: int | None = None
    decision: ObserverDecision | None = None
    error: str | None = None
    requests_today: int = 0
    request_limit_day: int = 0
    request_limit_minute: int = 0


class OverlappingSheetSampler:
    """Sample frames by time and emit fixed-size windows with overlap."""

    def __init__(
        self,
        *,
        sample_fps: float,
        window_frames: int,
        overlap_frames: int,
        frame_width: int,
        frame_height: int,
        columns: int,
    ) -> None:
        if sample_fps <= 0:
            raise ValueError("sample_fps must be positive")
        if window_frames < 2:
            raise ValueError("window_frames must be at least two")
        if not 0 <= overlap_frames < window_frames:
            raise ValueError("overlap_frames must be smaller than window_frames")

        self._sample_interval = 1.0 / sample_fps
        self._window_frames = window_frames
        self._overlap_frames = overlap_frames
        self._frame_size = (frame_width, frame_height)
        self._columns = columns
        self._frames: list[tuple[float, np.ndarray]] = []
        self._next_sample_at: float | None = None
        self._sequence = 0

    def add(self, frame: np.ndarray, captured_at: float) -> ObservationWindow | None:
        """Add a frame when due and return a completed chronological sheet."""
        if self._next_sample_at is None:
            self._next_sample_at = captured_at
        if captured_at < self._next_sample_at:
            return None

        while self._next_sample_at <= captured_at:
            self._next_sample_at += self._sample_interval

        resized = cv2.resize(frame, self._frame_size, interpolation=cv2.INTER_AREA)
        self._frames.append((captured_at, resized))
        if len(self._frames) < self._window_frames:
            return None

        selected = self._frames[: self._window_frames]
        self._sequence += 1
        window = ObservationWindow(
            sequence=self._sequence,
            started_at=selected[0][0],
            ended_at=selected[-1][0],
            sheet=self._compose_sheet([item[1] for item in selected]),
        )
        self._frames = selected[-self._overlap_frames :] if self._overlap_frames else []
        return window

    def _compose_sheet(self, frames: list[np.ndarray]) -> np.ndarray:
        frame_width, frame_height = self._frame_size
        rows = math.ceil(len(frames) / self._columns)
        sheet = np.zeros(
            (rows * frame_height, self._columns * frame_width, 3),
            dtype=np.uint8,
        )
        for index, frame in enumerate(frames):
            row, column = divmod(index, self._columns)
            x = column * frame_width
            y = row * frame_height
            sheet[y : y + frame_height, x : x + frame_width] = frame
            cv2.rectangle(sheet, (x + 4, y + 4), (x + 48, y + 28), (0, 0, 0), cv2.FILLED)
            cv2.putText(
                sheet,
                str(index + 1),
                (x + 12, y + 23),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
        return sheet


class QwenVisionClient:
    """Call Qwen's OpenAI-compatible vision endpoint with one contact sheet."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        client: httpx.Client | None = None,
    ) -> None:
        self._model = model
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_seconds,
        )

    @property
    def name(self) -> str:
        return self._model

    def analyze(self, window: ObservationWindow, rule: str) -> ObserverDecision:
        success, encoded = cv2.imencode(".jpg", window.sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not success:
            raise RuntimeError("Could not encode observation sheet as JPEG")

        data_url = "data:image/jpeg;base64," + base64.b64encode(encoded).decode("ascii")
        prompt = (
            "The image is a chronological contact sheet. Frame numbers increase left-to-right "
            "and then top-to-bottom. Evaluate only visible evidence.\n\n"
            f"Rule: {rule}\n\n"
            "Return JSON with exactly these fields: triggered (boolean), confidence (0 to 1), "
            "summary (short string), first_frame (integer or null), and scene_observations "
            "(an array of stable visible regions/equipment/entities). Each scene observation "
            "has stable_key, label, kind, normalized bounding_box {x,y,width,height}, "
            "description, state, confidence, attributes, and relationships. Use an empty array "
            "when no stable scene item can be identified."
        )
        response = self._client.post(
            "/chat/completions",
            json={
                "model": self._model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
                "response_format": {"type": "json_object"},
                "enable_thinking": False,
                "max_tokens": 200,
            },
        )
        response.raise_for_status()
        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("response content is not a string")
            decision = ObserverDecision.model_validate(json.loads(_strip_code_fence(content)))
            usage = payload.get("usage", {})
            return decision.model_copy(
                update={
                    "input_tokens": int(usage.get("prompt_tokens", 0) or 0),
                    "output_tokens": int(usage.get("completion_tokens", 0) or 0),
                }
            )
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as error:
            raise RuntimeError("Qwen returned an invalid observer response") from error

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


class GeminiVisionClient:
    """Call Google's Gemini API with one chronological contact sheet."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        client: httpx.Client | None = None,
    ) -> None:
        self._model = model
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"x-goog-api-key": api_key},
            timeout=timeout_seconds,
        )

    @property
    def name(self) -> str:
        return self._model

    def analyze(self, window: ObservationWindow, rule: str) -> ObserverDecision:
        success, encoded = cv2.imencode(".jpg", window.sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not success:
            raise RuntimeError("Could not encode observation sheet as JPEG")

        prompt = (
            "The image is a chronological contact sheet. Frame numbers increase left-to-right "
            "and then top-to-bottom. Evaluate only visible evidence. Do not infer an event that "
            "is not visible.\n\n"
            f"Rule: {rule}\n\n"
            "Decide whether the rule occurred anywhere in the sheet. first_frame is the earliest "
            "numbered frame showing the event, or null when it did not occur. Also return stable "
            "visible regions, equipment, displays, and tracked entities in scene_observations; "
            "use normalized bounding boxes and an empty array when none are reliable."
        )
        response = self._client.post(
            f"/models/{self._model}:generateContent",
            json={
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": prompt},
                            {
                                "inlineData": {
                                    "mimeType": "image/jpeg",
                                    "data": base64.b64encode(encoded).decode("ascii"),
                                }
                            },
                        ],
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseJsonSchema": {
                        "type": "object",
                        "properties": {
                            "triggered": {"type": "boolean"},
                            "confidence": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                            },
                            "summary": {"type": "string", "maxLength": 1000},
                            "first_frame": {
                                "anyOf": [
                                    {"type": "integer", "minimum": 1},
                                    {"type": "null"},
                                ]
                            },
                            "scene_observations": {
                                "type": "array",
                                "maxItems": 50,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "stable_key": {"type": "string"},
                                        "label": {"type": "string"},
                                        "kind": {
                                            "type": "string",
                                            "enum": [
                                                "region",
                                                "equipment",
                                                "display",
                                                "tracked_entity",
                                                "other",
                                            ],
                                        },
                                        "bounding_box": {
                                            "type": "object",
                                            "properties": {
                                                "x": {"type": "number"},
                                                "y": {"type": "number"},
                                                "width": {"type": "number"},
                                                "height": {"type": "number"},
                                            },
                                            "required": ["x", "y", "width", "height"],
                                        },
                                        "description": {"type": "string"},
                                        "state": {"type": "string"},
                                        "confidence": {"type": "number"},
                                        "attributes": {"type": "object"},
                                        "relationships": {"type": "array"},
                                    },
                                    "required": [
                                        "stable_key",
                                        "label",
                                        "kind",
                                        "bounding_box",
                                        "description",
                                        "state",
                                        "confidence",
                                        "attributes",
                                        "relationships",
                                    ],
                                },
                            },
                        },
                        "required": [
                            "triggered",
                            "confidence",
                            "summary",
                            "first_frame",
                            "scene_observations",
                        ],
                        "additionalProperties": False,
                    },
                    "maxOutputTokens": 200,
                    "thinkingConfig": {"thinkingLevel": "MINIMAL"},
                },
            },
        )
        response.raise_for_status()
        try:
            payload = response.json()
            parts = payload["candidates"][0]["content"]["parts"]
            content = "".join(part.get("text", "") for part in parts)
            if not content:
                raise TypeError("response content is empty")
            decision = ObserverDecision.model_validate_json(_strip_code_fence(content))
        except (KeyError, IndexError, TypeError, ValidationError) as error:
            raise RuntimeError("Gemini returned an invalid observer response") from error

        usage = payload.get("usageMetadata", {})
        if usage:
            logger.info(
                "Gemini usage prompt=%s output=%s thinking=%s total=%s",
                usage.get("promptTokenCount"),
                usage.get("candidatesTokenCount"),
                usage.get("thoughtsTokenCount"),
                usage.get("totalTokenCount"),
            )
        return decision.model_copy(
            update={
                "input_tokens": int(usage.get("promptTokenCount", 0) or 0),
                "output_tokens": int(usage.get("candidatesTokenCount", 0) or 0),
            }
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


class DryRunVisionClient:
    """Produce predictable decisions while exercising the full pipeline without a key."""

    def __init__(self, trigger_every: int = 3) -> None:
        if trigger_every < 1:
            raise ValueError("trigger_every must be at least one")
        self._trigger_every = trigger_every

    @property
    def name(self) -> str:
        return "dry-run"

    def analyze(self, window: ObservationWindow, rule: str) -> ObserverDecision:
        triggered = window.sequence % self._trigger_every == 0
        return ObserverDecision(
            triggered=triggered,
            confidence=0.99 if triggered else 0.95,
            summary=(
                f"Simulated alert for rule: {rule}"
                if triggered
                else "Dry-run window completed; no simulated alert."
            ),
            first_frame=1 if triggered else None,
        )

    def close(self) -> None:
        return None


class RequestBudget:
    """Enforce hard per-minute and per-day provider request ceilings."""

    def __init__(self, *, per_minute: int, per_day: int) -> None:
        if per_minute < 1 or per_day < 1:
            raise ValueError("request budgets must be positive")
        self._per_minute = per_minute
        self._per_day = per_day
        self._recent: deque[float] = deque()
        self._day = datetime.now(UTC).date()
        self._daily_count = 0

    @property
    def daily_count(self) -> int:
        return self._daily_count

    @property
    def per_day(self) -> int:
        return self._per_day

    @property
    def per_minute(self) -> int:
        return self._per_minute

    def acquire(
        self, *, now_monotonic: float, today: date | None = None
    ) -> tuple[bool, str | None]:
        current_day = today or datetime.now(UTC).date()
        if current_day != self._day:
            self._day = current_day
            self._daily_count = 0
            self._recent.clear()

        cutoff = now_monotonic - 60.0
        while self._recent and self._recent[0] <= cutoff:
            self._recent.popleft()
        if self._daily_count >= self._per_day:
            return False, "daily request budget reached"
        if len(self._recent) >= self._per_minute:
            return False, "per-minute request budget reached"

        self._recent.append(now_monotonic)
        self._daily_count += 1
        return True, None


class ObserverArtifactSink:
    """Persist exactly what the provider saw plus its validated decision."""

    def __init__(self, directory: Path, mode: Literal["none", "triggered", "all"]) -> None:
        self._directory = directory.expanduser().resolve()
        self._mode = mode

    def write(
        self,
        *,
        provider: str,
        rule: str,
        window: ObservationWindow,
        decision: ObserverDecision,
    ) -> tuple[Path, Path] | None:
        if self._mode == "none" or (self._mode == "triggered" and not decision.triggered):
            return None

        self._directory.mkdir(parents=True, exist_ok=True)
        stem = f"window-{window.sequence:06d}"
        sheet_path = self._directory / f"{stem}.jpg"
        decision_path = self._directory / f"{stem}.json"
        if not cv2.imwrite(str(sheet_path), window.sheet, [cv2.IMWRITE_JPEG_QUALITY, 90]):
            raise RuntimeError(f"Could not persist observer sheet at {sheet_path}")

        payload = {
            "schema_version": 1,
            "provider": provider,
            "rule": rule,
            "sequence": window.sequence,
            "window_started_at_seconds": window.started_at,
            "window_ended_at_seconds": window.ended_at,
            "recorded_at": datetime.now(UTC).isoformat(),
            "sheet_path": str(sheet_path),
            "decision": decision.model_dump(mode="json"),
        }
        decision_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        logger.info("Observer artifact persisted: %s", decision_path)
        return sheet_path, decision_path


class ContinuousObserver:
    """Analyze completed sheets without delaying camera capture or YOLO."""

    def __init__(
        self,
        provider: VisionObserverProvider,
        rule: str,
        *,
        queue_size: int = 2,
        max_requests_per_minute: int = 1,
        max_requests_per_day: int = 20,
        artifact_sink: ObserverArtifactSink | None = None,
        on_decision: Callable[[ObservationWindow, ObserverDecision], None] | None = None,
    ) -> None:
        self._provider = provider
        self._rule = rule
        self._budget = RequestBudget(
            per_minute=max_requests_per_minute,
            per_day=max_requests_per_day,
        )
        self._artifact_sink = artifact_sink
        self._on_decision = on_decision
        self._queue: queue.Queue[ObservationWindow | None] = queue.Queue(maxsize=queue_size)
        self._lock = threading.Lock()
        self._snapshot = ObserverSnapshot(state="collecting")
        self._thread = threading.Thread(
            target=self._run,
            name="continuous-vlm-observer",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def submit(self, window: ObservationWindow) -> None:
        try:
            self._queue.put_nowait(window)
        except queue.Full:
            try:
                dropped = self._queue.get_nowait()
                self._queue.task_done()
                logger.warning(
                    "Observer is behind; dropping window %s",
                    dropped.sequence if dropped is not None else "shutdown",
                )
            except queue.Empty:
                pass
            self._queue.put_nowait(window)
        with self._lock:
            # Keep the last completed decision visible while a newer sheet is queued.
            # Without this, a useful alert can disappear from the preview almost
            # immediately when overlapping windows are enabled.
            self._snapshot = ObserverSnapshot(
                state="queued",
                sequence=window.sequence,
                decision=self._snapshot.decision,
            )

    def snapshot(self) -> ObserverSnapshot:
        with self._lock:
            snapshot = self._snapshot
            return ObserverSnapshot(
                state=snapshot.state,
                sequence=snapshot.sequence,
                decision=snapshot.decision,
                error=snapshot.error,
                requests_today=self._budget.daily_count,
                request_limit_day=self._budget.per_day,
                request_limit_minute=self._budget.per_minute,
            )

    def close(self) -> None:
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                pass
            self._queue.put_nowait(None)
        self._thread.join(timeout=5)
        self._provider.close()

    def _run(self) -> None:
        while True:
            window = self._queue.get()
            try:
                if window is None:
                    return
                with self._lock:
                    self._snapshot = ObserverSnapshot(
                        state="analyzing",
                        sequence=window.sequence,
                        decision=self._snapshot.decision,
                    )
                allowed, reason = self._budget.acquire(now_monotonic=window.ended_at)
                if not allowed:
                    logger.warning("Observer window=%d skipped: %s", window.sequence, reason)
                    with self._lock:
                        self._snapshot = ObserverSnapshot(
                            state="budget-limited",
                            sequence=window.sequence,
                            decision=self._snapshot.decision,
                            error=reason,
                        )
                    continue
                decision = self._provider.analyze(window, self._rule)
                if self._artifact_sink is not None:
                    self._artifact_sink.write(
                        provider=self._provider.name,
                        rule=self._rule,
                        window=window,
                        decision=decision,
                    )
                with self._lock:
                    self._snapshot = ObserverSnapshot(
                        state="complete",
                        sequence=window.sequence,
                        decision=decision,
                    )
                logger.info(
                    "Observer window=%d triggered=%s confidence=%.2f summary=%s",
                    window.sequence,
                    decision.triggered,
                    decision.confidence,
                    decision.summary,
                )
                if self._on_decision is not None:
                    self._on_decision(window, decision)
            except Exception as error:
                logger.exception("Observer window failed")
                with self._lock:
                    self._snapshot = ObserverSnapshot(
                        state="error",
                        sequence=window.sequence if window is not None else None,
                        error=str(error),
                    )
            finally:
                self._queue.task_done()


def _strip_code_fence(value: str) -> str:
    stripped = value.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines:
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
