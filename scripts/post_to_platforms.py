#!/usr/bin/env python3
"""
Post a watermarked clip to Instagram Reels, TikTok, and YouTube Shorts.

Supports two modes:
  --dry-run    Log what would be posted without calling any API (default)
  --live       Actually call platform APIs (requires credentials in .env)

Usage:
  python3 scripts/post_to_platforms.py data/clips-processed/EP350_clip_watermarked.mp4
  python3 scripts/post_to_platforms.py clip.mp4 --live --platforms instagram tiktok youtube
"""

import argparse
import json
import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime

try:
    import requests
except ImportError:
    print("Missing dependency: pip install requests", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("poster")

POST_LOG_PATH = Path(os.environ.get("POST_LOG", "data/post_log.jsonl"))


def load_env():
    """Load .env file if it exists (simple key=value parser)."""
    env_path = SCRIPT_DIR.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def log_post(entry):
    """Append a JSON line to the post log."""
    POST_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(POST_LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def generate_captions(filename):
    """Import caption generation inline to avoid circular deps."""
    sys.path.insert(0, str(SCRIPT_DIR))
    from generate_captions import generate_all
    return generate_all(filename)


# ---------------------------------------------------------------------------
# Instagram Reels (Meta Graph API)
# ---------------------------------------------------------------------------

def post_instagram(video_path, caption, dry_run=True):
    account_id = os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
    access_token = os.environ.get("META_ACCESS_TOKEN", "")

    if dry_run:
        log.info("[DRY RUN] Instagram Reels: would post %s", video_path.name)
        log.info("[DRY RUN]   Caption: %s", caption[:80] + "...")
        return {"platform": "instagram", "status": "dry_run", "file": video_path.name}

    if not account_id or not access_token:
        log.error("Instagram: missing INSTAGRAM_BUSINESS_ACCOUNT_ID or META_ACCESS_TOKEN")
        return {"platform": "instagram", "status": "error", "error": "missing credentials"}

    # Step 1: Create media container
    log.info("Instagram: creating media container...")
    resp = requests.post(
        f"https://graph.facebook.com/v19.0/{account_id}/media",
        data={
            "media_type": "REELS",
            "video_url": str(video_path),  # must be a public URL in production
            "caption": caption,
            "access_token": access_token,
        },
    )

    if resp.status_code != 200:
        log.error("Instagram container creation failed: %s", resp.text)
        return {"platform": "instagram", "status": "error", "error": resp.text}

    container_id = resp.json().get("id")
    log.info("Instagram: container created (%s), waiting for processing...", container_id)

    # Step 2: Poll until ready
    for attempt in range(30):
        time.sleep(10)
        status_resp = requests.get(
            f"https://graph.facebook.com/v19.0/{container_id}",
            params={"fields": "status_code", "access_token": access_token},
        )
        status = status_resp.json().get("status_code")
        if status == "FINISHED":
            break
        if status == "ERROR":
            log.error("Instagram: processing failed")
            return {"platform": "instagram", "status": "error", "error": "processing_failed"}
        log.info("Instagram: processing... (attempt %d, status=%s)", attempt + 1, status)

    # Step 3: Publish
    log.info("Instagram: publishing...")
    pub_resp = requests.post(
        f"https://graph.facebook.com/v19.0/{account_id}/media_publish",
        data={"creation_id": container_id, "access_token": access_token},
    )

    if pub_resp.status_code == 200:
        media_id = pub_resp.json().get("id")
        log.info("Instagram: published (media_id=%s)", media_id)
        return {"platform": "instagram", "status": "posted", "media_id": media_id}
    else:
        log.error("Instagram publish failed: %s", pub_resp.text)
        return {"platform": "instagram", "status": "error", "error": pub_resp.text}


# ---------------------------------------------------------------------------
# TikTok (Content Posting API v2)
# ---------------------------------------------------------------------------

def post_tiktok(video_path, caption, dry_run=True):
    access_token = os.environ.get("TIKTOK_ACCESS_TOKEN", "")

    if dry_run:
        log.info("[DRY RUN] TikTok: would post %s", video_path.name)
        log.info("[DRY RUN]   Caption: %s", caption[:80] + "...")
        return {"platform": "tiktok", "status": "dry_run", "file": video_path.name}

    if not access_token:
        log.error("TikTok: missing TIKTOK_ACCESS_TOKEN")
        return {"platform": "tiktok", "status": "error", "error": "missing credentials"}

    file_size = video_path.stat().st_size

    # Step 1: Init upload
    log.info("TikTok: initializing upload...")
    init_resp = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/video/init/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json={
            "post_info": {
                "title": caption[:150],
                "privacy_level": "PUBLIC_TO_EVERYONE",
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": file_size,
                "total_chunk_count": 1,
            },
        },
    )

    if init_resp.status_code != 200:
        log.error("TikTok init failed: %s", init_resp.text)
        return {"platform": "tiktok", "status": "error", "error": init_resp.text}

    upload_url = init_resp.json().get("data", {}).get("upload_url", "")
    publish_id = init_resp.json().get("data", {}).get("publish_id", "")

    # Step 2: Upload video bytes
    log.info("TikTok: uploading video (%d bytes)...", file_size)
    with open(video_path, "rb") as f:
        upload_resp = requests.put(
            upload_url,
            headers={
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
            },
            data=f,
        )

    if upload_resp.status_code in (200, 201):
        log.info("TikTok: uploaded (publish_id=%s)", publish_id)
        return {"platform": "tiktok", "status": "posted", "publish_id": publish_id}
    else:
        log.error("TikTok upload failed: %s", upload_resp.text)
        return {"platform": "tiktok", "status": "error", "error": upload_resp.text}


# ---------------------------------------------------------------------------
# YouTube Shorts (Data API v3 resumable upload)
# ---------------------------------------------------------------------------

def get_youtube_access_token():
    """Exchange refresh token for a fresh access token."""
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN", "")

    if not all([client_id, client_secret, refresh_token]):
        return None

    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )

    if resp.status_code == 200:
        return resp.json().get("access_token")
    return None


