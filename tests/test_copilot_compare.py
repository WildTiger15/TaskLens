"""Checks the manual vs assisted comparison on made-up timings."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import copilot_compare  # noqa: E402


def timings(manual, assisted, name="copilot"):
    rows = [{"run_id": f"m{i}", "condition": "manual", "total_seconds": s, "errors": 0} for i, s in enumerate(manual)]
    rows += [{"run_id": f"a{i}", "condition": name, "total_seconds": s, "errors": 1} for i, s in enumerate(assisted)]
    return pd.DataFrame(rows)


def test_describe():
    s = copilot_compare.describe([10, 20, 30, 40])
    assert s["n"] == 4 and s["mean"] == 25 and s["median"] == 25
    assert round(s["sd"], 3) == 12.910


def test_overlapping_groups_give_no_clear_difference():
    manual = [70, 85, 62, 90, 75, 80, 68, 88]
    assisted = [72, 83, 66, 87, 78, 79, 70, 85]
    stats, comparisons = copilot_compare.compare(timings(manual, assisted))
    c = comparisons[0]
    assert c["low"] < 0 < c["high"]
    assert c["conclusion"].startswith("No clear difference")
    assert stats["copilot"]["mean_errors"] == 1


def test_clearly_faster_group():
    manual = [80, 82, 85, 79, 81, 84, 83, 80]
    assisted = [60, 62, 61, 59, 63, 60, 62, 61]
    _, comparisons = copilot_compare.compare(timings(manual, assisted))
    c = comparisons[0]
    assert c["difference"] == -20.75          # 61.0 - 81.75
    assert c["high"] < 0
    assert "faster" in c["conclusion"] and "first signal" in c["conclusion"]


def test_bootstrap_is_reproducible():
    a, b = [60, 70, 80, 75], [65, 72, 90, 85]
    assert copilot_compare.bootstrap_ci(a, b) == copilot_compare.bootstrap_ci(a, b)


def test_report_mentions_claude_and_small_n(tmp_path):
    data = timings([70, 80, 75], [65, 72, 78], name="Claude")
    stats, comparisons = copilot_compare.compare(copilot_compare.clean_timings(data))
    out = tmp_path / "report.md"
    copilot_compare.write_report(stats, comparisons, out)
    text = out.read_text(encoding="utf-8")
    assert "| manual | 3 |" in text
    assert "Claude was used as the assistant" in text
    assert "fewer than 8 runs" in text
