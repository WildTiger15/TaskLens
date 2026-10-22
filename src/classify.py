"""Label sampled frames with a step from steps.json using a Claude vision model.

Frames go to the model in batches of config.BATCH_SIZE. Each batch also gets the
last label of the previous batch, so batches inside one recording run in order.
Different recordings run in parallel. Every API response is cached on disk.

Usage:
  python src/classify.py run_01                 # one recording (frames from src/frames.py)
  python src/classify.py --all                  # every recording in data/frames
  python src/classify.py run_01 --model claude-haiku-5-5
  python src/classify.py --all --yes            # skip the >100 calls confirmation
Output: data/predictions/<model>/run_01.csv with columns t, step, confidence
"""

import argparse
import base64
import csv
import hashlib
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

STEPS = json.loads(config.STEPS_FILE.read_text(encoding="utf-8"))

# Bump this when the prompt changes, so old cached answers are not reused.
PROMPT_VERSION = "v1"

SYSTEM_PROMPT = f"""You label frames from screen recordings of one office task: invoice data entry.

In each recording a person opens a dummy invoice PDF, reads the vendor, date and total,
switches to a web form titled "Invoice Entry", types the three fields, clicks Submit, and
fixes the form if it shows a red error message.

You get a batch of consecutive frames, sampled every {config.FRAME_INTERVAL_S} seconds. Each frame
is preceded by its timestamp in seconds. Give each frame exactly one step label from this list.

Step labels and what they look like on screen:
- open_invoice: opening an invoice PDF. A file browser, a "recent files" list, a PDF viewer
  that is still loading, or the invoice appearing for the first time.
- read_fields: the invoice PDF is in front and the person is reading it. The mouse may hover
  or highlight the vendor name, the date or the TOTAL line. No typing is happening.
- switch_to_form: changing from the PDF to the form. Taskbar or alt-tab switcher visible,
  a browser tab being clicked, or the form appearing with no field focused yet.
- type_vendor: the Vendor field is focused or being filled in.
- type_date: the Invoice date field is focused or being filled in.
- type_total: the Total ($) field is focused or being filled in.
- submit: the Submit button is being clicked, or a green "Saved" message has just appeared
  after a submit.
- fix_error: a red "Error:" message is on the form and the person is correcting a field
  (a field with a red border is focused or its text is changing). Use this instead of
  type_vendor, type_date or type_total whenever the red error message is visible.
- idle: nothing related to the task is happening, for example a desktop with no change,
  the screen is static between runs, or the person is doing something unrelated.
- unclear: you cannot tell what is happening, for example a blurred or blank frame.

Rules:
- Use only the labels in the list above, spelled exactly as written.
- Consecutive frames usually share the same step. Change the label only when the screen
  shows the person has moved on. The label of the frame just before this batch is given
  for continuity.
- If two labels seem possible, pick the one that best matches what changed since the
  previous frame, and lower your confidence.
- confidence is a number from 0 to 1: how sure you are about that frame's label.
- Return one entry per frame, in the same order, with the same timestamp t you were given.
- Reply with JSON only, matching the requested schema. No other text."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "frames": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "t": {"type": "number"},
                    "step": {"type": "string", "enum": STEPS},
                    "confidence": {"type": "number"},
                },
                "required": ["t", "step", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["frames"],
    "additionalProperties": False,
}

log_lock = threading.Lock()


# ---------- reading frames ----------

def read_frames(frames_dir):
    """Return a list of (image path, t) from frames.csv."""
    with open(Path(frames_dir) / "frames.csv", encoding="utf-8") as f:
        return [(Path(frames_dir) / row["file"], float(row["t"])) for row in csv.DictReader(f)]


def make_batches(frames, size=config.BATCH_SIZE):
    return [frames[i:i + size] for i in range(0, len(frames), size)]


# ---------- disk cache ----------

def cache_key(batch, model, previous_label):
    """Hash of the frame images, timestamps, model, prompt version and previous label."""
    digest = hashlib.sha256()
    digest.update(f"{model}|{PROMPT_VERSION}|{previous_label}".encode())
    for path, t in batch:
        digest.update(f"|{t}|".encode())
        digest.update(Path(path).read_bytes())
    return digest.hexdigest()


def cache_path(key):
    return config.CACHE_DIR / f"{key}.json"


def load_cached(key):
    path = cache_path(key)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def save_cached(key, entry):
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path(key).write_text(json.dumps(entry, indent=1), encoding="utf-8")


# ---------- talking to the model ----------

def build_content(batch, previous_label):
    """User message: each frame's timestamp followed by its image, then the instruction."""
    content = []
    for path, t in batch:
        content.append({"type": "text", "text": f"Frame at t={t} s"})
        image_data = base64.standard_b64encode(Path(path).read_bytes()).decode("utf-8")
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data}})
    content.append({
        "type": "text",
        "text": f"The frame just before this batch was labeled: {previous_label}. "
                f"Label all {len(batch)} frames above.",
    })
    return content


