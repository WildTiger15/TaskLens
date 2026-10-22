"""Checks smoothing, merging and time study metrics on hand-made label sequences."""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import segment  # noqa: E402


def test_smooth_removes_single_frame_flip_only():
    steps = ["read_fields", "type_vendor", "read_fields", "read_fields", "type_date", "type_total"]
    assert segment.smooth(steps) == ["read_fields", "read_fields", "read_fields",
                                     "read_fields", "type_date", "type_total"]


def test_to_segments_covers_whole_recording():
    times = [0, 2, 4, 6]
    steps = ["open_invoice", "open_invoice", "read_fields", "read_fields"]
    segs = segment.to_segments(times, steps, interval=2)
    assert segs == [{"step": "open_invoice", "start_s": 0, "end_s": 4},
                    {"step": "read_fields", "start_s": 4, "end_s": 8}]


def test_merge_short_uses_longer_neighbor():
    segs = [{"step": "type_vendor", "start_s": 0, "end_s": 6},
            {"step": "unclear", "start_s": 6, "end_s": 7},
            {"step": "type_date", "start_s": 7, "end_s": 9}]
    assert segment.merge_short(segs, min_s=2) == [{"step": "type_vendor", "start_s": 0, "end_s": 7},
                                                  {"step": "type_date", "start_s": 7, "end_s": 9}]


def test_merge_short_joins_matching_neighbors():
    segs = [{"step": "type_total", "start_s": 0, "end_s": 3},
            {"step": "idle", "start_s": 3, "end_s": 4},
            {"step": "type_total", "start_s": 4, "end_s": 6}]
    assert segment.merge_short(segs, min_s=2) == [{"step": "type_total", "start_s": 0, "end_s": 6}]


def test_metrics_with_rework():
    segs = [{"step": "idle", "start_s": 0, "end_s": 4},
            {"step": "open_invoice", "start_s": 4, "end_s": 8},
            {"step": "read_fields", "start_s": 8, "end_s": 16},
            {"step": "type_total", "start_s": 16, "end_s": 20},
            {"step": "submit", "start_s": 20, "end_s": 22},
            {"step": "fix_error", "start_s": 22, "end_s": 28},
            {"step": "read_fields", "start_s": 28, "end_s": 32},   # went back to the PDF: a repeat
            {"step": "submit", "start_s": 32, "end_s": 34},        # second submit: a repeat
            {"step": "unclear", "start_s": 34, "end_s": 36}]
    m = segment.run_metrics(segs)
    assert m["cycle_s"] == 36
    assert m["wait_s"] == 4
    assert m["unclear_s"] == 2
    assert m["touch_s"] == 30
    assert m["fix_error_count"] == 1 and m["fix_error_s"] == 6
    assert m["repeat_step_count"] == 2 and m["repeat_step_s"] == 6
    assert m["rework_s"] == 12
    assert m["cycle_s"] == m["touch_s"] + m["wait_s"] + m["unclear_s"]


def test_process_model_writes_outputs(tmp_path):
    pred_dir = tmp_path / "predictions"
    pred_dir.mkdir()
    rows = [(0, "open_invoice", 0.9), (2, "open_invoice", 0.9), (4, "read_fields", 0.5),
            (6, "read_fields", 0.8), (8, "type_vendor", 0.95), (10, "submit", 0.7)]
    with open(pred_dir / "run_01.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([("t", "step", "confidence")] + rows)

    metric_rows, review_count, out_dir = segment.process_model("test-model", pred_dir, tmp_path / "out")

    assert metric_rows[0]["run"] == "run_01"
    assert metric_rows[0]["cycle_s"] == 12
    assert review_count == 1  # only the 0.5 frame is below 0.6
    for name in ("segments.csv", "run_metrics.csv", "review_list.csv"):
        assert (out_dir / name).exists()
