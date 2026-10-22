"""Turn per frame step labels into timed segments and time study metrics.

Steps:
  1. Smooth single frame flips with a small majority window.
  2. Join consecutive frames with the same label into segments.
     Each frame covers the time from its timestamp to the next frame's timestamp.
  3. Merge segments shorter than config.MIN_SEGMENT_S into a neighbor.
  4. Compute cycle, touch, wait and rework time per run.
  5. List frames with confidence below config.LOW_CONFIDENCE for human review.

Usage:
  python src/segment.py                       # predictions from config.MODEL
  python src/segment.py --model claude-haiku-5-5
Output (in outputs/<model>/): segments.csv, run_metrics.csv, review_list.csv
"""

import argparse
import csv
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

NOT_TOUCH = {"idle", "unclear"}             # everything else counts as touch time
NOT_REPEAT_CHECKED = {"idle", "unclear", "fix_error"}


# ---------- reading ----------

def read_predictions(path):
    """List of dicts with t (float), step and confidence (float), sorted by time."""
    with open(path, encoding="utf-8") as f:
        rows = [{"t": float(r["t"]), "step": r["step"], "confidence": float(r["confidence"])}
                for r in csv.DictReader(f)]
    return sorted(rows, key=lambda r: r["t"])


def frame_interval(times):
    """Typical gap between frames. Falls back to the configured interval."""
    gaps = [b - a for a, b in zip(times, times[1:])]
    return statistics.median(gaps) if gaps else config.FRAME_INTERVAL_S


# ---------- smoothing and segments ----------

def smooth(steps, window=config.SMOOTH_WINDOW):
    """Replace a label by the most common label in the window around it.
    On a tie the original label is kept, so real step changes are not shifted."""
    half = window // 2
    smoothed = []
    for i, step in enumerate(steps):
        counts = Counter(steps[max(0, i - half): i + half + 1]).most_common()
        top_step, top_count = counts[0]
        tied = len(counts) > 1 and counts[1][1] == top_count
        smoothed.append(step if tied else top_step)
    return smoothed


def to_segments(times, steps, interval):
    """Join runs of the same label. Each segment is a dict with step, start_s, end_s."""
    segments = []
    for i, (t, step) in enumerate(zip(times, steps)):
        end = times[i + 1] if i + 1 < len(times) else t + interval
        if segments and segments[-1]["step"] == step:
            segments[-1]["end_s"] = end
        else:
            segments.append({"step": step, "start_s": t, "end_s": end})
    return segments


def duration(segment):
    return segment["end_s"] - segment["start_s"]


def join_same_neighbors(segments):
    joined = []
    for seg in segments:
        if joined and joined[-1]["step"] == seg["step"]:
            joined[-1]["end_s"] = seg["end_s"]
        else:
            joined.append(dict(seg))
    return joined


def merge_short(segments, min_s=config.MIN_SEGMENT_S):
    """Merge the shortest segment under min_s into a neighbor, repeat until none are left.
    The segment takes the label of its longer neighbor (or of both, if they match)."""
    segments = [dict(s) for s in segments]
    while len(segments) > 1:
        short = [i for i, s in enumerate(segments) if duration(s) < min_s - 1e-9]
        if not short:
            break
        i = min(short, key=lambda k: duration(segments[k]))
        before = segments[i - 1] if i > 0 else None
        after = segments[i + 1] if i + 1 < len(segments) else None
        if before is None or (after is not None and duration(after) > duration(before)):
            segments[i]["step"] = after["step"]
        else:
            segments[i]["step"] = before["step"]
        segments = join_same_neighbors(segments)
    return segments


def segment_predictions(rows):
    """Full pipeline for one run: smooth, segment, merge short pieces."""
    times = [r["t"] for r in rows]
    steps = smooth([r["step"] for r in rows])
    return merge_short(to_segments(times, steps, frame_interval(times)))


# ---------- time study metrics ----------

