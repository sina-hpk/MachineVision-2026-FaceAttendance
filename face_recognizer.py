"""
face_recognizer.py — Advanced Face Recognition (InsightFace + face_recognition)

Architecture:
  - InsightFace (ArcFace + RetinaFace) is the primary detector/recognizer
  - face_recognition (dlib) is used as fallback for edge cases
  - Quality Assessment, Liveness Detection, Face Alignment, Tracking

Pipeline:
  Frame → RetinaFace detect → Quality gate → ArcFace encode →
  Match DB → Liveness check → Kalman tracking → Augmentation

Dependencies: insightface, face_recognition, onnxruntime, cv2, numpy
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
import os

import cv2
import numpy as np

# InsightFace (primary engine) - lazy import in __init__
# face_recognition (fallback engine)
try:
    import face_recognition
    _FR_AVAILABLE = True
except ImportError:
    _FR_AVAILABLE = False

from models.repository import FaceRepository
from cv_modules.quality import FaceQualityAssessor, quick_quality_check
from cv_modules.liveness import LivenessDetector
from cv_modules.alignment import align_face, AlignmentConfig
from cv_modules.tracking import MultiFaceTracker


# Default configuration
DEFAULT_TOLERANCE = 0.55
DEFAULT_PROCESS_SCALE = 0.25
DEFAULT_AUGMENT_COOLDOWN = timedelta(minutes=5)
DEFAULT_MAX_ENCODINGS = 10
DEFAULT_QUALITY_THRESHOLD = 0.5
DEFAULT_LIVENESS_THRESHOLD = 0.55
INSIGHTFACE_CONFIDENCE_THRESHOLD = 0.4

log = logging.getLogger("FaceRecognizer")


class FaceRecognizer:
    """
    Advanced Face Recognizer using InsightFace (ArcFace) as primary engine
    with face_recognition (dlib) as fallback.

    Key improvements over v1:
      - RetinaFace detection (more robust than HOG)
      - ArcFace encoding (512-dim, higher accuracy than dlib 128-dim)
      - Built-in landmark detection (no extra call needed)
      - GPU acceleration via ONNX Runtime
    """

    def __init__(
        self,
        db: FaceRepository,
        tolerance: float = DEFAULT_TOLERANCE,
        process_scale: float = DEFAULT_PROCESS_SCALE,
        augment_min_distance: float = 0.2,
        max_encodings: int = DEFAULT_MAX_ENCODINGS,
        augment_cooldown: timedelta = DEFAULT_AUGMENT_COOLDOWN,
        quality_threshold: float = DEFAULT_QUALITY_THRESHOLD,
        liveness_threshold: float = DEFAULT_LIVENESS_THRESHOLD,
        enable_alignment: bool = True,
        enable_liveness: bool = True,
        enable_tracking: bool = True,
        enable_quality_gate: bool = True,
        prefer_insightface: bool = True,
        insightface_det_size: int = 320,
    ):
        self.db = db

        # Core recognition parameters
        self.tolerance = tolerance
        self.process_scale = process_scale
        self.augment_min_distance = augment_min_distance
        self.max_encodings = max_encodings
        self.augment_cooldown = augment_cooldown
        self._last_augment: dict[str, datetime] = {}

        # Feature flags
        self.quality_threshold = quality_threshold
        self.liveness_threshold = liveness_threshold
        self.enable_alignment = enable_alignment
        self.enable_liveness = enable_liveness
        self.enable_tracking = enable_tracking
        self.enable_quality_gate = enable_quality_gate

        # Camera
        self._cap: cv2.VideoCapture | None = None

        # Phase 2 Modules
        self.quality_assessor = FaceQualityAssessor()
        self.liveness_detector = LivenessDetector(threshold=liveness_threshold)
        self.alignment_config = AlignmentConfig()
        self.tracker = MultiFaceTracker()

        # Tracking state
        self._frame_count = 0

        # Known-encoding cache (the DB is queried once per TTL, not per frame)
        self._known_cache: Optional[tuple[List[str], List[np.ndarray]]] = None
        self._known_cache_at = 0.0
        self._known_cache_ttl = 5.0

        # ── InsightFace Engine (primary) ──
        self._insightface_app = None
        self._use_insightface = prefer_insightface
        if self._use_insightface:
            try:
                from insightface.app import FaceAnalysis as InsightFaceAnalysis
                self._insightface_app = InsightFaceAnalysis(
                    name="buffalo_l",
                    providers=["CPUExecutionProvider"],
                    # Only these two sub-models are used. Skipping the bundled
                    # genderage/landmark nets cut per-frame cost from ~740ms to
                    # ~625ms at det_size 640 on a 4-core CPU.
                    allowed_modules=["detection", "recognition"],
                )
                # det_size must be square: SCRFD builds its anchor grid from the
                # input height for both axes, so a non-square size such as
                # (320, 240) raises "operands could not be broadcast together
                # with shapes (140,) (160,)" inside distance2bbox().
                det = int(insightface_det_size)
                self._insightface_app.prepare(ctx_id=-1, det_size=(det, det))
                print(
                    f"[FaceRecognizer] InsightFace ready "
                    f"(buffalo_l, ArcFace 512-d, det_size={det})"
                )
            except Exception as e:
                print(f"[FaceRecognizer] InsightFace init failed: {e}, falling back")
                self._use_insightface = False

    # ── Public status ──

    @property
    def engine_name(self) -> str:
        if self._use_insightface:
            return "insightface_arcface"
        return "face_recognition_dlib"

    # ── Camera Management ──

    def open(self, index: int = 0) -> bool:
        """Open camera with simple, safe configuration."""
        import concurrent.futures
        import platform
        def _open():
            # CAP_DSHOW is Windows-only and does not exist on Linux/macOS
            # builds of OpenCV, so pick the backend per-platform.
            if platform.system() == "Windows":
                cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            else:
                cap = cv2.VideoCapture(index)
            if not cap.isOpened():
                cap.release()
                return None
            # Just set resolution to reduce noise, nothing fancy
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            return cap
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_open)
            try:
                self._cap = fut.result(timeout=5)
            except (concurrent.futures.TimeoutError, Exception):
                self._cap = None
                return False
        if self._cap is None:
            return False
        return True

    def close(self):
        if self._cap:
            self._cap.release()
            self._cap = None
        cv2.destroyAllWindows()

    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def read(self) -> Optional[np.ndarray]:
        if not self.is_open():
            return None
        ret, raw = self._cap.read()
        return raw.copy() if ret and raw is not None else None

    # ── Core Recognition Pipeline ──

    def recognize(self, frame: np.ndarray) -> List[Dict]:
        """
        Main recognition pipeline.

        1. Detect faces using InsightFace (RetinaFace) or face_recognition (HOG)
        2. Quality Assessment (blur, pose, illumination gate)
        3. Face Alignment (geometric normalization)
        4. Liveness Detection
        5. Encoding extraction
        6. Database matching (cosine distance for ArcFace, Euclidean for dlib)
        7. Multi-face Tracking + Temporal Smoothing
        8. Quality-gated augmentation
        """
        self._frame_count += 1

        if self._use_insightface:
            results = self._recognize_insightface(frame)
        else:
            results = self._recognize_dlib(frame)

        # ── Tracking ──
        if self.enable_tracking and results:
            results = self._apply_tracking(results)

        return results

    def invalidate_cache(self) -> None:
        """Drop the cached known encodings after a DB write."""
        self._known_cache = None

    def _get_known(self) -> tuple[List[str], List[np.ndarray]]:
        """Known encodings, cached for a short TTL to keep the loop off the DB."""
        now = time.time()
        if self._known_cache is None or now - self._known_cache_at > self._known_cache_ttl:
            self._known_cache = self.db.get_all_known()
            self._known_cache_at = now
        return self._known_cache

    # ── InsightFace Pipeline ──

    def _recognize_insightface(self, frame: np.ndarray) -> List[Dict]:
        """Recognition using InsightFace (ArcFace + RetinaFace)."""
        if self._insightface_app is None:
            return self._recognize_dlib(frame)

        # Detect + Recognize in one call
        try:
            dets = self._insightface_app.get(frame)
        except Exception as e:
            log.warning("insightface.get() failed: %s", e)
            return self._recognize_dlib(frame)

        if not dets:
            log.debug("insightface.get() returned 0 detections")
            return []

        known_ids, known_encs = self._get_known()
        # Built lazily on the first face of the frame (needs the embedding dim).
        known_matrix: Optional[np.ndarray] = None
        match_ids: List[str] = []
        results = []

        for det in dets:
            bbox = det.bbox.astype(np.int32)  # [x1, y1, x2, y2]
            if bbox.size < 4:
                continue

            l, t, r, b = bbox[0], bbox[1], bbox[2], bbox[3]
            if l >= r or t >= b:
                log.debug("invalid bbox: %s", bbox)
                continue

            # Face crop for quality/liveness
            face_crop = frame[t:b, l:r].copy()
            if face_crop.size == 0:
                continue

            # Quality Assessment
            quality_metrics = self.quality_assessor.assess(face_crop)
            quality_score = quality_metrics.overall_score

            if self.enable_quality_gate and quality_score < self.quality_threshold:
                log.debug("quality gate: score=%.2f < thresh=%.2f", quality_score, self.quality_threshold)
                continue

            # ArcFace embedding (512-dim from InsightFace)
            encoding = det.embedding  # Already computed by InsightFace
            if encoding is None or encoding.size == 0:
                log.debug("empty encoding for face")
                continue

            # Normalize encoding for cosine similarity
            encoding_norm = encoding / (np.linalg.norm(encoding) + 1e-8)

            # Landmarks (5-point, already provided by InsightFace)
            landmarks = det.kps if hasattr(det, "kps") and det.kps is not None else None

            # Alignment using InsightFace landmarks. Kept for display/storage
            # only: ArcFace's own preprocessing already warps the face to
            # 112x112 from the 5-point landmarks, so re-encoding our aligned
            # crop would only add variance between embeddings of one person.
            aligned_face = face_crop
            if self.enable_alignment and landmarks is not None:
                try:
                    aligned_face, _ = align_face(
                        face_crop,
                        landmarks.T if landmarks.shape == (2, 5) else landmarks,
                        self.alignment_config,
                    )
                except Exception:
                    aligned_face = face_crop

            # Liveness Detection
            liveness_result = None
            if self.enable_liveness and face_crop.size > 0:
                try:
                    face_gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
                    lm_np = landmarks.T if landmarks is not None else None
                    liveness_result = self.liveness_detector.update(
                        face_gray, lm_np, (l, t, r, b)
                    )
                    if not liveness_result.is_live:
                        continue
                except Exception:
                    pass

            # Database Matching (cosine distance for ArcFace embeddings)
            person_id = None
            confidence = 0.0
            name = None

            if known_encs:
                # Known vectors are filtered by dimension (the DB may still
                # hold 128-d dlib vectors) and L2-normalized once per frame,
                # not once per face. Uses separate names so the loop never
                # mutates the frame-level lists.
                if known_matrix is None:
                    dim = encoding_norm.shape[0]
                    filtered = [
                        (kid, np.asarray(ke, dtype=np.float32))
                        for kid, ke in zip(known_ids, known_encs)
                        if np.asarray(ke).shape[0] == dim
                    ]
                    if filtered:
                        match_ids = [kid for kid, _ in filtered]
                        known_matrix = np.array([
                            e / (np.linalg.norm(e) + 1e-8) for _, e in filtered
                        ])
                    else:
                        match_ids = []
                        known_matrix = np.empty((0, encoding_norm.shape[0]), np.float32)

                if known_matrix.shape[0] > 0:
                    similarities = known_matrix @ encoding_norm  # cosine similarity
                    best_idx = int(np.argmax(similarities))
                    best_sim = float(similarities[best_idx])

                    # ArcFace: cosine similarity above 1 - tolerance (0.4 by
                    # default) is treated as the same person.
                    arcface_min_sim = 1.0 - self.tolerance
                    if best_sim > arcface_min_sim:
                        person_id = match_ids[best_idx]

                    # Confidence from cosine similarity, discounted when the
                    # runner-up is nearly as close. A *ratio* of similarities
                    # is wrong here: cosine similarity can be negative or near
                    # zero, which makes the divisor meaningless. Use the margin.
                    if similarities.shape[0] >= 2:
                        sd = np.sort(similarities)[::-1]  # descending
                        margin = float(sd[0] - sd[1])
                        confidence = best_sim * min(1.0, 0.5 + margin)
                    else:
                        confidence = best_sim
                    confidence = max(0.0, min(1.0, confidence))

                    # Quality-weighted confidence
                    confidence = confidence * (0.5 + 0.5 * quality_score)

                    if person_id:
                        # Augmentation: only borderline views are worth
                        # storing. The band check lives in
                        # _maybe_augment_arcface, mirroring the dlib path.
                        if person_id.startswith("W"):
                            self._maybe_augment_arcface(
                                person_id, best_sim, encoding_norm, quality_score
                            )
                        person = self.db.get_person(person_id)
                        if person:
                            name = person["name"]

            result = {
                "box": (t, r, b, l),
                "bbox": np.array([l, t, r, b], dtype=np.float32),
                "person_id": person_id,
                "name": name,
                "confidence": round(confidence, 3),
                "encoding": encoding_norm,
                "quality": quality_metrics,
                "quality_score": quality_score,
                "liveness": liveness_result,
                "landmarks": landmarks,
                "aligned_face": aligned_face if self.enable_alignment else None,
                "det_score": det.det_score if hasattr(det, "det_score") else 0.0,
            }
            results.append(result)

        return results

    # ── face_recognition (dlib) Fallback Pipeline ──

    def _recognize_dlib(self, frame: np.ndarray) -> List[Dict]:
        """Fallback recognition using face_recognition (dlib)."""
        if not _FR_AVAILABLE:
            return []

        small = cv2.resize(frame, (0, 0), fx=self.process_scale, fy=self.process_scale)
        rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        rgb_full = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        locations = face_recognition.face_locations(rgb_small)
        if not locations:
            return []

        scale = int(1 / self.process_scale)
        # Detection is cheap at reduced scale, but the encoder must see the
        # full-resolution face: dlib's ResNet expects ~150px input, and encoding
        # a downscaled face produces vectors that don't compare against
        # full-resolution ones (distances drift well past `tolerance`).
        full_locations = [
            (t * scale, r * scale, b * scale, l * scale) for (t, r, b, l) in locations
        ]
        encodings = face_recognition.face_encodings(rgb_full, full_locations)
        known_ids, known_encs = self._get_known()
        results = []

        for (t_s, r_s, b_s, l_s), enc in zip(full_locations, encodings):
            face_crop = frame[t_s:b_s, l_s:r_s].copy()
            if face_crop.size == 0:
                continue

            # Quality gate
            quality_metrics = self.quality_assessor.assess(face_crop)
            quality_score = quality_metrics.overall_score
            if self.enable_quality_gate and quality_score < self.quality_threshold:
                continue

            # Landmarks on the face crop (shared by alignment and liveness)
            landmarks = None
            crop_rgb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
            try:
                fl = face_recognition.face_locations(crop_rgb)
                if fl:
                    flm = face_recognition.face_landmarks(crop_rgb, fl)
                    if flm:
                        landmarks = self._landmarks_to_array(flm[0])
            except Exception:
                pass

            # Alignment is kept for display/storage only. Re-encoding the
            # aligned 112x112 crop is deliberately skipped: dlib already aligns
            # internally from landmarks, so a second resize only adds variance
            # between encodings of the same person.
            aligned_face = face_crop
            if self.enable_alignment and landmarks is not None:
                try:
                    aligned_face, _ = align_face(
                        face_crop, landmarks, self.alignment_config
                    )
                except Exception:
                    aligned_face = face_crop

            # Liveness
            liveness_result = None
            if self.enable_liveness:
                face_gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
                liveness_result = self.liveness_detector.update(
                    face_gray, landmarks, (l_s, t_s, r_s, b_s)
                )
                if not liveness_result.is_live:
                    continue

            # DB matching
            person_id, confidence, name = self._match_dlib(enc, known_ids, known_encs, quality_score)

            result = {
                "box": (t_s, r_s, b_s, l_s),
                "bbox": np.array([l_s, t_s, r_s, b_s], dtype=np.float32),
                "person_id": person_id,
                "name": name,
                "confidence": round(confidence, 3),
                "encoding": enc,
                "quality": quality_metrics,
                "quality_score": quality_score,
                "liveness": liveness_result,
                "landmarks": landmarks,
                "aligned_face": aligned_face if self.enable_alignment else None,
                "det_score": 0.0,
            }
            results.append(result)

        return results

    def _match_dlib(
        self, enc: np.ndarray, known_ids: list, known_encs: list, quality_score: float
    ) -> Tuple[Optional[str], float, Optional[str]]:
        """Match encoding against DB using Euclidean distance."""
        if not known_encs:
            return None, 0.0, None

        # The DB may hold embeddings from the other engine (512-d ArcFace vs
        # 128-d dlib). Comparing across models is meaningless and would raise a
        # broadcast error, so keep only same-dimension vectors.
        filtered = [
            (kid, ke) for kid, ke in zip(known_ids, known_encs)
            if np.asarray(ke).shape[0] == enc.shape[0]
        ]
        if not filtered:
            return None, 0.0, None
        known_ids, known_encs = [list(x) for x in zip(*filtered)]

        dists = face_recognition.face_distance(known_encs, enc)
        best = int(np.argmin(dists))
        best_dist = float(dists[best])

        if best_dist > self.tolerance:
            return None, 0.0, None

        confidence = 0.6
        if len(dists) >= 2:
            sd = np.sort(dists)
            confidence = max(0.0, 1.0 - sd[0] / max(sd[1], 1e-6))
        confidence = confidence * (0.5 + 0.5 * quality_score)

        person_id = known_ids[best]

        if person_id.startswith("W"):
            self._maybe_augment(person_id, best_dist, enc, quality_score)

        person = self.db.get_person(person_id)
        name = person["name"] if person else None
        return person_id, confidence, name

    # ── Tracking ──

    def _apply_tracking(self, results: List[Dict]) -> List[Dict]:
        """Apply multi-face tracking + temporal smoothing."""
        detections = [r["bbox"] for r in results]
        identities = [r["person_id"] for r in results]
        confidences = [r["confidence"] for r in results]
        qualities = [r.get("quality_score", 0.5) for r in results]

        self.tracker.update(detections, identities, confidences, qualities)
        track_identities = self.tracker.get_track_identities()

        for result in results:
            track_id = self._match_to_track(result["bbox"], self.tracker.tracks)
            result["track_id"] = track_id
            if track_id and track_id in track_identities:
                smoothed_id = track_identities[track_id]
                if smoothed_id:
                    result["person_id"] = smoothed_id
                    person = self.db.get_person(smoothed_id)
                    if person:
                        result["name"] = person["name"]

        return results

    # ── Helpers ──

    @staticmethod
    def _landmarks_to_array(landmarks_dict: Dict) -> np.ndarray:
        """Convert face_recognition landmarks dict to (68, 2) array."""
        points = []
        order = [
            "chin", "left_eyebrow", "right_eyebrow", "nose_bridge",
            "nose_tip", "left_eye", "right_eye", "top_lip", "bottom_lip",
        ]
        for key in order:
            if key in landmarks_dict:
                for pt in landmarks_dict[key]:
                    points.append(pt)
        return np.array(points, dtype=np.float32)

    def _match_to_track(self, bbox: np.ndarray, tracks: Dict) -> Optional[str]:
        """Match bbox to track by IoU."""
        best_iou, best_track_id = 0, None
        for tid, track in tracks.items():
            if track.confirmed:
                pred = track.predict()
                iou = self._compute_iou(bbox, pred)
                if iou > 0.3 and iou > best_iou:
                    best_iou = iou
                    best_track_id = tid
        return best_track_id

    @staticmethod
    def _compute_iou(box1: np.ndarray, box2: np.ndarray) -> float:
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        if x2 <= x1 or y2 <= y1:
            return 0.0
        inter = (x2 - x1) * (y2 - y1)
        a1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        a2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        return inter / max(a1 + a2 - inter, 1e-6)

    # ── Augmentation ──

    def _maybe_augment(self, pid: str, dist: float, enc: np.ndarray, quality: float):
        if quality < self.quality_threshold:
            return
        now = datetime.now()
        if now - self._last_augment.get(pid, datetime.min) < self.augment_cooldown:
            return
        if self.augment_min_distance < dist < self.tolerance:
            if self.db.add_encoding_to_worker(pid, enc, self.max_encodings):
                self._last_augment[pid] = datetime.now()

    def _maybe_augment_arcface(
        self, pid: str, sim: float, enc: np.ndarray, quality: float
    ):
        """Augmentation for ArcFace (cosine similarity based).

        Mirrors `_maybe_augment`, translated from distance to similarity:
        `dist ≈ 1 - sim`, so the dlib band
        `augment_min_distance < dist < tolerance` becomes
        `1 - tolerance < sim < 1 - augment_min_distance`. Near-duplicates
        (sim above the upper bound) are skipped so they don't consume the
        `max_encodings` budget.
        """
        if quality < self.quality_threshold:
            return
        now = datetime.now()
        if now - self._last_augment.get(pid, datetime.min) < self.augment_cooldown:
            return
        if (1.0 - self.tolerance) < sim < (1.0 - self.augment_min_distance):
            if self.db.add_encoding_to_worker(pid, enc, self.max_encodings):
                self._last_augment[pid] = datetime.now()

    # ── Capture for Registration ──

    def capture_encodings(
        self, seed_enc: np.ndarray, count: int = 5, timeout: float = 5.0
    ) -> List[np.ndarray]:
        """Capture multiple diverse, high-quality encodings."""
        collected = [seed_enc]
        start = time.time()

        while len(collected) < count and time.time() - start < timeout:
            frame = self.read()
            if frame is None:
                break

            if self._use_insightface:
                dets = self._insightface_app.get(frame) if self._insightface_app else []
                for det in dets:
                    enc = det.embedding
                    if enc is None:
                        continue
                    enc_norm = enc / (np.linalg.norm(enc) + 1e-8)
                    if (1.0 - self.tolerance) < np.dot(enc_norm, seed_enc / (np.linalg.norm(seed_enc) + 1e-8)):
                        bbox = det.bbox.astype(np.int32)
                        face_crop = frame[bbox[1]:bbox[3], bbox[0]:bbox[2]]
                        if face_crop.size > 0 and quick_quality_check(face_crop):
                            collected.append(enc_norm)
                            break
            else:
                # Detect small, encode full-resolution: dlib's ResNet expects a
                # ~150px face, so encoding the downscaled crop yields vectors
                # that don't compare against the ones stored at full scale.
                small = cv2.resize(frame, (0, 0), fx=self.process_scale, fy=self.process_scale)
                rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                locs = face_recognition.face_locations(rgb_small)
                if locs:
                    scale = int(1 / self.process_scale)
                    full_locs = [
                        (t * scale, r * scale, b * scale, l * scale)
                        for (t, r, b, l) in locs
                    ]
                    rgb_full = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    encs = face_recognition.face_encodings(rgb_full, full_locs)
                    for (t, r, b, l), enc in zip(full_locs, encs):
                        if face_recognition.face_distance([seed_enc], enc)[0] <= self.tolerance:
                            face_crop = frame[t:b, l:r]
                            if face_crop.size > 0 and quick_quality_check(face_crop):
                                collected.append(enc)
                            break

            cv2.putText(
                frame, f"Capture: {len(collected)}/{count}", (20, 40),
                cv2.FONT_HERSHEY_DUPLEX, 0.8, (0, 200, 0), 2,
            )
            cv2.imshow("CV Attendance", frame)
            cv2.waitKey(1)

        return collected

    # ── Visualization ──

    @staticmethod
    def draw_boxes(frame: np.ndarray, results: List[Dict]):
        """Draw bounding boxes with enhanced info."""
        for r in results:
            t, ri, b, l = r["box"]
            track_id = r.get("track_id", "")
            quality_score = r.get("quality_score", 0)
            liveness = r.get("liveness")

            color = (0, 200, 0) if r["person_id"] else (0, 140, 255)
            name = r["name"] or r["person_id"] or "?"
            conf = r["confidence"]

            label_parts = [name]
            if conf > 0.01:
                label_parts.append(f"{int(conf*100)}%")
            if quality_score > 0:
                label_parts.append(f"Q:{quality_score:.2f}")
            if liveness:
                label_parts.append(f"L:{liveness.score:.2f}")
            if track_id:
                label_parts.append(f"T:{track_id[1:]}")

            label = " | ".join(label_parts)

            cv2.rectangle(frame, (l, t), (ri, b), color, 2)
            cv2.rectangle(frame, (l, b - 28), (ri, b), color, cv2.FILLED)
            cv2.putText(
                frame, label, (l + 4, b - 6),
                cv2.FONT_HERSHEY_DUPLEX, 0.5, (255, 255, 255), 1,
            )

    # ── CLI Loop ──

    def run(self, on_unknown, on_known=None, hud=None):
        if not self.open():
            print("[!] Camera not available")
            return
        print(f"[FaceRecognizer] Engine: {self.engine_name}")
        print("Camera ready — press 'q' to quit.\n")
        try:
            while True:
                frame = self.read()
                if frame is None:
                    break
                results = self.recognize(frame)
                unknown = None
                for r in results:
                    pid = r["person_id"]
                    if pid is None:
                        if unknown is None and r["encoding"].size > 0:
                            unknown = (r["box"], r["encoding"])
                        continue
                    if r["name"] and on_known:
                        on_known(pid, r["name"])
                self.draw_boxes(frame, results)
                if hud:
                    y = 28
                    for line in hud():
                        cv2.putText(
                            frame, line, (16, y),
                            cv2.FONT_HERSHEY_DUPLEX, 0.6,
                            (255, 255, 255), 1, cv2.LINE_AA,
                        )
                        y += 26
                if unknown:
                    box, enc = unknown
                    cv2.rectangle(frame, (box[3], box[0]), (box[1], box[2]),
                                  (0, 140, 255), 2)
                    cv2.putText(frame, "New face", (20, frame.shape[0] - 20),
                                cv2.FONT_HERSHEY_DUPLEX, 0.65, (0, 140, 255), 2)
                    cv2.imshow("CV Attendance", frame)
                    cv2.waitKey(1)
                    on_unknown(
                        enc,
                        frame[box[0] : box[2], box[3] : box[1]].copy()
                        if box[0] < box[2] and box[3] < box[1]
                        else None,
                    )
                else:
                    cv2.imshow("CV Attendance", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
        finally:
            self.close()
