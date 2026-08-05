"""
quality.py — Face Quality Assessment Module

Responsibility:
  - Assess face quality: Blur, Pose, Illumination, Occlusion
  - Filter low-quality faces before recognition
  - Provide quality score [0, 1] for adaptive thresholds

Dependencies: cv2, numpy
"""

import cv2
import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class QualityMetrics:
    """Container for face quality metrics."""
    blur_score: float = 0.0           # Laplacian variance (higher = sharper)
    brightness_score: float = 0.0     # Mean pixel intensity (optimal ~128)
    contrast_score: float = 0.0       # Standard deviation (higher = better contrast)
    pose_score: float = 0.0           # Head pose estimation (0 = frontal)
    occlusion_score: float = 0.0      # Occlusion detection (0 = no occlusion)
    overall_score: float = 0.0        # Weighted composite score

    def is_acceptable(self, threshold: float = 0.5) -> bool:
        """Check if face quality meets minimum threshold."""
        return self.overall_score >= threshold

    def to_dict(self) -> dict:
        return {
            "blur": round(self.blur_score, 3),
            "brightness": round(self.brightness_score, 3),
            "contrast": round(self.contrast_score, 3),
            "pose": round(self.pose_score, 3),
            "occlusion": round(self.occlusion_score, 3),
            "overall": round(self.overall_score, 3),
        }


