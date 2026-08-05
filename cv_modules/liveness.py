"""
liveness.py — Liveness Detection Module

Responsibility:
  - Detect spoofing attempts (printed photos, screen replays, masks)
  - Multi-cue approach: Eye blink, Texture analysis, Head motion, Frequency analysis
  - Designed for real-time operation with minimal latency

Dependencies: cv2, numpy, scipy (optional for FFT)
"""

import cv2
import numpy as np
from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Tuple
import time


@dataclass
class LivenessResult:
    """Result of liveness check."""
    is_live: bool
    score: float                    # Overall liveness score [0, 1]
    blink_score: float              # Eye blink detection score
    texture_score: float            # Texture/frequency analysis score
    motion_score: float             # Natural head motion score
    details: dict                   # Per-component scores


class BlinkDetector:
    """
    Eye blink detection using Eye Aspect Ratio (EAR).
    Tracks consecutive frames with low EAR to detect natural blinks.
    """

    def __init__(
        self,
        ear_threshold: float = 0.22,
        consecutive_frames: int = 2,
        history_size: int = 30,
    ):
        self.ear_threshold = ear_threshold
        self.consecutive_frames = consecutive_frames
        self.history_size = history_size

        self._ear_history: Deque[float] = deque(maxlen=history_size)
        self._blink_count = 0
        self._consecutive_low = 0
        self._last_blink_time = 0

    @staticmethod
    def _eye_aspect_ratio(eye: np.ndarray) -> float:
        """Calculate EAR from 6 eye landmarks."""
        # Vertical distances
        v1 = np.linalg.norm(eye[1] - eye[5])
        v2 = np.linalg.norm(eye[2] - eye[4])
        # Horizontal distance
        h = np.linalg.norm(eye[0] - eye[3])
        return (v1 + v2) / (2.0 * max(h, 1e-6))

    def update(self, left_eye: np.ndarray, right_eye: np.ndarray) -> float:
        """
        Update with new eye landmarks.
        Returns current blink score [0, 1].
        """
        left_ear = self._eye_aspect_ratio(left_eye)
        right_ear = self._eye_aspect_ratio(right_eye)
        avg_ear = (left_ear + right_ear) / 2.0

        self._ear_history.append(avg_ear)

        # Detect blink: sustained low EAR followed by recovery
        if avg_ear < self.ear_threshold:
            self._consecutive_low += 1
        else:
            if self._consecutive_low >= self.consecutive_frames:
                self._blink_count += 1
                self._last_blink_time = time.time()
            self._consecutive_low = 0

        # Score based on blink frequency (natural: ~15-20 blinks/min)
        elapsed = time.time() - (self._ear_history[0] if self._ear_history else time.time())
        if elapsed > 10 and self._blink_count > 0:
            blink_rate = self._blink_count / (elapsed / 60.0)
            # Natural blink rate: 15-20 per minute
            if 10 <= blink_rate <= 30:
                return 1.0
            elif 5 <= blink_rate <= 40:
                return 0.7
        return 0.3

    def reset(self):
        self._ear_history.clear()
        self._blink_count = 0
        self._consecutive_low = 0
        self._last_blink_time = 0


