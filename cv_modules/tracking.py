"""
tracking.py — Temporal Smoothing & Identity Tracking Module

Responsibility:
  - Face tracking across frames using IoU-based association
  - Temporal identity smoothing (consensus voting over window)
  - Kalman filter for bounding box smoothing
  - ID management (creation, confirmation, expiration)

Dependencies: numpy, cv2 (for Kalman), scipy (optional, for Hungarian)
"""

import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

# Try to import Hungarian algorithm for optimal assignment
try:
    from scipy.optimize import linear_sum_assignment
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


@dataclass
class TrackConfig:
    """Configuration for tracking behavior."""
    # IoU threshold for association
    iou_threshold: float = 0.35
    # Maximum frames to keep unmatched track alive
    max_age: int = 30
    # Frames required to confirm a new track
    min_hits: int = 3
    # Temporal voting window
    vote_window: int = 10
    # Minimum votes for identity confirmation
    min_votes: int = 5
    # Vote ratio threshold (majority)
    vote_ratio: float = 0.55
    # Kalman filter process noise
    kalman_process_noise: float = 0.01
    # Kalman filter measurement noise
    kalman_measurement_noise: float = 0.1


@dataclass
class Track:
    """Single face track with identity and state."""
    track_id: str
    bbox: np.ndarray  # [x1, y1, x2, y2] in image coordinates
    identity: Optional[str] = None  # Person ID (e.g., "W001")
    identity_votes: Dict[str, float] = field(default_factory=dict)  # identity -> weighted votes
    age: int = 0  # Frames since creation
    hits: int = 0  # Frames with detection match
    time_since_update: int = 0  # Frames since last match
    confirmed: bool = False
    quality_ema: float = 0.5  # Exponential moving average of quality
    kalman: Optional[cv2.KalmanFilter] = None
    last_update_time: float = field(default_factory=time.time)

    def __post_init__(self):
        if self.kalman is None:
            self.kalman = self._create_kalman()

    def _create_kalman(self) -> cv2.KalmanFilter:
        """Create Kalman filter for bbox smoothing (constant velocity model)."""
        kf = cv2.KalmanFilter(8, 4)  # state: [x, y, w, h, vx, vy, vw, vh], meas: [x, y, w, h]
        kf.measurementMatrix = np.eye(4, 8, dtype=np.float32)
        kf.transitionMatrix = np.eye(8, dtype=np.float32)
        for i in range(4):
            kf.transitionMatrix[i, i + 4] = 1.0  # position += velocity
        kf.processNoiseCov = np.eye(8, dtype=np.float32) * 0.01
        kf.measurementNoiseCov = np.eye(4, dtype=np.float32) * 0.1
        kf.errorCovPost = np.eye(8, dtype=np.float32)
        return kf

    def update(self, bbox: np.ndarray, quality: float = 1.0) -> None:
        """Update track with new detection. bbox format: [x1, y1, x2, y2]."""
        self.bbox = bbox.copy()
        self.age += 1
        self.hits += 1
        self.time_since_update = 0
        self.last_update_time = time.time()
        self.quality_ema = 0.7 * self.quality_ema + 0.3 * quality

        # Kalman update: convert [x1,y1,x2,y2] to [cx,cy,w,h]
        if self.kalman:
            x1, y1, x2, y2 = bbox.astype(np.float32)
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            w, h = max(x2 - x1, 1.0), max(y2 - y1, 1.0)
            meas = np.array([cx, cy, w, h], dtype=np.float32)
            self.kalman.correct(meas)

    def predict(self) -> np.ndarray:
        """Predict next bbox using Kalman filter. Returns [x1, y1, x2, y2]."""
        if self.kalman:
            # predict() returns an (8, 1) column vector — flatten to scalars,
            # otherwise the max() below mixes floats with 1-element arrays.
            pred = self.kalman.predict().ravel()
            cx, cy, w, h = (float(v) for v in pred[:4])
            x1 = max(0.0, cx - w / 2)
            y1 = max(0.0, cy - h / 2)
            x2 = cx + w / 2
            y2 = cy + h / 2
            return np.array([x1, y1, x2, y2], dtype=np.float32)
        return self.bbox.copy()

    def add_identity_vote(self, identity: str, confidence: float, quality: float) -> None:
        """Add weighted vote for identity."""
        weight = confidence * (0.5 + 0.5 * quality)  # Quality-weighted
        self.identity_votes[identity] = self.identity_votes.get(identity, 0.0) + weight

    def get_consensus_identity(self, window_size: int = 10, min_votes: int = 5, ratio: float = 0.55) -> Optional[str]:
        """Get consensus identity from recent votes."""
        if not self.identity_votes:
            return None

        # Sort by vote weight
        sorted_votes = sorted(self.identity_votes.items(), key=lambda x: x[1], reverse=True)
        best_id, best_weight = sorted_votes[0]
        total_weight = sum(v for _, v in sorted_votes)

        if total_weight > 0:
            vote_ratio = best_weight / total_weight
            if vote_ratio >= ratio and self.hits >= min_votes:
                return best_id
        return None

    def mark_missed(self) -> None:
        """Mark track as missed in current frame."""
        self.time_since_update += 1

    def is_expired(self, max_age: int) -> bool:
        return self.time_since_update > max_age


