#!/usr/bin/env python3
"""
End-to-end test of the full clip automation pipeline.

Creates a synthetic test video, then runs every stage:
  1. Generate a fake 9:16 vertical video (simulating a podcast clip)
  2. Validate it (episode number check)
  3. Apply watermark
  4. Generate platform captions
  5. Verify output

No real clips, API keys, or social media accounts needed.

Usage:
  python3 scripts/test_pipeline.py
"""

import json
import os
import subprocess
import sys
import shutil
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"

passed = 0
failed = 0


def step(msg):
    print(f"\n{BOLD}>>> {msg}{RESET}")


def ok(msg):
    global passed
    passed += 1
    print(f"  {GREEN}PASS{RESET}: {msg}")


def fail(msg):
    global failed
    failed += 1
    print(f"  {RED}FAIL{RESET}: {msg}")


def warn(msg):
    print(f"  {YELLOW}WARN{RESET}: {msg}")


def run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def main():
    print(f"{BOLD}=== Julian Dorey Clip Pipeline — End-to-End Test ==={RESET}\n")

    test_dir = Path(tempfile.mkdtemp(prefix="jd_test_"))
    print(f"Test directory: {test_dir}\n")

    # ---------------------------------------------------------------
    # Stage 0: Check dependencies
    # ---------------------------------------------------------------
    step("Stage 0: Check dependencies")

    for cmd in ["ffmpeg", "ffprobe", "python3"]:
        r = run(["which", cmd])
        if r.returncode == 0:
            ok(f"{cmd} found at {r.stdout.strip()}")
        else:
            fail(f"{cmd} not found")
            print("Cannot continue without dependencies.")
            sys.exit(1)

    # ---------------------------------------------------------------
    # Stage 1: Generate synthetic test video (9:16 vertical, 10 seconds)
    # ---------------------------------------------------------------
    step("Stage 1: Generate synthetic test clips")

    valid_clip = test_dir / "EP350_test_topic_ai_future.mp4"
    invalid_old_ep = test_dir / "EP100_old_episode.mp4"
    no_episode = test_dir / "random_clip.mp4"

    ffmpeg_base = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", "color=c=0x1a1a2e:s=1080x1920:d=5:r=30",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "5", "-c:v", "libx264", "-preset", "ultrafast",
        "-crf", "28", "-c:a", "aac", "-shortest",
    ]

    for clip_path, label in [
        (valid_clip, "valid EP350 clip"),
        (invalid_old_ep, "invalid EP100 clip"),
        (no_episode, "no-episode clip"),
    ]:
        r = run(ffmpeg_base + [str(clip_path)])
        if r.returncode == 0 and clip_path.exists():
            size_kb = clip_path.stat().st_size / 1024
            ok(f"Generated {label}: {clip_path.name} ({size_kb:.0f} KB)")
        else:
            fail(f"Failed to generate {label}: {r.stderr[-200:]}")
            sys.exit(1)

    # ---------------------------------------------------------------
    # Stage 2: Validate clips
    # ---------------------------------------------------------------
    step("Stage 2: Validate clips")

    # Valid clip should pass
    r = run([sys.executable, str(SCRIPT_DIR / "validate_clip.py"), "--json", str(valid_clip)])
    if r.returncode == 0:
        data = json.loads(r.stdout)
        if data["valid"] and data["episode"] == 350:
            ok(f"EP350 clip validated (episode={data['episode']})")
        else:
            fail(f"EP350 should be valid: {data}")
    else:
        fail(f"validate_clip.py crashed: {r.stderr}")

    # Old episode should fail
    r = run([sys.executable, str(SCRIPT_DIR / "validate_clip.py"), "--json", str(invalid_old_ep)])
    data = json.loads(r.stdout) if r.stdout else {}
    if not data.get("valid", True):
        ok(f"EP100 correctly rejected: {data.get('errors', [''])[0][:60]}")
    else:
        fail("EP100 should have been rejected (below episode 343)")

    # No episode number should fail
    r = run([sys.executable, str(SCRIPT_DIR / "validate_clip.py"), "--json", str(no_episode)])
    data = json.loads(r.stdout) if r.stdout else {}
    if not data.get("valid", True):
        ok(f"No-episode clip correctly rejected")
    else:
        fail("Clip without episode number should have been rejected")

    # ---------------------------------------------------------------
    # Stage 3: Apply watermark
    # ---------------------------------------------------------------
    step("Stage 3: Apply watermark")

    watermark_path = PROJECT_ROOT / "config" / "watermark" / "julian_dorey_watermark.png"

    if not watermark_path.exists():
        warn(f"Watermark not found at {watermark_path}")
        warn("Generating a placeholder watermark for testing...")
        watermark_path.parent.mkdir(parents=True, exist_ok=True)
        r = run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "color=c=white:s=400x80:d=1",
            "-vf", "drawtext=text='JULIAN DOREY':fontsize=48:fontcolor=red:x=(w-tw)/2:y=(h-th)/2",
            "-frames:v", "1",
            str(watermark_path),
        ])
        if r.returncode == 0:
            ok("Generated placeholder watermark for testing")
        else:
            fail(f"Could not generate placeholder watermark: {r.stderr[-200:]}")

    watermarked_clip = test_dir / "EP350_test_topic_ai_future_watermarked.mp4"

    r = run([
        sys.executable, str(SCRIPT_DIR / "apply_watermark.py"),
        str(valid_clip), str(watermarked_clip),
        "--watermark", str(watermark_path),
        "--scale", "0.25",
        "--opacity", "0.8",
    ])

    if r.returncode == 0 and watermarked_clip.exists():
        size_kb = watermarked_clip.stat().st_size / 1024
        ok(f"Watermarked clip created: {watermarked_clip.name} ({size_kb:.0f} KB)")

        # Verify dimensions are preserved
        probe = run([
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", "-select_streams", "v:0",
            str(watermarked_clip),
        ])
        if probe.returncode == 0:
            stream = json.loads(probe.stdout)["streams"][0]
            w, h = int(stream["width"]), int(stream["height"])
            if w == 1080 and h == 1920:
                ok(f"Output dimensions correct: {w}x{h}")
            else:
                fail(f"Dimensions changed: expected 1080x1920, got {w}x{h}")
    else:
        fail(f"Watermark failed: {r.stderr[-300:]}")

    # ---------------------------------------------------------------
    # Stage 4: Batch processing
    # ---------------------------------------------------------------
    step("Stage 4: Batch processing")

    batch_input = test_dir / "batch_in"
    batch_output = test_dir / "batch_out"
    batch_input.mkdir()
    batch_output.mkdir()

    shutil.copy(valid_clip, batch_input / valid_clip.name)

    r = run([
        sys.executable, str(SCRIPT_DIR / "batch_process.py"),
        str(batch_input), str(batch_output),
        "--watermark", str(watermark_path),
    ])

    batch_results = list(batch_output.glob("*_watermarked.*"))
    if len(batch_results) == 1:
        ok(f"Batch processing produced 1 clip: {batch_results[0].name}")
    else:
        fail(f"Expected 1 batch output, got {len(batch_results)}")

    # Dry run should produce 0 files in a new dir
    dry_output = test_dir / "dry_out"
    dry_output.mkdir()
    r = run([
        sys.executable, str(SCRIPT_DIR / "batch_process.py"),
        str(batch_input), str(dry_output),
        "--watermark", str(watermark_path),
        "--dry-run",
    ])
    dry_results = list(dry_output.glob("*"))
    if len(dry_results) == 0:
        ok("Dry run produced no output files (correct)")
    else:
        fail(f"Dry run should produce no files, got {len(dry_results)}")

    # ---------------------------------------------------------------
    # Stage 5: Caption generation
    # ---------------------------------------------------------------
    step("Stage 5: Caption generation")

    r = run([
        sys.executable, str(SCRIPT_DIR / "generate_captions.py"),
        "EP350_on_ai_future_watermarked.mp4",
    ])

    if r.returncode == 0 and "Instagram" in r.stdout and "TikTok" in r.stdout:
        ok("Captions generated for all platforms")

        if "@JulianDorey" in r.stdout:
            ok("YouTube channel link present in YouTube description")
        if "#FYP" in r.stdout:
            ok("TikTok hashtags present")
        if "#JulianDorey" in r.stdout:
            ok("Brand hashtags present")
    else:
        fail(f"Caption generation failed: {r.stderr}")

    # JSON output
    captions_json = test_dir / "captions.json"
    r = run([
        sys.executable, str(SCRIPT_DIR / "generate_captions.py"),
        "EP350_on_ai_future_watermarked.mp4",
        "--output", str(captions_json),
    ])
    if captions_json.exists():
        data = json.loads(captions_json.read_text())
        if len(data) == 1 and data[0]["episode"] == 350:
            ok(f"JSON caption export works (episode={data[0]['episode']})")
        else:
            fail(f"Unexpected JSON output: {data}")
    else:
        fail("JSON caption export failed")

    # ---------------------------------------------------------------
    # Stage 6: Full pipeline simulation
    # ---------------------------------------------------------------
    step("Stage 6: Full pipeline (validate -> watermark -> captions)")

    pipe_input = test_dir / "pipe_in"
    pipe_output = test_dir / "pipe_out"
    pipe_input.mkdir()
    pipe_output.mkdir()

    # Create a fresh clip
    fresh_clip = pipe_input / "EP360_breaking_news_interview.mp4"
    r = run(ffmpeg_base + [str(fresh_clip)])

    # Validate
    r = run([sys.executable, str(SCRIPT_DIR / "validate_clip.py"), "--json", str(fresh_clip)])
    v = json.loads(r.stdout)
    if v["valid"]:
        ok("Pipeline: validation passed")
    else:
        fail(f"Pipeline: validation failed: {v['errors']}")

    # Watermark
    out_clip = pipe_output / "EP360_breaking_news_interview_watermarked.mp4"
    r = run([
        sys.executable, str(SCRIPT_DIR / "apply_watermark.py"),
        str(fresh_clip), str(out_clip),
        "--watermark", str(watermark_path),
    ])
    if out_clip.exists():
        ok("Pipeline: watermark applied")
    else:
        fail("Pipeline: watermark failed")

    # Captions
    r = run([
        sys.executable, str(SCRIPT_DIR / "generate_captions.py"),
        out_clip.name, "--platform", "tiktok",
    ])
    if "Breaking News Interview" in r.stdout:
        ok("Pipeline: TikTok caption generated from filename")
    else:
        fail(f"Pipeline: caption missing title. Got: {r.stdout[:100]}")

    r = run([
        sys.executable, str(SCRIPT_DIR / "generate_captions.py"),
        out_clip.name, "--platform", "youtube",
    ])
    if "EP 360" in r.stdout:
        ok("Pipeline: YouTube metadata includes episode number")
    else:
        fail(f"Pipeline: YouTube missing episode. Got: {r.stdout[:100]}")

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print(f"\n{BOLD}{'='*50}{RESET}")
    total = passed + failed
    if failed == 0:
        print(f"{GREEN}{BOLD}ALL {total} TESTS PASSED{RESET}")
    else:
        print(f"{RED}{BOLD}{failed} FAILED{RESET}, {GREEN}{passed} passed{RESET} (out of {total})")

    # Cleanup
    shutil.rmtree(test_dir)
    print(f"\nCleaned up test directory: {test_dir}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
