"""Small local alert boundary for the standalone camera playground."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

from video_intelligence_inference.observer import ObservationWindow, ObserverDecision

logger = logging.getLogger(__name__)


def _default_beep() -> None:
    """Play a native Windows alert when available without adding a dependency."""
    if os.name != "nt":
        return

    import winsound

    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)


class LocalAlertNotifier:
    """Report triggered semantic decisions in the terminal and through a sound."""

    def __init__(self, beep: Callable[[], None] = _default_beep) -> None:
        self._beep = beep

    def __call__(self, window: ObservationWindow, decision: ObserverDecision) -> None:
        if not decision.triggered:
            return

        logger.warning(
            "LOCAL ALERT window=%d confidence=%.2f first_frame=%s summary=%s",
            window.sequence,
            decision.confidence,
            decision.first_frame,
            decision.summary,
        )
        try:
            self._beep()
        except (OSError, RuntimeError):
            logger.warning("Could not play the local alert sound", exc_info=True)