def call_model(client, model, batch, previous_label):
    """One API call. Returns (response text or None, usage dict, stop reason)."""
    response = client.messages.create(
        model=model,
        max_tokens=8000,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": build_content(batch, previous_label)}],
        output_config={"effort": config.EFFORT, "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
    )
    text = next((block.text for block in response.content if block.type == "text"), None)
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cache_read_input_tokens": response.usage.cache_read_input_tokens or 0,
        "cache_creation_input_tokens": response.usage.cache_creation_input_tokens or 0,
    }
    return text, usage, response.stop_reason


def parse_labels(text, batch):
    """Turn the model's JSON into a list of (t, step, confidence). Raises ValueError if it is unusable."""
    if not text:
        raise ValueError("empty response")
    frames = json.loads(text)["frames"]
    if len(frames) != len(batch):
        raise ValueError(f"expected {len(batch)} frames, got {len(frames)}")

    labels = []
    for (_, t), item in zip(batch, frames):
        step = item["step"]
        if step not in STEPS:
            raise ValueError(f"unknown step {step!r}")
        confidence = min(max(float(item["confidence"]), 0.0), 1.0)
        labels.append((t, step, confidence))  # trust our own timestamps, not the echoed ones
    return labels


def log_problem(run_name, model, message):
    config.PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
    with log_lock, open(config.PREDICTIONS_DIR / "problems.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {model} {run_name}: {message}\n")


def classify_batch(client, model, batch, previous_label, run_name, stats):
    """Labels for one batch, from cache if possible. Retries once on bad output, then marks the batch unclear."""
    key = cache_key(batch, model, previous_label)
    cached = load_cached(key)
    if cached is not None:
        stats["cache_hits"] += 1
        return [tuple(row) for row in cached["labels"]]

    last_error = ""
    marked_unclear = False
    usage_total = {}
    for attempt in (1, 2):
        stats["api_calls"] += 1
        text, usage, stop_reason = call_model(client, model, batch, previous_label)
        for name, value in usage.items():
            usage_total[name] = usage_total.get(name, 0) + value
        try:
            if stop_reason not in ("end_turn", "stop_sequence"):
                raise ValueError(f"stop_reason={stop_reason}")
            labels = parse_labels(text, batch)
            break
        except (ValueError, KeyError, TypeError) as error:  # json.JSONDecodeError is a ValueError
            last_error = str(error)
            log_problem(run_name, model, f"batch at t={batch[0][1]} attempt {attempt} failed: {last_error}")
    else:
        labels = [(t, "unclear", 0.0) for _, t in batch]
        marked_unclear = True
        stats["unclear_batches"] += 1
        log_problem(run_name, model, f"batch at t={batch[0][1]} marked unclear after 2 attempts")

    # Unclear batches are cached too, so reruns stay identical. Delete the cache file to retry one.
    save_cached(key, {"model": model, "previous_label": previous_label, "labels": labels,
                      "usage": usage_total, "error": last_error if marked_unclear else ""})
    for name, value in usage_total.items():
        stats[name] = stats.get(name, 0) + value
    return labels


# ---------- whole recordings ----------

def new_stats():
    return {"api_calls": 0, "cache_hits": 0, "unclear_batches": 0}


def classify_run(client, model, frames_dir, stats):
    """Label every frame of one recording, batch by batch, and write the predictions CSV."""
    run_name = Path(frames_dir).name
    labels = []
    previous_label = "none (this is the start of the recording)"
    for batch in make_batches(read_frames(frames_dir)):
        batch_labels = classify_batch(client, model, batch, previous_label, run_name, stats)
        labels.extend(batch_labels)
        previous_label = batch_labels[-1][1]

    out_path = config.PREDICTIONS_DIR / model / f"{run_name}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["t", "step", "confidence"])
        writer.writerows((t, step, round(conf, 3)) for t, step, conf in labels)
    return out_path


def estimate_calls(model, frames_dirs):
    """How many API calls a run would make, following cached answers as far as they go."""
    calls = 0
    for frames_dir in frames_dirs:
        batches = make_batches(read_frames(frames_dir))
        previous_label = "none (this is the start of the recording)"
        for i, batch in enumerate(batches):
            cached = load_cached(cache_key(batch, model, previous_label))
            if cached is None:
                calls += len(batches) - i  # everything from here on is uncached
                break
            previous_label = cached["labels"][-1][1]
    return calls


