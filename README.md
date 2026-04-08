# titkok-2-insta-reposter

never ever expose this to the internet pls

## Setup

1. Create a Meta App at https://developers.facebook.com
2. Add Instagram API product to your app
3. Configure OAuth with these permissions:
   - `instagram_content_publish`
   - `instagram_basic`
4. Connect your Instagram Professional Account to a Facebook Page

## Environment Variables

Create a `.env` file:

```env
INSTAGRAM_APP_ID=your_app_id
INSTAGRAM_APP_SECRET=your_app_secret
INSTAGRAM_ACCESS_TOKEN=your_long_lived_access_token
INSTAGRAM_ACCOUNT_ID=your_ig_account_id
INSTAGRAM_GRAPH_API_URL=https://graph.instagram.com/v25.0
AUTO_POST_ENABLED=false
AUTO_POST_INTERVAL_MINUTES=15
```

To get your Instagram Account ID:
```
GET https://graph.facebook.com/v25.0/me/accounts?access_token=YOUR_TOKEN
```
Then:
```
GET https://graph.facebook.com/v25.0/{PAGE_ID}?fields=instagram_business_account&access_token=YOUR_TOKEN
```

## UploadThing Setup

1. Sign up at https://uploadthing.com
2. Create a new app and get your credentials from the dashboard
3. Add to `.env` (legacy SDK):
   ```
   UPLOADTHING_APP_ID=your_app_id
   UPLOADTHING_SECRET=your_secret
   ```

## API Endpoints (Instagram Graph API)

- Create container: `POST {INSTAGRAM_GRAPH_API_URL}/{IG_ID}/media`
- Upload video: `POST https://rupload.facebook.com/ig-api-upload/v25.0/{CONTAINER_ID}`
- Publish: `POST {INSTAGRAM_GRAPH_API_URL}/{IG_ID}/media_publish`
- Check status: `GET {INSTAGRAM_GRAPH_API_URL}/{CONTAINER_ID}?fields=status_code`

## Workflow

1. **Upload local file** → UploadThing → get public URL
2. **Create IG container** with that URL
3. **Poll for processing** (check status_code = FINISHED)
4. **Publish** the container

## Automatic Queue Posting

- Auto-posting runs inside the Flask app while the server is up.
- The oldest `queued` item is published every `AUTO_POST_INTERVAL_MINUTES`.
- Queue page controls can override the `.env` defaults and persist the setting in `queue.json`.
- Failed items stay marked as `failed`; later queued items continue on later intervals.
- The `Run now` button on the Queue page triggers one immediate oldest-first publish attempt.

## Usage

```pwsh
# Upload local video to Instagram
python src/components/video_logic/uploadvideo.py "videos/my_video.mp4" --caption "My caption #tags"

# Upload with an explicit custom Reel cover image (publicly hosted via UploadThing)
python src/components/video_logic/uploadvideo.py "videos/my_video.mp4" --caption "My caption #tags" --cover-image-path "cover.jpg"

# Use a frame from the video as cover thumbnail (milliseconds)
python src/components/video_logic/uploadvideo.py "videos/my_video.mp4" --thumb-offset 1200
```

You can also call `POST /api/upload`, but it does not accept direct browser file uploads. Send form fields named `video_path` (required) and `cover_image_path` (optional), where each value is a filesystem path on the machine running the Flask server. Use `cover_image_path` to set a custom cover image during publish.

## Tests

```bash
PYTHONPATH=. pytest -q
```

For targeted runs:

```bash
PYTHONPATH=. pytest -q tests/test_render.py
```

Use `-k <pattern>` to narrow the test run to a specific case while iterating.