def post_youtube(video_path, title, description, tags, dry_run=True):
    if dry_run:
        log.info("[DRY RUN] YouTube Shorts: would post %s", video_path.name)
        log.info("[DRY RUN]   Title: %s", title)
        return {"platform": "youtube", "status": "dry_run", "file": video_path.name}

    access_token = get_youtube_access_token()
    if not access_token:
        log.error("YouTube: could not obtain access token (check GOOGLE_* env vars)")
        return {"platform": "youtube", "status": "error", "error": "missing credentials"}

    # Step 1: Init resumable upload
    log.info("YouTube: initializing upload...")
    metadata = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags,
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    init_resp = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos",
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(video_path.stat().st_size),
        },
        json=metadata,
    )

    if init_resp.status_code != 200:
        log.error("YouTube init failed: %s", init_resp.text)
        return {"platform": "youtube", "status": "error", "error": init_resp.text}

    upload_url = init_resp.headers.get("Location", "")

    # Step 2: Upload video
    log.info("YouTube: uploading video...")
    with open(video_path, "rb") as f:
        upload_resp = requests.put(
            upload_url,
            headers={"Content-Type": "video/mp4"},
            data=f,
        )

    if upload_resp.status_code == 200:
        video_id = upload_resp.json().get("id", "")
        log.info("YouTube: published (video_id=%s)", video_id)
        return {"platform": "youtube", "status": "posted", "video_id": video_id}
    else:
        log.error("YouTube upload failed: %s", upload_resp.text)
        return {"platform": "youtube", "status": "error", "error": upload_resp.text}


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

PLATFORM_MAP = {
    "instagram": post_instagram,
    "tiktok": post_tiktok,
    "youtube": None,  # handled separately due to different args
}


def post_clip(video_path, platforms, dry_run=True):
    """Post a clip to all specified platforms. Returns list of results."""
    video_path = Path(video_path)
    if not video_path.exists():
        log.error("Video not found: %s", video_path)
        return []

    captions = generate_captions(video_path.name)
    results = []

    for platform in platforms:
        log.info("--- Posting to %s ---", platform)

        if platform == "instagram":
            result = post_instagram(video_path, captions["instagram"]["caption"], dry_run)
        elif platform == "tiktok":
            result = post_tiktok(video_path, captions["tiktok"]["caption"], dry_run)
        elif platform == "youtube":
            yt = captions["youtube"]
            result = post_youtube(
                video_path, yt["title"], yt["description"], yt["tags"], dry_run
            )
        else:
            log.warning("Unknown platform: %s", platform)
            continue

        result["timestamp"] = datetime.now().isoformat()
        result["file"] = video_path.name
        results.append(result)
        log_post(result)

    return results


def main():
    parser = argparse.ArgumentParser(description="Post clip to social platforms")
    parser.add_argument("video", help="Path to watermarked video file")
    parser.add_argument(
        "--platforms",
        nargs="+",
        default=["instagram", "tiktok", "youtube"],
        choices=["instagram", "tiktok", "youtube"],
    )
    parser.add_argument("--live", action="store_true", help="Actually call APIs (default is dry-run)")
    args = parser.parse_args()

    load_env()

    dry_run = not args.live
    if dry_run:
        log.info("=== DRY RUN MODE (use --live to actually post) ===")
    else:
        log.info("=== LIVE MODE — posting to real accounts ===")

    results = post_clip(args.video, args.platforms, dry_run)

    print("\n--- Results ---")
    for r in results:
        status = r["status"]
        icon = "OK" if status in ("posted", "dry_run") else "FAIL"
        print(f"  [{icon}] {r['platform']}: {status}")

    sys.exit(0 if all(r["status"] in ("posted", "dry_run") for r in results) else 1)


if __name__ == "__main__":
    main()
