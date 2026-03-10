#!/usr/bin/env python3
"""
Generate platform-specific captions and metadata for Julian Dorey clips.

Reads clip filenames (EP###_description.mp4) and produces captions
formatted for Instagram Reels, TikTok, and YouTube Shorts.

Usage:
  python generate_captions.py EP345_on_free_speech_watermarked.mp4
  python generate_captions.py /path/to/clips/ --all --output captions.json
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


EPISODE_PATTERN = re.compile(r"[Ee][Pp]\.?(\d+)")

YOUTUBE_URL = "https://www.youtube.com/@JulianDorey/"

INSTAGRAM_HASHTAGS = [
    "#JulianDorey", "#JulianDoreyPodcast", "#Podcast", "#Clips",
    "#Reels", "#PodcastClips",
]

TIKTOK_HASHTAGS = [
    "#JulianDorey", "#JulianDoreyPodcast", "#Podcast", "#Clips",
    "#FYP", "#ForYou", "#PodcastClips", "#Viral",
]

YOUTUBE_TAGS = [
    "Julian Dorey", "Julian Dorey Podcast", "Podcast Clips", "Shorts",
]


def clean_title(filename):
    """Extract a readable title from the filename."""
    stem = Path(filename).stem
    stem = re.sub(r"_watermarked$", "", stem)
    stem = re.sub(r"^[Ee][Pp]\.?\d+[_\-]?", "", stem)
    title = stem.replace("_", " ").replace("-", " ").strip()
    return title.title() if title else "Julian Dorey Podcast Clip"


def get_episode(filename):
    match = EPISODE_PATTERN.search(filename)
    return int(match.group(1)) if match else None


def generate_instagram_caption(filename):
    title = clean_title(filename)
    episode = get_episode(filename)
    ep_line = f"EP {episode}" if episode else ""

    lines = [
        title,
        "",
        ep_line,
        f"Full episodes: {YOUTUBE_URL}",
        "",
        " ".join(INSTAGRAM_HASHTAGS),
    ]
    return "\n".join(line for line in lines if line is not None).strip()


def generate_tiktok_caption(filename):
    title = clean_title(filename)
    hashtag_str = " ".join(TIKTOK_HASHTAGS)
    return f"{title} {hashtag_str}"


def generate_youtube_metadata(filename):
    title = clean_title(filename)
    episode = get_episode(filename)

    yt_title = f"{title} | Julian Dorey Podcast"
    if episode:
        yt_title = f"{title} | Julian Dorey Podcast EP {episode}"

    if len(yt_title) > 100:
        yt_title = yt_title[:97] + "..."

    description_lines = [
        title,
        "",
        f"From Julian Dorey Podcast{f' Episode {episode}' if episode else ''}",
        "",
        f"Subscribe to Julian Dorey: {YOUTUBE_URL}",
        "",
        "---",
        " ".join(f"#{tag}" for tag in YOUTUBE_TAGS),
    ]

    return {
        "title": yt_title,
        "description": "\n".join(description_lines),
        "tags": YOUTUBE_TAGS,
        "category_id": "22",
    }


def generate_all(filename):
    return {
        "file": filename,
        "episode": get_episode(filename),
        "title": clean_title(filename),
        "instagram": {"caption": generate_instagram_caption(filename)},
        "tiktok": {"caption": generate_tiktok_caption(filename)},
        "youtube": generate_youtube_metadata(filename),
    }


def main():
    parser = argparse.ArgumentParser(description="Generate captions for Julian Dorey clips")
    parser.add_argument("input", help="Clip filename or directory of clips")
    parser.add_argument("--all", action="store_true", help="Process all clips in directory")
    parser.add_argument("--output", help="Save JSON output to file")
    parser.add_argument("--platform", choices=["instagram", "tiktok", "youtube"],
                        help="Show caption for one platform only")
    args = parser.parse_args()

    input_path = Path(args.input)

    if args.all and input_path.is_dir():
        video_exts = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
        files = sorted(f.name for f in input_path.iterdir()
                       if f.is_file() and f.suffix.lower() in video_exts)
    elif input_path.is_file() or not input_path.exists():
        files = [input_path.name if input_path.exists() else args.input]
    else:
        print(f"Not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    results = []
    for filename in files:
        data = generate_all(filename)
        results.append(data)

        if not args.output:
            print(f"=== {filename} ===")
            if args.platform:
                if args.platform == "youtube":
                    yt = data["youtube"]
                    print(f"Title: {yt['title']}")
                    print(f"Description:\n{yt['description']}")
                    print(f"Tags: {', '.join(yt['tags'])}")
                else:
                    print(data[args.platform]["caption"])
            else:
                print(f"\n--- Instagram ---\n{data['instagram']['caption']}")
                print(f"\n--- TikTok ---\n{data['tiktok']['caption']}")
                yt = data["youtube"]
                print(f"\n--- YouTube ---\nTitle: {yt['title']}")
                print(f"Description:\n{yt['description']}")
            print()

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Saved {len(results)} entries to {args.output}")


if __name__ == "__main__":
    main()
