![Demo](img/ScreenRecording_04-14-2026%2020-00-02_1.gif)

## Docker / Coolify

This app ships with a Dockerfile for Coolify's Dockerfile build pack.

Coolify settings:

- Build pack: `Dockerfile`
- Port: `3000`
- Persistent storage: mount a volume at `/app/data`
- Runtime environment variables: copy the values you need from your local `.env`
- `WEB_CONCURRENCY`: keep this set to `1` so the queue worker only runs once

The container stores queue state, captions, downloaded videos, previews, and the cover image under `/app/data`.

Run locally with Docker:

```bash
docker compose up --build
```

Then open `http://localhost:3000`.
