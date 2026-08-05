"""
Unit tests for FaceRecognizer matching/augmentation logic.

These run without a camera and without InsightFace: the recognizer is built
with `prefer_insightface=False` so only pure-python decision logic is touched.
"""
import numpy as np
import pytest

from face_recognizer import FaceRecognizer


@pytest.fixture
def recognizer(repo):
    return FaceRecognizer(
        repo,
        tolerance=0.6,
        augment_min_distance=0.2,
        quality_threshold=0.4,
        prefer_insightface=False,
        enable_tracking=False,
        enable_liveness=False,
    )


def sample_count(repo) -> int:
    return repo.list_workers_detailed()[0]["sample_count"]


class TestArcFaceAugmentBand:
    """`_maybe_augment_arcface` must mirror the dlib distance band."""

    def test_near_duplicate_is_skipped(self, recognizer, repo):
        repo.add_worker("Alice", [np.ones(512)])
        # sim 0.95 -> dist 0.05, below augment_min_distance: redundant sample
        recognizer._maybe_augment_arcface("W001", 0.95, np.ones(512), 0.9)
        assert sample_count(repo) == 1

    def test_borderline_view_is_stored(self, recognizer, repo):
        repo.add_worker("Alice", [np.ones(512)])
        # sim 0.6 -> dist 0.4: inside (0.2, 0.6)
        recognizer._maybe_augment_arcface("W001", 0.6, np.ones(512), 0.9)
        assert sample_count(repo) == 2

    def test_non_match_is_skipped(self, recognizer, repo):
        repo.add_worker("Alice", [np.ones(512)])
        # sim 0.1 -> dist 0.9, past tolerance: not the same person
        recognizer._maybe_augment_arcface("W001", 0.1, np.ones(512), 0.9)
        assert sample_count(repo) == 1

    def test_low_quality_is_skipped(self, recognizer, repo):
        repo.add_worker("Alice", [np.ones(512)])
        recognizer._maybe_augment_arcface("W001", 0.6, np.ones(512), 0.1)
        assert sample_count(repo) == 1

    def test_cooldown_blocks_second_call(self, recognizer, repo):
        repo.add_worker("Alice", [np.ones(512)])
        recognizer._maybe_augment_arcface("W001", 0.6, np.ones(512), 0.9)
        recognizer._maybe_augment_arcface("W001", 0.55, np.ones(512), 0.9)
        assert sample_count(repo) == 2


class TestDimensionFilter:
    """512-d ArcFace and 128-d dlib vectors must never be compared."""

    def test_mismatched_dimension_yields_no_match(self, recognizer, repo):
        repo.add_worker("Alice", [np.ones(512)])
        known_ids, known_encs = repo.get_all_known()
        pid, conf, name = recognizer._match_dlib(
            np.zeros(128), known_ids, known_encs, 0.9
        )
        assert pid is None
        assert name is None

    def test_matching_dimension_is_compared(self, recognizer, repo):
        enc = np.zeros(128)
        repo.add_worker("Alice", [enc])
        known_ids, known_encs = repo.get_all_known()
        pid, conf, name = recognizer._match_dlib(enc, known_ids, known_encs, 0.9)
        assert pid == "W001"
        assert name == "Alice"
