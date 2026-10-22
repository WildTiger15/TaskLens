"""Checks the evaluation metrics on hand-made labels and predictions."""

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import config  # noqa: E402
import evaluate  # noqa: E402

TRUE = [{"step": "open_invoice", "start_s": 0, "end_s": 4},
        {"step": "read_fields", "start_s": 4, "end_s": 10},
        {"step": "type_vendor", "start_s": 10, "end_s": 14},
        {"step": "submit", "start_s": 14, "end_s": 16}]


def predictions(steps, interval=2):
    return [{"t": i * interval, "step": step, "confidence": 0.9} for i, step in enumerate(steps)]


def test_perfect_prediction():
    rows = predictions(["open_invoice"] * 2 + ["read_fields"] * 3 + ["type_vendor"] * 2 + ["submit"])
    metrics, step_errors, _ = evaluate.evaluate_run(TRUE, rows)
    assert metrics["frame_accuracy"] == 1.0
    assert metrics["frame_accuracy_raw"] == 1.0
    assert metrics["cycle_abs_error_s"] == 0
    assert metrics["order_distance"] == 0
    assert max(step_errors.values()) == 0
    assert metrics["seconds_compared"] == 16


def test_one_step_late():
    # read_fields predicted 2 s too long, type_vendor 2 s too short
    rows = predictions(["open_invoice"] * 2 + ["read_fields"] * 4 + ["type_vendor"] + ["submit"])
    metrics, step_errors, pairs = evaluate.evaluate_run(TRUE, rows)
    assert metrics["frame_accuracy_raw"] == 14 / 16
    assert step_errors["read_fields"] == 2 and step_errors["type_vendor"] == 2
    assert metrics["order_distance"] == 0


def test_wrong_step_changes_order_distance():
    rows = predictions(["open_invoice"] * 2 + ["read_fields"] * 3 + ["type_date"] * 2 + ["submit"])
    metrics, _, pairs = evaluate.evaluate_run(TRUE, rows)
    assert metrics["order_distance"] == 0.25          # 1 of 4 steps substituted
    seconds, spans = evaluate.confusion_examples({"run_01": pairs})
    assert seconds[("type_vendor", "type_date")] == 4
    assert spans[("type_vendor", "type_date")] == [["run_01", 10, 14]]


def test_edit_distance():
    assert evaluate.edit_distance(list("abc"), list("abc")) == 0
    assert evaluate.edit_distance(list("abc"), list("ac")) == 1
    assert evaluate.edit_distance([], list("ab")) == 2


def test_check_hand_labels_finds_mistakes():
    bad = [{"step": "open_invoice", "start_s": 0, "end_s": 5},
           {"step": "read_field", "start_s": 4, "end_s": 8},      # typo and overlap
           {"step": "submit", "start_s": 10, "end_s": 9}]         # gap and end before start
    problems = evaluate.check_hand_labels(bad)
    assert any("unknown step 'read_field'" in p for p in problems)
    assert any("overlaps" in p for p in problems)
    assert any("gap" in p for p in problems)
    assert any("not after" in p for p in problems)
    assert evaluate.check_hand_labels(TRUE) == []


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def test_full_evaluation_writes_outputs(tmp_path, monkeypatch):
    for name in ("PREDICTIONS_DIR", "LABELS_DIR", "FRAMES_DIR", "OUTPUTS_DIR", "CACHE_DIR"):
        monkeypatch.setattr(config, name, tmp_path / name.lower())
    write_csv(config.LABELS_DIR / "run_01.csv",
              [("step", "start_s", "end_s")] + [(s["step"], s["start_s"], s["end_s"]) for s in TRUE])
    steps = ["open_invoice"] * 2 + ["read_fields"] * 3 + ["type_date"] * 2 + ["submit"]
    write_csv(config.PREDICTIONS_DIR / "model-a" / "run_01.csv",
              [("t", "step", "confidence")] + [(i * 2, s, 0.9) for i, s in enumerate(steps)])

    evaluate.run_evaluation()

    summary = (config.OUTPUTS_DIR / "evaluation_summary.md").read_text(encoding="utf-8")
    assert "| model-a | 1 | 16 | 75.0% |" in summary
    assert "| type_vendor | type_date | 4 |" in summary
    assert "{To be written" in summary
    for name in ("metrics.csv", "step_errors.csv", "confusions.csv"):
        assert (config.OUTPUTS_DIR / name).exists()
