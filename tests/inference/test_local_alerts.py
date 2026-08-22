import numpy as np
from video_intelligence_inference.local_alerts import LocalAlertNotifier
from video_intelligence_inference.observer import ObservationWindow, ObserverDecision


def _window() -> ObservationWindow:
    return ObservationWindow(
        sequence=3,
        started_at=10,
        ended_at=19,
        sheet=np.zeros((20, 40, 3), dtype=np.uint8),
    )


def test_local_notifier_beeps_for_triggered_decision() -> None:
    calls: list[str] = []
    notifier = LocalAlertNotifier(beep=lambda: calls.append("beep"))

    notifier(
        _window(),
        ObserverDecision(
            triggered=True,
            confidence=0.9,
            summary="No hard hat visible.",
            first_frame=2,
        ),
    )

    assert calls == ["beep"]


def test_local_notifier_stays_silent_for_clear_decision() -> None:
    calls: list[str] = []
    notifier = LocalAlertNotifier(beep=lambda: calls.append("beep"))

    notifier(
        _window(),
        ObserverDecision(
            triggered=False,
            confidence=0.95,
            summary="No matching event.",
            first_frame=None,
        ),
    )

    assert calls == []