class FaceQualityAssessor:
    """
    Assess face quality using multiple metrics.

    Metrics:
    1. Blur (Laplacian variance) - detects motion blur, defocus
    2. Brightness (mean intensity) - detects under/over exposure
    3. Contrast (std dev) - detects low contrast
    4. Pose (landmark-based) - detects non-frontal faces
    5. Occlusion - detects partial face coverage
    """

    # Thresholds for quality gates
    BLUR_THRESHOLD = 100.0          # Laplacian variance minimum
    BRIGHTNESS_MIN = 40             # Minimum mean brightness
    BRIGHTNESS_MAX = 220            # Maximum mean brightness
    CONTRAST_THRESHOLD = 20.0       # Minimum contrast (std dev)
    POSE_YAW_THRESHOLD = 30.0       # Maximum yaw angle (degrees)
    POSE_PITCH_THRESHOLD = 25.0     # Maximum pitch angle (degrees)

    # Weights for composite score
    WEIGHTS = {
        "blur": 0.25,
        "brightness": 0.20,
        "contrast": 0.20,
        "pose": 0.25,
        "occlusion": 0.10,
    }

    def __init__(
        self,
        blur_threshold: float = None,
        brightness_min: int = None,
        brightness_max: int = None,
        contrast_threshold: float = None,
        pose_yaw_threshold: float = None,
        pose_pitch_threshold: float = None,
    ):
        self.blur_threshold = blur_threshold or self.BLUR_THRESHOLD
        self.brightness_min = brightness_min or self.BRIGHTNESS_MIN
        self.brightness_max = brightness_max or self.BRIGHTNESS_MAX
        self.contrast_threshold = contrast_threshold or self.CONTRAST_THRESHOLD
        self.pose_yaw_threshold = pose_yaw_threshold or self.POSE_YAW_THRESHOLD
        self.pose_pitch_threshold = pose_pitch_threshold or self.POSE_PITCH_THRESHOLD

    def assess(
        self,
        face_img: np.ndarray,
        landmarks: Optional[np.ndarray] = None,
        bbox: Optional[Tuple[int, int, int, int]] = None,
    ) -> QualityMetrics:
        """
        Assess quality of a face image.

        Args:
            face_img: Cropped face image (RGB or BGR)
            landmarks: Optional 68 facial landmarks (x, y) for pose/occlusion
            bbox: Optional (x, y, w, h) for size checks

        Returns:
            QualityMetrics with individual scores and overall composite
        """
        if face_img.size == 0:
            return QualityMetrics()

        # Ensure grayscale
        if len(face_img.shape) == 3:
            gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY)
        else:
            gray = face_img

        h, w = gray.shape[:2]

        # 1. Blur Score (Laplacian variance)
        lap = cv2.Laplacian(gray, cv2.CV_64F)
        blur_var = lap.var()
        blur_score = min(blur_var / self.blur_threshold, 1.0) if self.blur_threshold > 0 else 1.0

        # 2. Brightness Score
        mean_bright = np.mean(gray)
        if self.brightness_min <= mean_bright <= self.brightness_max:
            # Optimal around 128
            brightness_score = 1.0 - abs(mean_bright - 128) / 128
        else:
            brightness_score = 0.0
        brightness_score = max(0.0, min(1.0, brightness_score))

        # 3. Contrast Score
        contrast = np.std(gray)
        contrast_score = min(contrast / self.contrast_threshold, 1.0) if self.contrast_threshold > 0 else 1.0

        # 4. Pose Score (if landmarks available)
        pose_score = 1.0
        if landmarks is not None and len(landmarks) >= 68:
            pose_score = self._estimate_pose_score(landmarks, w, h)

        # 5. Occlusion Score (basic heuristic)
        occlusion_score = 1.0
        if landmarks is not None and len(landmarks) >= 68:
            occlusion_score = self._estimate_occlusion(landmarks, gray)

        # Composite score (weighted)
        overall = (
            self.WEIGHTS["blur"] * blur_score +
            self.WEIGHTS["brightness"] * brightness_score +
            self.WEIGHTS["contrast"] * contrast_score +
            self.WEIGHTS["pose"] * pose_score +
            self.WEIGHTS["occlusion"] * occlusion_score
        )

        return QualityMetrics(
            blur_score=blur_score,
            brightness_score=brightness_score,
            contrast_score=contrast_score,
            pose_score=pose_score,
            occlusion_score=occlusion_score,
            overall_score=overall,
        )

    def _estimate_pose_score(self, landmarks: np.ndarray, img_w: int, img_h: int) -> float:
        """
        Estimate head pose from 68 facial landmarks.
        Returns score [0, 1] where 1 = frontal.
        """
        try:
            # Key landmarks for pose estimation
            # Nose tip (30), Chin (8), Left eye corner (36), Right eye corner (45)
            # Left mouth corner (48), Right mouth corner (54)

            nose_tip = landmarks[30]
            chin = landmarks[8]
            left_eye = landmarks[36]
            right_eye = landmarks[45]
            left_mouth = landmarks[48]
            right_mouth = landmarks[54]

            # Eye line vector
            eye_vec = right_eye - left_eye
            eye_dist = np.linalg.norm(eye_vec)

            # Nose to chin vector
            nose_chin = chin - nose_tip

            # Yaw: horizontal offset of nose from eye center
            eye_center = (left_eye + right_eye) / 2
            nose_offset_x = nose_tip[0] - eye_center[0]
            yaw = np.degrees(np.arctan2(nose_offset_x, eye_dist * 0.5))

            # Pitch: vertical ratio
            pitch = np.degrees(np.arctan2(nose_chin[1], eye_dist * 0.8))

            # Normalize scores (1.0 = frontal, 0.0 = extreme)
            yaw_score = max(0.0, 1.0 - abs(yaw) / self.pose_yaw_threshold)
            pitch_score = max(0.0, 1.0 - abs(pitch) / self.pose_pitch_threshold)

            return min(yaw_score, pitch_score)

        except Exception:
            return 0.5  # Unknown pose, moderate penalty

    def _estimate_occlusion(self, landmarks: np.ndarray, gray: np.ndarray) -> float:
        """
        Estimate occlusion using landmark symmetry and texture.
        Returns score [0, 1] where 1 = no occlusion.
        """
        try:
            # Check symmetry of facial features
            left_eye = landmarks[36:42]
            right_eye = landmarks[42:48]

            # Eye aspect ratio symmetry
            left_ear = self._eye_aspect_ratio(left_eye)
            right_ear = self._eye_aspect_ratio(right_eye)
            ear_diff = abs(left_ear - right_ear) / max(left_ear, right_ear, 1e-6)

            # Mouth symmetry
            mouth_left = landmarks[48]
            mouth_right = landmarks[54]
            mouth_center = landmarks[51]
            mouth_sym = abs(mouth_left[0] - mouth_center[0]) / max(abs(mouth_right[0] - mouth_center[0]), 1e-6)

            # Texture analysis in face region
            # If face has uniform texture (like a mask), variance is low
            face_var = np.var(gray)
            texture_score = min(face_var / 500.0, 1.0)

            # Combine
            occlusion = (1.0 - ear_diff) * 0.4 + (1.0 - mouth_sym) * 0.3 + texture_score * 0.3
            return max(0.0, min(1.0, occlusion))

        except Exception:
            return 0.7  # Moderate score if estimation fails

    @staticmethod
    def _eye_aspect_ratio(eye: np.ndarray) -> float:
        """Calculate Eye Aspect Ratio (EAR) for 6 eye landmarks."""
        # Vertical distances
        v1 = np.linalg.norm(eye[1] - eye[5])
        v2 = np.linalg.norm(eye[2] - eye[4])
        # Horizontal distance
        h = np.linalg.norm(eye[0] - eye[3])
        return (v1 + v2) / (2.0 * max(h, 1e-6))


def quick_quality_check(face_img: np.ndarray, min_score: float = 0.4) -> bool:
    """
    Quick quality gate - returns True if face passes minimum quality.
    Optimized for speed (no landmarks required).
    """
    if face_img.size == 0:
        return False

    if len(face_img.shape) == 3:
        gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY)
    else:
        gray = face_img

    # Quick blur check
    lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    if lap_var < 50:
        return False

    # Quick brightness check
    mean_bright = np.mean(gray)
    if mean_bright < 40 or mean_bright > 220:
        return False

    # Quick contrast check
    if np.std(gray) < 15:
        return False

    return True