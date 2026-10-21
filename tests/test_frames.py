"""Checks frame count, timestamps and image size on a short generated video."""

import csv
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import frames  # noqa: E402

FPS = 10
SECONDS = 11


def make_test_video(path):
    """11 second, 1280x720 video. Each second has its own brightness (second * 20),
    so we can tell which second a sampled frame came from."""
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (1280, 720))
    for i in range(FPS * SECONDS):
        second = i // FPS
        writer.write(np.full((720, 1280, 3), second * 20, dtype=np.uint8))
    writer.release()


def test_sample_frames(tmp_path):
    video_path = tmp_path / "test.mp4"
    make_test_video(video_path)
    out_dir = tmp_path / "frames"

    rows = frames.sample_frames(video_path, out_dir, interval_s=2, width=1024)

    # Frames at 0, 2, 4, 6, 8 and 10 seconds
    assert len(rows) == 6
    assert [t for _, t in rows] == [0.0, 2.0, 4.0, 6.0, 8.0, 10.0]

    # frames.csv matches what was returned
    with open(out_dir / "frames.csv", encoding="utf-8") as f:
        saved = [(row["file"], float(row["t"])) for row in csv.DictReader(f)]
    assert saved == rows

    for file_name, t in rows:
        image = cv2.imread(str(out_dir / file_name))
        assert image.shape[:2] == (576, 1024)               # downscaled, aspect ratio kept
        assert abs(image.mean() - int(t) * 20) < 4           # content comes from the right second


def test_interval_of_one_second(tmp_path):
    video_path = tmp_path / "test.mp4"
    make_test_video(video_path)
    rows = frames.sample_frames(video_path, tmp_path / "frames", interval_s=1)
    assert len(rows) == SECONDS