def compute_iou(box1: np.ndarray, box2: np.ndarray) -> float:
    """Compute IoU between two boxes [x1, y1, x2, y2]."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    if x2 <= x1 or y2 <= y1:
        return 0.0

    inter = (x2 - x1) * (y2 - y1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - inter

    return inter / max(union, 1e-6)


def compute_cost_matrix(tracks: List[Track], detections: List[np.ndarray]) -> np.ndarray:
    """
    Compute cost matrix for assignment (1 - IoU).
    """
    n_tracks = len(tracks)
    n_dets = len(detections)
    cost = np.ones((n_tracks, n_dets), dtype=np.float32)

    for i, trk in enumerate(tracks):
        pred_bbox = trk.predict()
        for j, det in enumerate(detections):
            iou = compute_iou(pred_bbox, det)
            if iou > 0:
                cost[i, j] = 1.0 - iou
    return cost


def associate_detections_to_tracks(
    tracks: List[Track],
    detections: List[np.ndarray],
    iou_threshold: float = 0.35,
) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
    """
    Associate detections to tracks using Hungarian algorithm or greedy IoU.

    Returns:
        matches: List of (track_idx, det_idx)
        unmatched_tracks: List of track indices
        unmatched_dets: List of detection indices
    """
    if not tracks or not detections:
        return [], list(range(len(tracks))), list(range(len(detections)))

    cost = compute_cost_matrix(tracks, detections)

    if HAS_SCIPY:
        # Hungarian algorithm for optimal assignment
        row_ind, col_ind = linear_sum_assignment(cost)
        matches = []
        for r, c in zip(row_ind, col_ind):
            if cost[r, c] <= 1.0 - iou_threshold:
                matches.append((r, c))
    else:
        # Greedy matching
        matches = []
        used_dets = set()
        cost_flat = [(cost[i, j], i, j) for i in range(cost.shape[0]) for j in range(cost.shape[1])]
        cost_flat.sort()

        for c, i, j in cost_flat:
            if i not in [m[0] for m in matches] and j not in used_dets:
                if c <= 1.0 - iou_threshold:
                    matches.append((i, j))
                    used_dets.add(j)

    matched_tracks = {m[0] for m in matches}
    matched_dets = {m[1] for m in matches}
    unmatched_tracks = [i for i in range(len(tracks)) if i not in matched_tracks]
    unmatched_dets = [j for j in range(len(detections)) if j not in matched_dets]

    return matches, unmatched_tracks, unmatched_dets


class MultiFaceTracker:
    """
    Multi-face tracker with temporal identity smoothing.
    """

    def __init__(self, config: Optional[TrackConfig] = None):
        self.config = config or TrackConfig()
        self.tracks: Dict[str, Track] = {}
        self._next_id = 0

    def update(
        self,
        detections: List[np.ndarray],
        identities: List[Optional[str]],
        confidences: List[float],
        qualities: List[float],
    ) -> List[Track]:
        """
        Update tracker with new frame detections.

        Args:
            detections: List of bboxes [x1, y1, x2, y2]
            identities: List of person IDs (or None for unknown)
            confidences: List of recognition confidences (0-1)
            qualities: List of face quality scores (0-1)

        Returns:
            List of active confirmed tracks
        """
        # Associate detections to existing tracks
        active_tracks = list(self.tracks.values())
        matches, unmatched_tracks, unmatched_dets = associate_detections_to_tracks(
            active_tracks, detections, self.config.iou_threshold
        )

        # Update matched tracks
        for trk_idx, det_idx in matches:
            trk = active_tracks[trk_idx]
            trk.update(detections[det_idx], qualities[det_idx])

            # Add identity vote if recognized
            if identities[det_idx] is not None:
                trk.add_identity_vote(
                    identities[det_idx],
                    confidences[det_idx],
                    qualities[det_idx]
                )

        # Mark unmatched tracks as missed
        for trk_idx in unmatched_tracks:
            active_tracks[trk_idx].mark_missed()

        # Create new tracks for unmatched detections
        for det_idx in unmatched_dets:
            new_track = self._create_track(
                detections[det_idx],
                identities[det_idx],
                confidences[det_idx],
                qualities[det_idx]
            )
            self.tracks[new_track.track_id] = new_track

        # Cleanup expired tracks
        self._cleanup()

        # Confirm tracks with enough hits
        self._confirm_tracks()

        # Return confirmed tracks
        return [t for t in self.tracks.values() if t.confirmed]

    def _create_track(
        self,
        bbox: np.ndarray,
        identity: Optional[str],
        confidence: float,
        quality: float,
    ) -> Track:
        track_id = f"T{self._next_id:04d}"
        self._next_id += 1

        track = Track(
            track_id=track_id,
            bbox=bbox.copy(),
            quality_ema=quality,
        )

        if identity is not None:
            track.add_identity_vote(identity, confidence, quality)

        return track

    def _cleanup(self) -> None:
        expired = [tid for tid, trk in self.tracks.items() if trk.is_expired(self.config.max_age)]
        for tid in expired:
            del self.tracks[tid]

    def _confirm_tracks(self) -> None:
        for trk in self.tracks.values():
            if not trk.confirmed and trk.hits >= self.config.min_hits:
                trk.confirmed = True

    def get_track_identities(self) -> Dict[str, Optional[str]]:
        """Get consensus identities for all confirmed tracks."""
        result = {}
        for trk in self.tracks.values():
            if trk.confirmed:
                result[trk.track_id] = trk.get_consensus_identity(
                    self.config.vote_window,
                    self.config.min_votes,
                    self.config.vote_ratio
                )
            else:
                result[trk.track_id] = None
        return result

    def get_active_tracks(self) -> List[Track]:
        return [t for t in self.tracks.values() if t.confirmed and t.time_since_update == 0]


def smooth_bbox(bbox: np.ndarray, prev_bbox: np.ndarray, alpha: float = 0.7) -> np.ndarray:
    """Exponential moving average smoothing for bbox."""
    return alpha * prev_bbox + (1 - alpha) * bbox