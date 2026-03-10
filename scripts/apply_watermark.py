#!/usr/bin/env python3
"""
Apply Julian Dorey's YouTube watermark to a video clip.

Watermark specs:
  - 25% of video width
  - 80% opacity
  - Positioned horizontally centered, below the subtitle region (bottom ~12% of frame)

Usage:
  python apply_watermark.py input.mp4 output.mp4 [--watermark path/to/watermark.png]
"""

import argparse
import os
import subprocess
import sys
import json


def get_video_dimensions(video_path):
    """Return (width, height) of the video using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "v:0",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ffprobe failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    info = json.loads(result.stdout)
    stream = info["streams"][0]
    return int(stream["width"]), int(stream["height"])


def apply_watermark(input_path, output_path, watermark_path, scale=0.25, opacity=0.8):
    """
    Overlay watermark on video.

    The watermark is scaled to `scale` fraction of the video width,
    given `opacity` (0.0 = invisible, 1.0 = fully opaque),
    and placed at bottom-center, slightly above the very bottom edge
    so it sits below typical subtitle placement.
    """
    if not os.path.isfile(input_path):
        print(f"Input video not found: {input_path}", file=sys.stderr)
        return False

    if not os.path.isfile(watermark_path):
        print(f"Watermark image not found: {watermark_path}", file=sys.stderr)
        return False

    vid_w, vid_h = get_video_dimensions(input_path)
    watermark_w = int(vid_w * scale)

    # Position: horizontally centered, 88% down from top (below subtitle region).
    # For 9:16 vertical video (1080x1920), this puts watermark around y=1690.
    # The "88% of height" accounts for subtitles typically living at 70-85% height.
    x_expr = f"(main_w-overlay_w)/2"
    y_expr = f"main_h*0.88-overlay_h/2"

    # Filter chain:
    #   1. Scale watermark to target width, preserve aspect ratio
    #   2. Convert to RGBA so opacity channel works
    #   3. Apply opacity via colorchannelmixer (aa = alpha multiplier)
    #   4. Overlay on video at computed position
    filter_complex = (
        f"[1:v]scale={watermark_w}:-1,format=rgba,"
        f"colorchannelmixer=aa={opacity}[wm];"
        f"[0:v][wm]overlay=x={x_expr}:y={y_expr}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-i", watermark_path,
        "-filter_complex", filter_complex,
        "-codec:a", "copy",
        "-preset", "fast",
        "-crf", "18",
        output_path,
    ]

    print(f"Processing: {os.path.basename(input_path)}")
    print(f"  Video: {vid_w}x{vid_h}")
    print(f"  Watermark width: {watermark_w}px ({scale*100:.0f}% of video)")
    print(f"  Opacity: {opacity*100:.0f}%")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FFmpeg failed:\n{result.stderr}", file=sys.stderr)
        return False

    print(f"  Output: {output_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Apply Julian Dorey watermark to a clip")
    parser.add_argument("input", help="Path to input video file")
    parser.add_argument("output", help="Path to output video file")
    parser.add_argument(
        "--watermark",
        default=os.environ.get("WATERMARK_PATH", "config/watermark/julian_dorey_watermark.png"),
        help="Path to watermark PNG image",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=float(os.environ.get("WATERMARK_SCALE", "0.25")),
        help="Watermark size as fraction of video width (default: 0.25)",
    )
    parser.add_argument(
        "--opacity",
        type=float,
        default=float(os.environ.get("WATERMARK_OPACITY", "0.8")),
        help="Watermark opacity 0.0-1.0 (default: 0.8)",
    )
    args = parser.parse_args()

    ok = apply_watermark(args.input, args.output, args.watermark, args.scale, args.opacity)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
