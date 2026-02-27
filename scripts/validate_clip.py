#!/usr/bin/env python3
"""
Validate a clip before processing.

Checks:
  1. File is a valid video (ffprobe can read it)
  2. Episode number >= MIN_EPISODE_NUMBER (343)
  3. Filename follows naming convention: EP{number}_{description}.mp4

Usage:
  python validate_clip.py clip_file.mp4
  python validate_clip.py EP345_on_free_speech.mp4 --min-episode 343

Exit codes:
  0 = valid
  1 = invalid (reason printed to stderr)
"""

import argparse
import json
import os
import re
import subprocess
import sys


MIN_EPISODE = int(os.environ.get("MIN_EPISODE_NUMBER", "343"))

# Accept filenames like: EP343_some_description.mp4, ep350-clip-title.mp4, etc.
EPISODE_PATTERN = re.compile(r"[Ee][Pp]\.?(\d+)", re.IGNORECASE)


def extract_episode_number(filename):
    """
    Try to extract an episode number from the filename.
    Returns the episode int, or None if not found.
    """
    basename = os.path.basename(filename)
    match = EPISODE_PATTERN.search(basename)
    if match:
        return int(match.group(1))
    return None


def is_valid_video(filepath):
    """Check if ffprobe can read at least one video stream."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "v:0",
        filepath,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return False, "ffprobe could not read the file"

    try:
        info = json.loads(result.stdout)
        streams = info.get("streams", [])
        if not streams:
            return False, "no video stream found"
    except json.JSONDecodeError:
        return False, "ffprobe output was not valid JSON"

    return True, ""


def validate_clip(filepath, min_episode=MIN_EPISODE):
    """
    Run all validation checks.
    Returns (is_valid: bool, errors: list[str]).
    """
    errors = []

    if not os.path.isfile(filepath):
        return False, [f"file not found: {filepath}"]

    valid_video, video_err = is_valid_video(filepath)
    if not valid_video:
        errors.append(f"invalid video: {video_err}")

    episode_num = extract_episode_number(filepath)
    if episode_num is None:
        errors.append(
            f"could not detect episode number in filename '{os.path.basename(filepath)}'. "
            f"Expected format: EP<number>_<description>.mp4 (e.g. EP345_on_free_speech.mp4)"
        )
    elif episode_num < min_episode:
        errors.append(
            f"episode {episode_num} is below minimum allowed ({min_episode}). "
            f"Only episodes {min_episode}+ are permitted."
        )

    return len(errors) == 0, errors


def main():
    parser = argparse.ArgumentParser(description="Validate a Julian Dorey clip")
    parser.add_argument("clip", help="Path to clip video file")
    parser.add_argument(
        "--min-episode",
        type=int,
        default=MIN_EPISODE,
        help=f"Minimum episode number (default: {MIN_EPISODE})",
    )
    parser.add_argument("--json", action="store_true", help="Output result as JSON")
    args = parser.parse_args()

    is_valid, errors = validate_clip(args.clip, args.min_episode)

    if args.json:
        result = {
            "file": args.clip,
            "valid": is_valid,
            "episode": extract_episode_number(args.clip),
            "errors": errors,
        }
        print(json.dumps(result))
    else:
        if is_valid:
            ep = extract_episode_number(args.clip)
            print(f"VALID: {os.path.basename(args.clip)} (Episode {ep})")
        else:
            print(f"INVALID: {os.path.basename(args.clip)}", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)

    sys.exit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