class TextureAnalyzer:
    """
    Texture/Frequency analysis for spoof detection.
    Real faces have high-frequency details; printed photos/screens lack them.
    """

    def __init__(
        self,
        laplacian_threshold: float = 50.0,
        fft_threshold: float = 0.15,
    ):
        self.laplacian_threshold = laplacian_threshold
        self.fft_threshold = fft_threshold

    def analyze(self, face_gray: np.ndarray) -> float:
        """
        Analyze face texture.
        Returns score [0, 1] where 1 = live texture.
        """
        if face_gray.size == 0:
            return 0.0

        # 1. Laplacian variance (high-frequency content)
        lap = cv2.Laplacian(face_gray, cv2.CV_64F)
        lap_var = lap.var()
        lap_score = min(lap_var / self.laplacian_threshold, 1.0)

        # 2. FFT-based frequency analysis
        fft_score = self._fft_analysis(face_gray)

        # 3. Local Binary Pattern (LBP) variance
        lbp_score = self._lbp_analysis(face_gray)

        # Combine (weighted)
        return 0.4 * lap_score + 0.4 * fft_score + 0.2 * lbp_score

    def _fft_analysis(self, img: np.ndarray) -> float:
        """Frequency domain analysis - real faces have more high-frequency content."""
        h, w = img.shape[:2]
        # Resize to standard size for consistency
        img_resized = cv2.resize(img, (128, 128))

        # 2D FFT
        f = np.fft.fft2(img_resized)
        fshift = np.fft.fftshift(f)
        magnitude = np.log(np.abs(fshift) + 1e-10)

        # High-frequency energy (outer region)
        crow, ccol = h // 2, w // 2
        # Create mask for high frequencies
        mask = np.ones((128, 128), dtype=np.uint8)
        cv2.circle(mask, (64, 64), 32, 0, -1)  # Remove low frequencies
        high_freq_energy = np.mean(magnitude * mask)
        total_energy = np.mean(magnitude)

        if total_energy > 0:
            ratio = high_freq_energy / total_energy
            return min(ratio / self.fft_threshold, 1.0)
        return 0.0

    def _lbp_analysis(self, img: np.ndarray) -> float:
        """Local Binary Pattern analysis for texture uniformity."""
        try:
            # Simple LBP implementation
            img_small = cv2.resize(img, (64, 64))
            lbp = np.zeros_like(img_small, dtype=np.uint8)

            for i in range(1, 63):
                for j in range(1, 63):
                    center = img_small[i, j]
                    code = 0
                    neighbors = [
                        img_small[i-1, j-1], img_small[i-1, j], img_small[i-1, j+1],
                        img_small[i, j+1], img_small[i+1, j+1], img_small[i+1, j],
                        img_small[i+1, j-1], img_small[i, j-1]
                    ]
                    for k, n in enumerate(neighbors):
                        if n >= center:
                            code |= (1 << k)
                    lbp[i, j] = code

            # Uniform LBP patterns indicate natural texture
            hist, _ = np.histogram(lbp.ravel(), bins=256, range=(0, 256))
            hist = hist.astype(float) / (hist.sum() + 1e-6)
            # Entropy of LBP histogram
            entropy = -np.sum(hist * np.log2(hist + 1e-10))
            # Normalize (max entropy for 256 bins is 8)
            return min(entropy / 7.0, 1.0)
        except Exception:
            return 0.5


class MotionAnalyzer:
    """
    Natural head motion detection.
    Real faces exhibit subtle involuntary motion; static images don't.
    """

    def __init__(self, window_size: int = 30):
        self.window_size = window_size
        self._positions: Deque[Tuple[float, float]] = deque(maxlen=window_size)
        self._timestamps: Deque[float] = deque(maxlen=window_size)

    def update(self, nose_tip: Tuple[float, float]) -> float:
        """Update with nose tip position, return motion naturalness score."""
        now = time.time()
        self._positions.append(nose_tip)
        self._timestamps.append(now)

        if len(self._positions) < 10:
            return 0.3  # Not enough data

        # Calculate motion statistics
        pos_array = np.array(self._positions)
        motion = np.std(pos_array, axis=0)
        total_motion = np.sqrt(motion[0]**2 + motion[1]**2)

        # Time span
        time_span = self._timestamps[-1] - self._timestamps[0]
        if time_span < 1.0:
            return 0.3

        # Motion per second
        motion_rate = total_motion / time_span

        # Natural motion: 1-10 pixels/second subtle movement
        if 0.5 <= motion_rate <= 15.0:
            return 1.0
        elif 0.1 <= motion_rate <= 30.0:
            return 0.7
        elif motion_rate < 0.1:
            return 0.1  # Too static = likely photo
        else:
            return 0.4  # Too much motion = unnatural

    def reset(self):
        self._positions.clear()
        self._timestamps.clear()


