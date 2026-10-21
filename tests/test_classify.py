"""Offline checks for classify.py, using a fake client instead of the real API."""

import csv
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import classify  # noqa: E402
import config  # noqa: E402


class FakeClient:
    """Stands in for anthropic.Anthropic. `reply` decides the response text for each call."""

    def __init__(self, reply):
        self.reply = reply
        self.calls = []
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = self.reply(kwargs, len(self.calls))
        usage = SimpleNamespace(input_tokens=100, output_tokens=20,
                                cache_read_input_tokens=0, cache_creation_input_tokens=0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)],
                               usage=usage, stop_reason="end_turn")


def frame_times(kwargs):
    """Timestamps the fake model was shown, read back from the request."""
    texts = [block["text"] for block in kwargs["messages"][0]["content"] if block["type"] == "text"]
    return [float(text.split("t=")[1].split(" ")[0]) for text in texts if text.startswith("Frame at")]


def good_reply(kwargs, call_number):
    return json.dumps({"frames": [{"t": t, "step": "read_fields", "confidence": 0.9} for t in frame_times(kwargs)]})


@pytest.fixture
def run_dir(tmp_path, monkeypatch):
    """20 tiny fake frames (3 batches of 8, 8, 4) and temp output folders."""
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "PREDICTIONS_DIR", tmp_path / "predictions")
    frames_dir = tmp_path / "frames" / "run_01"
    frames_dir.mkdir(parents=True)
    rows = []
    for i in range(20):
        (frames_dir / f"frame_{i:04d}.jpg").write_bytes(f"fake image {i}".encode())
        rows.append((f"frame_{i:04d}.jpg", float(i * 2)))
    with open(frames_dir / "frames.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([("file", "t")] + rows)
    return frames_dir


def read_predictions(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_writes_predictions_and_uses_cache(run_dir):
    client = FakeClient(good_reply)
    stats = classify.new_stats()
    path = classify.classify_run(client, "test-model", run_dir, stats)

    rows = read_predictions(path)
    assert len(rows) == 20
    assert rows[0] == {"t": "0.0", "step": "read_fields", "confidence": "0.9"}
    assert stats["api_calls"] == 3
    assert classify.estimate_calls("test-model", [run_dir]) == 0

    # Second run: everything comes from the cache, no API calls
    stats = classify.new_stats()
    classify.classify_run(client, "test-model", run_dir, stats)
    assert stats["api_calls"] == 0 and stats["cache_hits"] == 3
    assert len(client.calls) == 3


def test_previous_label_is_passed_on(run_dir):
    def reply(kwargs, call_number):
        step = ["open_invoice", "type_vendor", "submit"][call_number - 1]
        return json.dumps({"frames": [{"t": t, "step": step, "confidence": 0.8} for t in frame_times(kwargs)]})

    client = FakeClient(reply)
    classify.classify_run(client, "test-model", run_dir, classify.new_stats())
    last_texts = [call["messages"][0]["content"][-1]["text"] for call in client.calls]
    assert "none" in last_texts[0]
    assert "labeled: open_invoice" in last_texts[1]
    assert "labeled: type_vendor" in last_texts[2]


def test_malformed_json_retries_once_then_marks_unclear(run_dir):
    def reply(kwargs, call_number):
        if call_number <= 2:
            return "not json at all"          # first batch fails twice
        return good_reply(kwargs, call_number)

    client = FakeClient(reply)
    stats = classify.new_stats()
    path = classify.classify_run(client, "test-model", run_dir, stats)

    rows = read_predictions(path)
    assert [row["step"] for row in rows[:8]] == ["unclear"] * 8
    assert [row["step"] for row in rows[8:]] == ["read_fields"] * 12
    assert stats["api_calls"] == 4 and stats["unclear_batches"] == 1
    assert "marked unclear" in (config.PREDICTIONS_DIR / "problems.log").read_text(encoding="utf-8")


def test_wrong_frame_count_counts_as_malformed(run_dir):
    def reply(kwargs, call_number):
        if call_number == 1:
            return json.dumps({"frames": [{"t": 0, "step": "idle", "confidence": 1}]})  # too few
        return good_reply(kwargs, call_number)

    client = FakeClient(reply)
    stats = classify.new_stats()
    path = classify.classify_run(client, "test-model", run_dir, stats)
    assert read_predictions(path)[0]["step"] == "read_fields"   # the retry succeeded
    assert stats["api_calls"] == 4 and stats["unclear_batches"] == 0


def test_estimate_calls_before_any_run(run_dir):
    assert classify.estimate_calls("test-model", [run_dir]) == 3
