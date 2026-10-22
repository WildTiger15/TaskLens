"""Shared settings for the TaskLens pipeline. Change values here, not in the scripts."""

from pathlib import Path

# Vision model. MODEL is the default; CHEAP_MODEL is the cheaper one we compare against.
MODEL = "claude-sonnet-5-5"
CHEAP_MODEL = "claude-haiku-5-5"

# US dollars per million tokens, used for cost per run. Base input and output prices
# and the Sonnet cache read price are published list prices as of Oct 2026. The other
# cache prices use the standard multipliers (read 0.1x input, write 1.25x input).
# Check the current pricing page before quoting any cost.
PRICES = {
    "claude-sonnet-5-5": {"input_tokens": 2.00, "output_tokens": 10.00,
                          "cache_read_input_tokens": 0.20, "cache_creation_input_tokens": 2.50},
    "claude-haiku-5-5": {"input_tokens": 0.10, "output_tokens": 0.50,
                         "cache_read_input_tokens": 0.01, "cache_creation_input_tokens": 0.125},
}

# Frame sampling
FRAME_INTERVAL_S = 2      # take one frame every N seconds
FRAME_WIDTH = 1024        # downscale frames to about this many pixels wide

# Classification
# Note: these models reject a custom temperature, so we cannot set temperature 0.
# Reruns are still identical because every response is cached on disk.
EFFORT = "low"            # model thinking effort; low suits simple labeling
BATCH_SIZE = 8            # frames per API call
MAX_WORKERS = 4           # recordings classified in parallel
CONFIRM_ABOVE_CALLS = 100 # ask before any run that needs more calls than this

# Segmentation and review
SMOOTH_WINDOW = 3         # frames in the majority window that removes single frame flips
MIN_SEGMENT_S = 2         # merge segments shorter than this into a neighbor
LOW_CONFIDENCE = 0.6      # frames below this go to the human review list

# Folders
ROOT = Path(__file__).resolve().parent
RECORDINGS_DIR = ROOT / "data" / "recordings"
LABELS_DIR = ROOT / "data" / "labels"
FRAMES_DIR = ROOT / "data" / "frames"
PREDICTIONS_DIR = ROOT / "data" / "predictions"
CACHE_DIR = ROOT / "data" / "cache"
OUTPUTS_DIR = ROOT / "outputs"
STEPS_FILE = ROOT / "steps.json"
