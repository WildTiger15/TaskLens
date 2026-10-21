"""Sample frames from a screen recording.

Takes one frame every N seconds, downscales it, saves it as a JPEG and writes
frames.csv (file, t) next to the frames.

Usage:
  python src/frames.py data/recordings/run_01.mp4
  python src/frames.py --all            # every video in data/recordings
  python src/frames.py run_01.mp4 --interval 1
"""

import argparse
import csv
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}


def resize_to_width(frame, width):
    """Downscale a frame to the given width, keeping the aspect ratio. Never upscales."""
    height, current_width = frame.shape[:2]
    if current_width <= width:
        return frame
    new_height = round(height * width / current_width)
    return cv2.resize(frame, (width, new_height), interpolation=cv2.INTER_AREA)


def frame_time(video, index, fps):
    """Timestamp of the frame just read, in seconds.

    Uses the timestamp stored in the video when available (screen recorders often
    use a variable frame rate), otherwise falls back to index / fps.
    """
    ms = video.get(cv2.CAP_PROP_POS_MSEC)
    if ms > 0 or index == 0:
        return ms / 1000
    return index / fps


def sample_frames(video_path, out_dir, interval_s=config.FRAME_INTERVAL_S, width=config.FRAME_WIDTH):
    """Save one frame every interval_s seconds. Returns a list of (file name, seconds)."""
    video = cv2.VideoCapture(str(video_path))
    if not video.isOpened():
        raise FileNotFoundError(f"Could not open video: {video_path}")
    fps = video.get(cv2.CAP_PROP_FPS) or 30

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("frame_*.jpg"):  # clear frames from an earlier run
        old.unlink()

    rows = []
    next_time = 0.0
    index = 0
    while True:
        ok, frame = video.read()
        if not ok:
            break
        t = frame_time(video, index, fps)
        index += 1
        if t + 1e-6 < next_time:
            continue

        file_name = f"frame_{len(rows):04d}.jpg"
        cv2.imwrite(str(out_dir / file_name), resize_to_width(frame, width), [cv2.IMWRITE_JPEG_QUALITY, 85])
        rows.append((file_name, round(t, 3)))
        next_time += interval_s
    video.release()

    with open(out_dir / "frames.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["file", "t"])
        writer.writerows(rows)
    return rows


def frames_dir_for(video_path):
    """data/recordings/run_01.mp4 -> data/frames/run_01"""
    return config.FRAMES_DIR / Path(video_path).stem


def main():
    parser = argparse.ArgumentParser(description="Sample frames from screen recordings.")
    parser.add_argument("video", nargs="?", help="path to one video")
    parser.add_argument("--all", action="store_true", help="process every video in data/recordings")
    parser.add_argument("--interval", type=float, default=config.FRAME_INTERVAL_S, help="seconds between frames")
    args = parser.parse_args()

    if args.all:
        videos = sorted(p for p in config.RECORDINGS_DIR.iterdir() if p.suffix.lower() in VIDEO_EXTENSIONS)
    elif args.video:
        videos = [Path(args.video)]
    else:
        parser.error("give a video path or --all")

    for video_path in videos:
        rows = sample_frames(video_path, frames_dir_for(video_path), args.interval)
        last_t = rows[-1][1] if rows else 0
        print(f"{video_path.name}: {len(rows)} frames, 0.0s to {last_t}s -> {frames_dir_for(video_path)}")


if __name__ == "__main__":
    main()
