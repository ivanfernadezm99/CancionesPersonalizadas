# Proposal: canciones-automaticas

## Intent

AI-powered personalized romantic song generator in Spanish. User provides recipient, occasion, genre, mood, story → LLM generates Spanish lyrics → Google Lyria 3 produces music → audio preview via REST API. Freemium delivery: preview/streaming free, full download requires payment (v1+).

## Scope

### In Scope
- API-only FastAPI backend (generate, status, stream endpoints)
- Multi-provider LLM lyrics generation (test OpenAI/Gemini/OpenRouter, pick best)
- Google Lyria 3 music via OpenClaw gateway (localhost:18789)
- Audio preview/streaming endpoint (no download in v0)
- Configurable voice: male Spanish, female Spanish
- Duration extension research & implementation (target 2-3 min)
- Async SQLite job system with status polling
- MP3 output format

### Out of Scope
- Web/SPA frontend (deferred to v1)
- Full MP3 download (requires payment — freemium model)
- User accounts / authentication
- Payment processing
- Email delivery
- Revision workflow
- Celebrity voice cloning (v1+ item, documented as future)

## Capabilities

### New Capabilities
- `lyrics-generation`: Multi-provider LLM pipeline for Spanish romantic lyrics. Tests and selects best provider by quality.
- `music-generation`: Google Lyria 3 via OpenClaw gateway. Async generation + polling + duration extension.
- `audio-streaming`: Audio preview endpoint for freemium delivery. Streams generated MP3 without full download.
- `voice-configuration`: Male/female Spanish voice selection. Abstraction layer for future voice cloning support.
- `job-orchestration`: Background task system with SQLite store, status polling, and error handling.

### Modified Capabilities
None — greenfield project, no existing specs.

## Approach

```
POST /api/generate {recipient, relationship, occasion, genre, mood, story, voice}
  → LLM generates Spanish lyrics (multi-provider test harness)
  → Create background job (SQLite store)
  → OpenClaw music_generate with lyrics + voice config
  → Audio post-processing for duration extension (2-3 min target)
  → Store output file
  → Return job ID

GET /api/status/:id → {status, estimated_remaining}
GET /api/stream/:id → audio/mpeg streaming (freemium preview)
```

Backend: FastAPI + uvicorn + httpx + SQLite. LLM calls via direct API. OpenClaw at localhost:18789 for Lyria 3. Duration extension via pydub/ffmpeg (stitching, looping, or crossfade).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `app/` | New | FastAPI backend package |
| `app/lyrics/` | New | Multi-provider LLM lyrics generation |
| `app/music/` | New | OpenClaw + Lyria 3 integration |
| `app/jobs/` | New | Async job orchestration + SQLite |
| `app/stream/` | New | Audio preview/streaming |
| `app/voice/` | New | Voice selection abstraction |
| `tests/` | New | pytest + httpx integration tests |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Lyria 3 max duration hard-limited | High | Test; fallback to pydub looping/stitching |
| Voice selection unsupported by Lyria | Medium | Abstraction layer; alternate model fallback (MiniMax) |
| Spanish lyrics quality varies by LLM | Medium | Multi-provider comparison harness; prompt engineering |
| Duration extension degrades audio | Medium | Test stitching vs generative looping; preview before commit |
| OpenClaw single point of failure | Low | Gateway health check + auto-restart loop |

## Rollback Plan

Git revert to previous state. OpenClaw gateway unchanged — no rollback needed. SQLite jobs are ephemeral; clear store on rollback.

## Dependencies

- OpenClaw gateway (localhost:18789) — Lyria 3 music generation
- LLM API keys — OpenAI, Google Gemini, OpenRouter (≥1 functional)
- Python 3.10 + FastAPI + uvicorn + httpx (already installed)
- pydub + ffmpeg — audio processing for duration extension
- SQLite (stdlib, no install)

## Success Criteria

- [ ] `POST /api/generate` returns a job ID within 5 seconds
- [ ] `GET /api/status/:id` reports queued → processing → complete
- [ ] `GET /api/stream/:id` streams playable MP3 audio
- [ ] Spanish lyrics rated ≥7/10 by native speaker for 3 scenarios
- [ ] Generated song reaches 2-3 min (via extension if needed)
- [ ] Voice selection switches between male and female samples
- [ ] All endpoints covered by pytest integration tests
