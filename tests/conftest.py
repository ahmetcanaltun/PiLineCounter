"""Test fixtures.

The camera stack (OpenCV, ultralytics, picamera2) is heavy and irrelevant to the
logic under test, so it is stubbed before `app` is imported. That keeps CI to a
plain `pip install flask pytest` instead of pulling a multi-gigabyte runtime.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _module in ("cv2", "numpy", "ultralytics", "picamera2", "libcamera"):
    sys.modules.setdefault(_module, MagicMock())


class FakeProcessor:
    """Stands in for CameraProcessor, recording what the routes ask of it."""

    def __init__(self):
        self.data = {
            "counts": {"in": 7, "out": 3},
            "line": [427, 0, 427, 480],
            "mode": "person",
            "flip_direction": False,
            "roi": None,
            "fps": 9.7,
            "resolution": [854, 480],
        }
        self.config_updates = []
        self.roi_updates = []
        self.resets = 0

    def get_data(self):
        return dict(self.data)

    def get_latest_records(self, n=50):
        return [{"from": "2026-07-27T10:00:00", "to": "2026-07-27T10:00:05", "in": 1, "out": 0}]

    def update_config(self, **kwargs):
        self.config_updates.append(kwargs)

    def update_roi(self, roi):
        self.roi_updates.append(roi)

    def reset_counts(self):
        self.resets += 1


@pytest.fixture
def processor():
    return FakeProcessor()


@pytest.fixture
def client(processor):
    """Flask test client wired to a fake processor and --monitor enabled."""
    import argparse

    import app as flask_app

    flask_app.processor = processor
    flask_app.args = argparse.Namespace(monitor=True, interval=5.0, video=None)
    flask_app.app.config["TESTING"] = True
    return flask_app.app.test_client()
