# Julian Dorey - Social Media Content Workflow

Automated pipeline for processing and posting Julian Dorey podcast clips across Instagram Reels, TikTok, and YouTube Shorts.

## Architecture

```
Discord clips ──> data/clips-input/ ──> Validate ──> Watermark ──> data/clips-processed/
                                                                          │
                                   n8n scheduler ◄────────────────────────┘
                                        │
                        ┌───────────────┼───────────────┐
                        ▼               ▼               ▼
                   Instagram        TikTok          YouTube
                   Reels            @juliandorey    Shorts
                   @juliandorey     .wav            (clips channel)
                   .wav
```

**Stack:**
- **n8n** (self-hosted) — workflow orchestration, scheduling, API calls
- **PostgreSQL** — n8n backend database
- **Redis** — n8n queue mode for reliable webhook processing
- **FFmpeg** — video processing (watermark overlay)
- **Python** — clip validation and watermark scripts
- **Docker Compose** — runs everything

## Quick Start (Local)

### 1. Prerequisites

- **Python 3.10+**
- **FFmpeg** (`brew install ffmpeg` on macOS, `sudo apt install ffmpeg` on Ubuntu)

### 2. One-command setup

```bash
bash setup.sh
```

This installs Python deps, downloads the watermark, creates data directories, and sets up your `.env` file.

### 3. Process clips

```bash
# Single clip
bash scripts/process_clip.sh data/clips-input/EP345_topic.mp4

# All clips at once
python3 scripts/batch_process.py data/clips-input/ data/clips-processed/

# Generate captions for posting
python3 scripts/generate_captions.py data/clips-processed/ --all
```

### Optional: n8n Automated Posting

If you want fully automated scheduled posting (requires Docker):

```bash
docker compose up -d
```

Then open `http://localhost:5678`, import the workflows from `n8n-workflows/`, and configure API credentials.

## Usage

### Adding Clips

1. Get clips from the Discord `#clips-for-you` or `#viral-clips` channels
2. Rename each clip following the naming convention:
   ```
   EP345_topic_description.mp4
   ```
   The `EP<number>` prefix is required — clips from episodes before 343 will be rejected.
3. Drop the file into `data/clips-input/`
4. The processor will automatically:
   - Validate the episode number (must be >= 343)
   - Verify it's a valid video file
   - Apply the Julian Dorey YouTube watermark (25% size, 80% opacity, centered below subtitles)
   - Move the result to `data/clips-processed/`

### Manual Processing

Process a single clip without the watcher:

```bash
./scripts/process_clip.sh EP350_on_ai_future.mp4
```

Or run the individual scripts directly:

```bash
# Validate only
python3 scripts/validate_clip.py EP350_on_ai_future.mp4

# Watermark only
python3 scripts/apply_watermark.py input.mp4 output.mp4 \
  --watermark config/watermark/julian_dorey_watermark.png \
  --scale 0.25 --opacity 0.8
```

### Scheduling Posts via API

The content calendar workflow exposes a webhook:

```bash
curl -X POST http://localhost:5678/webhook/schedule-clip \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "EP350_on_ai_future_watermarked.mp4",
    "scheduled_date": "2026-03-01T13:00:00-08:00",
    "platforms": ["instagram", "tiktok", "youtube"]
  }'
```

### Posting Schedule

By default, posts go out at **9 AM, 1 PM, 5 PM Pacific**. Change this in the n8n workflow or in `config/platforms.json`.

## Watermark Specs

| Setting  | Value                              |
|----------|------------------------------------|
| Size     | 25% of video width                 |
| Opacity  | 80%                                |
| Position | Horizontally centered, below subtitles (~88% down from top) |
| File     | `config/watermark/julian_dorey_watermark.png` |

See the attached example images for reference on proper watermark framing.

## Platform Accounts

| Platform  | Handle              | Bio Link                                    |
|-----------|---------------------|---------------------------------------------|
| Instagram | @juliandorey.wav    | https://www.youtube.com/@JulianDorey/       |
| TikTok    | @juliandorey.wav    | https://www.youtube.com/@JulianDorey/       |
| YouTube   | Julian Dorey Clips  | https://www.youtube.com/@JulianDorey/       |

All accounts must have Julian's main YouTube channel link in the bio.

## Rules

1. Only clips from **Episode 343 and newer** are allowed
2. All clips **must** include Julian's YouTube watermark
3. **No** downloading/reposting other people's clips — edit clips yourself
4. **No** botting engagement (followers, views, likes)
5. **No** posts that make Julian look bad
6. Follow styles from the `short-form-wiki` in the [Notion site](https://sonny-army.notion.site/)

## API Credentials Setup

### Instagram (Meta Graph API)

1. Create a Meta App at [developers.facebook.com](https://developers.facebook.com)
2. Add Instagram Graph API product
3. Get a long-lived access token
4. Set `META_ACCESS_TOKEN` and `INSTAGRAM_BUSINESS_ACCOUNT_ID` in `.env`

### TikTok (Content Posting API)

1. Register at [developers.tiktok.com](https://developers.tiktok.com)
2. Create an app with "Content Posting" scope
3. Get OAuth access token
4. Set `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_ACCESS_TOKEN` in `.env`

### YouTube (Data API v3)

1. Create project in [Google Cloud Console](https://console.cloud.google.com)
2. Enable YouTube Data API v3
3. Create OAuth 2.0 credentials
4. Get a refresh token via OAuth flow
5. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` in `.env`

## Directory Structure

```
.
├── setup.sh                    # One-command local setup
├── requirements.txt            # Python dependencies
├── docker-compose.yml          # n8n + Postgres + Redis (optional)
├── Dockerfile.processor        # FFmpeg + Python processor image
├── .env.example                # Environment template
├── config/
│   ├── platforms.json          # Channel configs, rules, watermark specs
│   └── watermark/              # Watermark PNG (downloaded by setup.sh)
├── scripts/
│   ├── apply_watermark.py      # FFmpeg watermark overlay
│   ├── validate_clip.py        # Episode number + video validation
│   ├── batch_process.py        # Process all clips in a directory
│   ├── generate_captions.py    # Platform-specific captions & metadata
│   ├── download_watermark.sh   # Download watermark from Google Drive
│   ├── watch_and_process.py    # Auto-processing daemon (Docker)
│   └── process_clip.sh         # Manual single-clip processing
├── n8n-workflows/
│   ├── 01-clip-ingestion.json  # Clip validation + watermark workflow
│   ├── 02-multi-platform-post.json  # Scheduled multi-platform posting
│   └── 03-content-calendar.json     # Webhook API for scheduling
└── data/
    ├── clips-input/            # Drop raw clips here
    ├── clips-processed/        # Watermarked clips ready to post
    └── clips-posted/           # Archive of posted clips
```