def run_metrics(segments):
    """Cycle, touch, wait and rework time for one run, in seconds.

    Rework = fix_error segments, plus any task step that shows up again after a
    different step had started (for example a second submit, or going back to read the PDF).
    """
    cycle = segments[-1]["end_s"] - segments[0]["start_s"] if segments else 0.0
    touch = sum(duration(s) for s in segments if s["step"] not in NOT_TOUCH)
    wait = sum(duration(s) for s in segments if s["step"] == "idle")
    unclear = sum(duration(s) for s in segments if s["step"] == "unclear")

    fix_errors = [s for s in segments if s["step"] == "fix_error"]
    seen = set()
    repeats = []
    for s in segments:
        if s["step"] in NOT_REPEAT_CHECKED:
            continue
        if s["step"] in seen:
            repeats.append(s)
        seen.add(s["step"])

    fix_error_s = sum(duration(s) for s in fix_errors)
    repeat_s = sum(duration(s) for s in repeats)
    return {
        "cycle_s": round(cycle, 3),
        "touch_s": round(touch, 3),
        "wait_s": round(wait, 3),
        "unclear_s": round(unclear, 3),
        "fix_error_count": len(fix_errors),
        "fix_error_s": round(fix_error_s, 3),
        "repeat_step_count": len(repeats),
        "repeat_step_s": round(repeat_s, 3),
        "rework_s": round(fix_error_s + repeat_s, 3),
        "segment_count": len(segments),
    }


def low_confidence_frames(rows, threshold=config.LOW_CONFIDENCE):
    return [r for r in rows if r["confidence"] < threshold]


# ---------- whole study ----------

def write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def frame_file_lookup(run_name):
    """Map timestamp -> frame file, so reviewers can open the exact image."""
    frames_csv = config.FRAMES_DIR / run_name / "frames.csv"
    if not frames_csv.exists():
        return {}
    with open(frames_csv, encoding="utf-8") as f:
        return {float(r["t"]): str(Path("data/frames") / run_name / r["file"]) for r in csv.DictReader(f)}


def process_model(model, predictions_dir=None, out_dir=None):
    """Segment every run for one model and write the three output CSVs. Returns the metrics rows."""
    predictions_dir = Path(predictions_dir or config.PREDICTIONS_DIR / model)
    out_dir = Path(out_dir or config.OUTPUTS_DIR / model)
    prediction_files = sorted(predictions_dir.glob("run_*.csv"))
    if not prediction_files:
        raise FileNotFoundError(f"No predictions in {predictions_dir}. Run src/classify.py first.")

    segment_rows, metric_rows, review_rows = [], [], []
    for path in prediction_files:
        run_name = path.stem
        rows = read_predictions(path)
        segments = segment_predictions(rows)

        for order, s in enumerate(segments, start=1):
            segment_rows.append((run_name, order, s["step"], round(s["start_s"], 3),
                                 round(s["end_s"], 3), round(duration(s), 3)))
        metrics = run_metrics(segments)
        metric_rows.append({"run": run_name, **metrics})

        files = frame_file_lookup(run_name)
        for r in low_confidence_frames(rows):
            review_rows.append((run_name, r["t"], r["step"], r["confidence"], files.get(r["t"], "")))

    write_csv(out_dir / "segments.csv", ["run", "order", "step", "start_s", "end_s", "duration_s"], segment_rows)
    write_csv(out_dir / "run_metrics.csv", list(metric_rows[0].keys()), [list(m.values()) for m in metric_rows])
    write_csv(out_dir / "review_list.csv", ["run", "t", "predicted_step", "confidence", "frame_file"], review_rows)
    return metric_rows, len(review_rows), out_dir


def main():
    parser = argparse.ArgumentParser(description="Segment predictions and compute time study metrics.")
    parser.add_argument("--model", default=config.MODEL)
    args = parser.parse_args()

    metric_rows, review_count, out_dir = process_model(args.model)
    print(f"{'run':<10}{'cycle':>8}{'touch':>8}{'wait':>8}{'rework':>8}{'fixes':>7}{'repeats':>9}")
    for m in metric_rows:
        print(f"{m['run']:<10}{m['cycle_s']:>8.1f}{m['touch_s']:>8.1f}{m['wait_s']:>8.1f}"
              f"{m['rework_s']:>8.1f}{m['fix_error_count']:>7}{m['repeat_step_count']:>9}")
    print(f"\nn = {len(metric_rows)} runs. {review_count} low confidence frames "
          f"(below {config.LOW_CONFIDENCE}) listed for human review.")
    print(f"Wrote segments.csv, run_metrics.csv and review_list.csv to {out_dir}")


if __name__ == "__main__":
    main()