class LivenessDetector:
    """
    Multi-cue Liveness Detector.

    Combines:
    1. Eye blink detection (EAR-based)
    2. Texture/Frequency analysis
    3. Natural head motion
    4. (Optional) Challenge-response (not implemented here)

    Decision: Weighted combination with configurable thresholds.
    """

    def __init__(
        self,
        blink_weight: float = 0.35,
        texture_weight: float = 0.35,
        motion_weight: float = 0.30,
        threshold: float = 0.55,
    ):
        self.blink_weight = blink_weight
        self.texture_weight = texture_weight
        self.motion_weight = motion_weight
        self.threshold = threshold

        self.blink_detector = BlinkDetector()
        self.texture_analyzer = TextureAnalyzer()
        self.motion_analyzer = MotionAnalyzer()

        self._frame_count = 0
        self._last_result: Optional[LivenessResult] = None

    def update(
        self,
        face_gray: np.ndarray,
        landmarks: Optional[np.ndarray] = None,
        face_bbox: Optional[Tuple[int, int, int, int]] = None,
    ) -> LivenessResult:
        """
        Update liveness detection with new frame.

        Args:
            face_gray: Grayscale face crop
            landmarks: 68 facial landmarks (x, y)
            face_bbox: (x, y, w, h) of face in original frame

        Returns:
            LivenessResult with decision and component scores
        """
        self._frame_count += 1

        has_landmarks = landmarks is not None and len(landmarks) >= 48

        # 1. Blink detection (requires landmarks)
        blink_score = 0.0
        if has_landmarks:
            left_eye = landmarks[36:42]
            right_eye = landmarks[42:48]
            blink_score = self.blink_detector.update(left_eye, right_eye)

        # 2. Texture analysis
        texture_score = self.texture_analyzer.analyze(face_gray)

        # 3. Motion analysis (uses nose tip landmark 30)
        motion_score = 0.0
        if landmarks is not None and len(landmarks) >= 31:
            nose_tip = (landmarks[30][0], landmarks[30][1])
            motion_score = self.motion_analyzer.update(nose_tip)

        # Weighted combination over the cues that are actually available.
        # Without landmarks only texture can be measured, so its weight is
        # renormalized instead of scoring the missing cues as zero.
        components = [(self.texture_weight, texture_score)]
        if has_landmarks:
            components.append((self.blink_weight, blink_score))
        if landmarks is not None and len(landmarks) >= 31:
            components.append((self.motion_weight, motion_score))

        total_weight = sum(w for w, _ in components)
        overall = sum(w * s for w, s in components) / total_weight

        is_live = overall >= self.threshold

        result = LivenessResult(
            is_live=is_live,
            score=overall,
            blink_score=blink_score,
            texture_score=texture_score,
            motion_score=motion_score,
            details={
                "blink": blink_score,
                "texture": texture_score,
                "motion": motion_score,
                "threshold": self.threshold,
                "frame": self._frame_count,
            }
        )
        self._last_result = result
        return result

    def get_last_result(self) -> Optional[LivenessResult]:
        return self._last_result

    def reset(self):
        self.blink_detector.reset()
        self.motion_analyzer.reset()
        self._frame_count = 0
        self._last_result = None


def quick_liveness_check(face_gray: np.ndarray, landmarks: Optional[np.ndarray] = None) -> bool:
    """
    Quick liveness gate for real-time use.
    Returns True if likely live, False if likely spoof.
    """
    if face_gray.size == 0:
        return False

    # Quick texture check
    lap = cv2.Laplacian(face_gray, cv2.CV_64F)
    if lap.var() < 30:
        return False

    # Quick EAR check if landmarks available
    if landmarks is not None and len(landmarks) >= 48:
        left_eye = landmarks[36:42]
        right_eye = landmarks[42:48]
        v1 = np.linalg.norm(left_eye[1] - left_eye[5])
        v2 = np.linalg.norm(left_eye[2] - left_eye[4])
        h1 = np.linalg.norm(left_eye[0] - left_eye[3])
        ear = (v1 + v2) / (2.0 * max(h1, 1e-6))
        if ear < 0.15:  # Eyes very closed
            pass  # Could be blink, don't reject yet

    return True