def run_usage(model, frames_dir):
    """Total tokens the cached answers for one recording used. None if any batch is not cached."""
    totals = {}
    previous_label = "none (this is the start of the recording)"
    for batch in make_batches(read_frames(frames_dir)):
        cached = load_cached(cache_key(batch, model, previous_label))
        if cached is None:
            return None
        for name, value in cached.get("usage", {}).items():
            totals[name] = totals.get(name, 0) + value
        previous_label = cached["labels"][-1][1]
    return totals


def usage_cost(model, usage):
    """Dollar cost of a usage dict, from the prices in config.PRICES."""
    prices = config.PRICES[model]
    return sum(usage.get(name, 0) * prices[name] / 1_000_000 for name in prices)


def classify_runs(client, model, frames_dirs, workers=config.MAX_WORKERS):
    """Classify several recordings in parallel. Returns (output paths, stats)."""
    stats = new_stats()
    stats_lock = threading.Lock()

    def one_run(frames_dir):
        run_stats = new_stats()
        path = classify_run(client, model, frames_dir, run_stats)
        with stats_lock:
            for name, value in run_stats.items():
                stats[name] = stats.get(name, 0) + value
        return path

    with ThreadPoolExecutor(max_workers=workers) as pool:
        paths = list(pool.map(one_run, frames_dirs))
    return paths, stats


# ---------- side by side view ----------

def read_labels(label_path):
    """Hand labels as a list of (step, start_s, end_s)."""
    with open(label_path, encoding="utf-8") as f:
        return [(row["step"], float(row["start_s"]), float(row["end_s"])) for row in csv.DictReader(f)]


def label_at(hand_labels, t):
    for step, start, end in hand_labels:
        if start <= t < end:
            return step
    return ""


def print_side_by_side(prediction_path, label_path):
    with open(prediction_path, encoding="utf-8") as f:
        predictions = list(csv.DictReader(f))
    hand_labels = read_labels(label_path) if Path(label_path).exists() else []
    print(f"\n{'t':>7}  {'predicted':<15} {'conf':>5}  {'my label':<15}")
    for row in predictions:
        mine = label_at(hand_labels, float(row["t"])) if hand_labels else "(no label file)"
        mark = "" if not hand_labels or mine == row["step"] else "  <-- differs"
        print(f"{float(row['t']):>7.1f}  {row['step']:<15} {float(row['confidence']):>5.2f}  {mine:<15}{mark}")


def main():
    parser = argparse.ArgumentParser(description="Label frames with a Claude vision model.")
    parser.add_argument("run", nargs="?", help="recording name, e.g. run_01")
    parser.add_argument("--all", action="store_true", help="every recording in data/frames")
    parser.add_argument("--model", default=config.MODEL)
    parser.add_argument("--yes", action="store_true", help=f"allow more than {config.CONFIRM_ABOVE_CALLS} API calls")
    args = parser.parse_args()

    if args.all:
        frames_dirs = sorted(p for p in config.FRAMES_DIR.iterdir() if (p / "frames.csv").exists())
    elif args.run:
        frames_dirs = [config.FRAMES_DIR / args.run]
    else:
        parser.error("give a recording name or --all")

    estimated = estimate_calls(args.model, frames_dirs)
    print(f"{len(frames_dirs)} recording(s), model {args.model}: about {estimated} API calls needed "
          f"(retries can add a few)")
    if estimated > config.CONFIRM_ABOVE_CALLS and not args.yes:
        print(f"That is more than {config.CONFIRM_ABOVE_CALLS}. Rerun with --yes to go ahead.")
        return

    import anthropic  # imported here so tests and --help work without the package configured
    client = anthropic.Anthropic(max_retries=4)  # reads ANTHROPIC_API_KEY from the environment
    paths, stats = classify_runs(client, args.model, frames_dirs)

    print(f"\nAPI calls made: {stats['api_calls']}, cache hits: {stats['cache_hits']}, "
          f"batches marked unclear: {stats['unclear_batches']}")
    print(f"Tokens: input {stats.get('input_tokens', 0)}, output {stats.get('output_tokens', 0)}, "
          f"cache read {stats.get('cache_read_input_tokens', 0)}, cache write {stats.get('cache_creation_input_tokens', 0)}")
    for path in paths:
        print(f"Wrote {path}")

    if len(paths) == 1:
        print_side_by_side(paths[0], config.LABELS_DIR / f"{paths[0].stem}.csv")


if __name__ == "__main__":
    main()
