"""
alignment.py — Face Alignment Module

Responsibility:
  - Geometric face alignment using eye landmarks
  - Affine transform to canonical pose (frontal, normalized)
  - Improves recognition accuracy for non-frontal faces

Dependencies: cv2, numpy
"""

import cv2
import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class AlignmentConfig:
    """Configuration for face alignment."""
    # Desired eye positions in normalized coordinates (0-1)
    desired_left_eye: Tuple[float, float] = (0.35, 0.35)
    desired_right_eye: Tuple[float, float] = (0.65, 0.35)
    # Output size
    output_size: Tuple[int, int] = (112, 112)
    # Minimum eye distance to attempt alignment
    min_eye_distance: float = 10.0
    # Interpolation method
    interpolation: int = cv2.INTER_CUBIC


def get_eye_centers(landmarks: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Extract left and right eye centers from 68-point landmarks.

    Args:
        landmarks: (68, 2) or (68,) array of facial landmarks

    Returns:
        (left_eye_center, right_eye_center) as (x, y) arrays
    """
    if landmarks.shape == (68, 2):
        pts = landmarks
    elif landmarks.shape == (136,):
        pts = landmarks.reshape(68, 2)
    else:
        raise ValueError(f"Expected 68 landmarks, got shape {landmarks.shape}")

    # Left eye: indices 36-41, Right eye: indices 42-47
    left_eye = pts[36:42]
    right_eye = pts[42:48]

    left_center = np.mean(left_eye, axis=0).astype(int)
    right_center = np.mean(right_eye, axis=0).astype(int)

    return left_center, right_center


def compute_alignment_transform(
    left_eye: np.ndarray,
    right_eye: np.ndarray,
    config: AlignmentConfig,
) -> np.ndarray:
    """
    Compute affine transform matrix for face alignment.

    Args:
        left_eye: (x, y) coordinates of left eye center
        right_eye: (x, y) coordinates of right eye center
        config: AlignmentConfig with desired output parameters

    Returns:
        2x3 affine transformation matrix
    """
    # Current eye centers
    left = left_eye.astype(float)
    right = right_eye.astype(float)

    # Vector between eyes
    dy = right[1] - left[1]
    dx = right[0] - left[0]

    # Angle to rotate (make eyes horizontal)
    angle = np.degrees(np.arctan2(dy, dx))

    # Current distance between eyes
    current_dist = np.sqrt(dx**2 + dy**2)

    # Desired distance in output image
    desired_dist = (config.desired_right_eye[0] - config.desired_left_eye[0]) * config.output_size[0]

    # Scale factor
    scale = desired_dist / max(current_dist, 1e-6)

    # Center point between eyes (rotation center)
    eyes_center = ((left[0] + right[0]) * 0.5, (left[1] + right[1]) * 0.5)

    # Get rotation matrix
    M = cv2.getRotationMatrix2D(eyes_center, angle, scale)

    # Adjust translation to position eyes at desired locations
    t_x = config.output_size[0] * 0.5 - eyes_center[0]
    t_y = config.desired_left_eye[1] * config.output_size[1] - eyes_center[1]

    M[0, 2] += t_x
    M[1, 2] += t_y

    return M


def align_face(
    image: np.ndarray,
    landmarks: np.ndarray,
    config: Optional[AlignmentConfig] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Align face to canonical pose using eye landmarks.

    Args:
        image: Input image (BGR or RGB)
        landmarks: 68 facial landmarks
        config: AlignmentConfig (uses defaults if None)

    Returns:
        (aligned_image, transform_matrix)
    """
    if config is None:
        config = AlignmentConfig()

    left_eye, right_eye = get_eye_centers(landmarks)

    # Check if eyes are too close (bad landmarks)
    eye_dist = np.linalg.norm(right_eye - left_eye)
    if eye_dist < config.min_eye_distance:
        # Return original image if alignment not reliable
        return image, np.eye(3, 3, dtype=np.float32)[:2]

    # Compute transform
    M = compute_alignment_transform(left_eye, right_eye, config)

    # Apply transform
    aligned = cv2.warpAffine(
        image,
        M,
        config.output_size,
        flags=config.interpolation,
        borderMode=cv2.BORDER_REPLICATE,
    )

    return aligned, M


def align_face_simple(
    image: np.ndarray,
    left_eye: Tuple[int, int],
    right_eye: Tuple[int, int],
    output_size: Tuple[int, int] = (112, 112),
) -> np.ndarray:
    """
    Simple face alignment given explicit eye coordinates.
    Useful when landmarks are not available.

    Args:
        image: Input image
        left_eye: (x, y) of left eye center
        right_eye: (x, y) of right eye center
        output_size: Desired output size

    Returns:
        Aligned face image
    """
    config = AlignmentConfig(
        desired_left_eye=(0.35, 0.35),
        desired_right_eye=(0.65, 0.35),
        output_size=output_size,
    )

    M = compute_alignment_transform(
        np.array(left_eye),
        np.array(right_eye),
        config,
    )

    return cv2.warpAffine(image, M, output_size, flags=cv2.INTER_CUBIC)


def estimate_head_pose(landmarks: np.ndarray) -> Tuple[float, float, float]:
    """
    Estimate head pose (yaw, pitch, roll) from landmarks.

    Returns:
        (yaw, pitch, roll) in degrees
    """
    if landmarks.shape != (68, 2):
        pts = landmarks.reshape(68, 2)
    else:
        pts = landmarks

    # Key points
    nose_tip = pts[30]
    chin = pts[8]
    left_eye = pts[36]
    right_eye = pts[45]
    left_mouth = pts[48]
    right_mouth = pts[54]

    # Roll: angle of eye line
    eye_vec = right_eye - left_eye
    roll = np.degrees(np.arctan2(eye_vec[1], eye_vec[0]))

    # Yaw: horizontal offset of nose from eye center
    eye_center = (left_eye + right_eye) * 0.5
    nose_offset_x = nose_tip[0] - eye_center[0]
    eye_dist = np.linalg.norm(right_eye - left_eye)
    yaw = np.degrees(np.arctan2(nose_offset_x, eye_dist))

    # Pitch: vertical position of nose relative to eyes
    nose_offset_y = nose_tip[1] - eye_center[1]
    pitch = np.degrees(np.arctan2(nose_offset_y, eye_dist))

    return yaw, pitch, roll


def is_frontal_face(landmarks: np.ndarray, yaw_threshold: float = 25, pitch_threshold: float = 20) -> bool:
    """
    Check if face is approximately frontal.

    Args:
        landmarks: 68 facial landmarks
        yaw_threshold: Max absolute yaw angle (degrees)
        pitch_threshold: Max absolute pitch angle (degrees)

    Returns:
        True if face is frontal enough
    """
    yaw, pitch, roll = estimate_head_pose(landmarks)
    return abs(yaw) <= yaw_threshold and abs(pitch) <= pitch_threshold


def crop_and_align(
    image: np.ndarray,
    bbox: Tuple[int, int, int, int],  # x, y, w, h
    landmarks: np.ndarray,
    config: Optional[AlignmentConfig] = None,
    padding: float = 0.3,
) -> np.ndarray:
    """
    Crop face region and align in one step.

    Args:
        image: Input image
        bbox: Face bounding box (x, y, w, h)
        landmarks: 68 facial landmarks
        config: AlignmentConfig
        padding: Padding factor around face (0.3 = 30%)

    Returns:
        Aligned and cropped face
    """
    if config is None:
        config = AlignmentConfig()

    x, y, w, h = bbox

    # Add padding
    pad_x = int(w * padding)
    pad_y = int(h * padding)
    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_y)
    x2 = min(image.shape[1], x + w + pad_x)
    y2 = min(image.shape[0], y + h + pad_y)

    # Crop
    cropped = image[y1:y2, x1:x2]

    # Adjust landmarks to crop coordinates
    adjusted_landmarks = landmarks.copy()
    adjusted_landmarks[:, 0] -= x1
    adjusted_landmarks[:, 1] -= y1

    # Align
    aligned, _ = align_face(cropped, adjusted_landmarks, config)

    return aligned