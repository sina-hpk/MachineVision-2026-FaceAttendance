"""
Registration Module — 6-angle face capture with visual guidance.
Separated from the monitoring pipeline for reliability.
"""

import time
import threading
from typing import Optional, Dict, List
from dataclasses import dataclass, field
import numpy as np
import cv2

# Angle guidance steps
ANGLE_STEPS = [
    ("front", "Look straight ahead", 3),
    ("left", "Turn head left", 3),
    ("right", "Turn head right", 3),
    ("up", "Look up", 3),
    ("down", "Look down", 3),
    ("tilt", "Tilt head slightly", 3),
]


@dataclass
class RegistrationSession:
    """Active registration session state."""
    name: str
    step_index: int = 0
    encodings: List[np.ndarray] = field(default_factory=list)
    face_crops: List[np.ndarray] = field(default_factory=list)
    step_start_time: float = 0.0
    is_active: bool = True
    result_message: str = ""

    @property
    def current_step(self) -> str:
        if self.step_index >= len(ANGLE_STEPS):
            return "done"
        return ANGLE_STEPS[self.step_index][0]

    @property
    def current_guide(self) -> str:
        if self.step_index >= len(ANGLE_STEPS):
            return "Registration complete"
        return ANGLE_STEPS[self.step_index][1]

    @property
    def step_duration(self) -> float:
        if self.step_index >= len(ANGLE_STEPS):
            return 1
        return float(ANGLE_STEPS[self.step_index][2])

    @property
    def progress(self) -> float:
        return min(1.0, self.step_index / len(ANGLE_STEPS))

    @property
    def is_done(self) -> bool:
        return self.step_index >= len(ANGLE_STEPS)


# Global registration state (thread-safe)
_reg_lock = threading.Lock()
current_session: Optional[RegistrationSession] = None


def start_session(name: str) -> bool:
    """Start a new registration session for the given name."""
    global current_session
    with _reg_lock:
        if current_session and current_session.is_active and not current_session.is_done:
            return False  # Session already in progress
        current_session = RegistrationSession(
            name=name,
            step_start_time=time.time(),
        )
        return True


def abort_session() -> None:
    """Abort the current registration session."""
    global current_session
    with _reg_lock:
        if current_session:
            current_session.is_active = False
        current_session = None


def get_session() -> Optional[RegistrationSession]:
    """Get current session state (thread-safe read)."""
    with _reg_lock:
        return current_session


def update_session(
    encoding: Optional[np.ndarray] = None,
    face_crop: Optional[np.ndarray] = None,
) -> None:
    """Advance the registration session. Called from the camera loop.

    A sample is captured at the end of each pose step. If no face is visible
    when the step ends, the step is held open (the deadline is pushed back)
    instead of being skipped, so a session never completes with zero samples.
    """
    global current_session
    with _reg_lock:
        sess = current_session
        if sess is None or not sess.is_active or sess.is_done:
            return

        now = time.time()
        if now - sess.step_start_time < sess.step_duration:
            return

        if encoding is None:
            sess.result_message = "No face detected — align your face with the oval"
            sess.step_start_time = now - sess.step_duration + 0.5
            return

        sess.encodings.append(encoding)
        if face_crop is not None and face_crop.size > 0:
            sess.face_crops.append(face_crop)
        sess.step_index += 1
        sess.step_start_time = now
        sess.result_message = (
            f"Captured {len(sess.encodings)}/{len(ANGLE_STEPS)} samples"
        )


def draw_registration_overlay(frame: np.ndarray) -> np.ndarray:
    """Draw registration guidance overlay on the frame."""
    sess = get_session()
    if sess is None or not sess.is_active:
        return frame

    h, w = frame.shape[:2]
    overlay = frame.copy()

    # Semi-transparent top bar
    cv2.rectangle(overlay, (0, 0), (w, 80), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.4, frame, 0.6, 0, frame)

    # Title
    cv2.putText(frame, f"Register: {sess.name}", (20, 30),
                cv2.FONT_HERSHEY_DUPLEX, 0.8, (0, 255, 255), 1)

    if not sess.is_done:
        # Guide text (Persian + English)
        cv2.putText(frame, f"Step {sess.step_index+1}/{len(ANGLE_STEPS)}: {sess.current_guide}",
                    (20, 60), cv2.FONT_HERSHEY_DUPLEX, 0.6, (255, 255, 255), 1)

        # Progress bar
        bar_w = int((w - 40) * sess.progress)
        cv2.rectangle(frame, (20, h - 30), (20 + bar_w, h - 10), (0, 255, 0), -1)
        cv2.rectangle(frame, (20, h - 30), (w - 20, h - 10), (255, 255, 255), 1)

        # Center indicator (face oval)
        cx, cy = w // 2, h // 2
        cv2.ellipse(frame, (cx, cy), (w // 4, h // 4), 0, 0, 360, (0, 255, 0), 2)
        cv2.putText(frame, "Align face here", (cx - 60, cy + h // 4 + 30),
                    cv2.FONT_HERSHEY_DUPLEX, 0.5, (0, 255, 0), 1)
    else:
        cv2.putText(frame, "Registration Complete! Processing...", (20, 60),
                    cv2.FONT_HERSHEY_DUPLEX, 0.6, (0, 255, 0), 1)
        cv2.putText(frame, sess.result_message, (20, 85),
                    cv2.FONT_HERSHEY_DUPLEX, 0.5, (255, 255, 255), 1)

    return frame