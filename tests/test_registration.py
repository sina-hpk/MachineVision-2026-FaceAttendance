"""
Unit tests for the registration session state machine.
"""
import numpy as np
import pytest

import registration
from registration import (
    ANGLE_STEPS,
    start_session,
    abort_session,
    get_session,
    update_session,
)


@pytest.fixture(autouse=True)
def clean_session():
    abort_session()
    yield
    abort_session()


def _expire_step(sess):
    """Make the current pose step due for capture."""
    sess.step_start_time -= sess.step_duration


class TestRegistrationSession:
    def test_start_session_once(self):
        assert start_session("Alice") is True
        assert start_session("Bob") is False
        assert get_session().name == "Alice"

    def test_no_capture_before_step_duration(self):
        start_session("Alice")
        update_session(np.zeros(128))
        sess = get_session()
        assert sess.step_index == 0
        assert sess.encodings == []

    def test_capture_advances_step(self):
        start_session("Alice")
        sess = get_session()
        _expire_step(sess)
        update_session(np.zeros(128), np.ones((10, 10, 3), dtype=np.uint8))
        assert sess.step_index == 1
        assert len(sess.encodings) == 1
        assert len(sess.face_crops) == 1

    def test_missing_face_holds_step_open(self):
        start_session("Alice")
        sess = get_session()
        _expire_step(sess)
        update_session(None)
        assert sess.step_index == 0
        assert sess.encodings == []
        assert "No face detected" in sess.result_message

    def test_full_run_collects_one_sample_per_step(self):
        start_session("Alice")
        sess = get_session()
        for _ in ANGLE_STEPS:
            _expire_step(sess)
            update_session(np.zeros(128))
        assert sess.is_done
        assert len(sess.encodings) == len(ANGLE_STEPS)

    def test_update_after_done_is_noop(self):
        start_session("Alice")
        sess = get_session()
        for _ in ANGLE_STEPS:
            _expire_step(sess)
            update_session(np.zeros(128))
        _expire_step(sess)
        update_session(np.zeros(128))
        assert len(sess.encodings) == len(ANGLE_STEPS)

    def test_abort_clears_session(self):
        start_session("Alice")
        abort_session()
        assert get_session() is None
