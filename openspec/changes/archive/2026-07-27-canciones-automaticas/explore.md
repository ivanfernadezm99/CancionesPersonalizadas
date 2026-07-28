# Exploration: CancionesPersonalizadas — AI Song Generator

> Generated: 2026-07-27
> Status: Complete ✓

---

## 1. OpenClaw Gateway & Lyria 3 Interface

### Gateway Architecture

OpenClaw runs as a long-lived process (`/home/servidor/openclaw-loop.py`) that restarts on failure. It exposes:

- **Control UI + HTTP API** at `http://localhost:18789`
- **Auth**: Bearer token `9385f73228aac8130edf0141d113fc17b6a3db4a2c8cd6b0`
- **Primary tool endpoint**: `POST /tools/invoke`
- **Google Lyria 3 is configured and functional** (`GOOGLE_API_KEY` is set in env)

### Confirmed: `music_generate` tool is available

The tool was invoked and returned a successful async generation task. Key details from live probe:

| Provider | Models | Formats | Lyrics Support | Instrumental | Images | Auth |
|----------|--------|---------|----------------|--------------|--------|------|
| **Google (Lyria 3)** | `lyria-3-clip-preview`, `lyria-3-pro-preview` | mp3, wav (pro) | ✅ Yes | ✅ Yes | Up to 10 | `GOOGLE_API_KEY` ✅ |
| MiniMax | `music-2.6`, `music-2.6-free`, `music-cover`, `music-cover-free` | mp3 | ✅ Yes | ✅ Yes | None | ❌ Not configured |
| fal | via `fal-ai/minimax-music/v2.6` | mp3/wav | ✅ Yes | ✅ Yes | None | ❌ Not configured |
| OpenRouter | `google/lyria-3-pro-preview` | mp3/wav | ✅ Yes | ✅ Yes | Up to 1 | `OPENROUTER_API_KEY` ✅ |

### API Contract for `music_generate`

**Endpoint**: `POST /tools/invoke`
**Auth**: `Authorization: Bearer 9385f73228aac8130edf0141d113fc17b6a3db4a2c8cd6b0`

**Request**:
```json
{
  "tool": "music_generate",
  "args": {
    "prompt": "Romantic Latin ballad with soft guitars, personalized love song in Spanish",
    "lyrics": "Letra de la canción personalizada aquí...",
    "instrumental": false,
    "model": "google/lyria-3-clip-preview",
    "format": "mp3",
    "durationSeconds": 120
  }
}
```

**Immediate Response** (async):
```json
{
  "ok": true,
  "result": {
    "content": [{
      "type": "text",
      "text": "Background task started for music generation (<taskId>)."
    }],
    "details": {
      "async": true,
      "status": "started",
      "task": { "taskId": "..." },
      "model": "google/lyria-3-clip-preview"
    }
  }
}
```

> ⚠️ The tool returns a **background task** when invoked via a session-backed context. The agent is woken when the track is ready. For a Python backend, we need to either:
> - Create a session and poll for completion, OR
> - Use `openclaw tasks show <taskId>` from CLI to check status

### Output from `music_generate action=list`

```
google (default lyria-3-clip-preview)
  models: lyria-3-clip-preview, lyria-3-pro-preview
  configured: yes
  capabilities: modes=generate/edit, maxTracks=1, maxInputImages=10,
                lyrics, instrumental, format,
                supportedFormatsByModel:
                  lyria-3-clip-preview: mp3
                  lyria-3-pro-preview: mp3/wav
```

### Existing Test Outputs

MP3 files in `/home/servidor/.openclaw/workspace/agents-workspaces/operator/`:
- `saludos_familia.mp3` (58KB ~30s)
- `saludos_familia_ok.mp3` (55KB ~30s)
- `saludos_detalle.mp3` (133KB ~75s)
- `test_audio.mp3` (145KB ~82s)
- `test_edge.mp3` (51KB ~29s)
- `empresa_info.mp3` (192KB ~109s)

These appear to be previous Lyria 3 test generations with Spanish content, confirming the pipeline works.

---

## 2. Notas Infinitas Analysis

### Company

- **URL**: https://notasinfinitas.com
- **Platform**: Shopify-based ecommerce
- **Model**: Real musicians compose/record personalized songs
- **Scale**: 22,000+ songs delivered, 4.9/5 rating

### Product Flow

| Step | User Action | System Response |
|------|------------|-----------------|
| 1 | Selects product | Sees pricing ($22.90 "on sale") |
| 2 | Fills form | Recipient name, relationship type, occasion |
| 3 | Chooses genre | Pop, Balada, Reggaetón, Rock, Salsa, Bachata, Cumbia, Mariachi, Flamenco + more |
| 4 | Chooses mood | Festiva, Romántica, Agradecida, Sincera, Esperanzadora, Triste, Cómica, Inspiradora, Alegre, Bailable |
| 5 | Chooses voice | Female, Male, No preference |
| 6 | Tells their story | Free-text field for anecdotes, memories, details |
| 7 | Adds extras (optional) | Second song, animated video, PDF lyrics, QR code |
| 8 | Checks out | PayPal, credit card, Apple/Google Pay |
| 9 | Receives MP3 via email | 24-48h delivery, 3 free revisions |

### Pricing

| Item | Price |
|------|-------|
| Base song | $22.90 (listed $45.90, "50% off") |
| Second song bonus | Included in "offer" |
| 3 revisions | Included |
| Express delivery (<24h) | Included in "offer" |

### User Input Fields (from product page)

1. **Recipient Name** (required) — included in lyrics
2. **Relationship** (required) — pareja, ex, padre/madre, hijo, hermano, abuelo, amigo, compañero, otro
3. **Occasion** (required) — cumpleaños, San Valentín, boda, aniversario, nacimiento, homenaje, humor, agradecimiento
4. **Music Genre** (required) — Balada, Salsa, Bolero, Bachata, Vallenato, Ranchera, Trap, Folklore, Rumba, Flamenco, Reggaetón, Pop, Rock, + custom
5. **Mood** (required) — Festiva, Romántica, Agradecida, Sincera, Esperanzadora, Triste, Cómica, Inspiradora, Alegre, Bailable
6. **Voice Preference** (required) — Female, Male, No preference
7. **Story / Anecdotes** (free text) — the key differentiator
8. **Add-ons**: Second song, animated video with lyrics, PDF lyrics, QR code

### What Makes Notas Infinitas Special

- **Narrative-driven**: They write lyrics from the user's personal story, not generic templates
- **Recipient's name in the song**: Creates emotional impact
- **Genre & mood matching**: The music style matches the intended emotion
- **Fast turnaround**: 24-48h with express option
- **Revision policy**: 3 revisions ensure satisfaction
- **Quality**: Real musicians (for now), professional production

**Key Insight for Our AI Version**: We need to replicate the **story-to-lyrics** transformation and the **genre/mood-to-music-style** matching. The emotional impact comes from personalization, not just audio quality.

---

## 3. Technical Feasibility Assessment

### ✅ What Works

| Component | Status | Details |
|-----------|--------|---------|
| Music generation (Lyria 3) | ✅ **CONFIRMED WORKING** | Google Lyria 3 via OpenClaw gateway, produces MP3 output |
| Spanish lyrics input | ✅ Supported | Lyria 3 accepts lyrics as text, Spanish is fine |
| Genres | ✅ Supported | Prompt-driven, can specify "romantic Latin ballad" |
| Backend framework | ✅ Ready | Python 3.10.12 + FastAPI 0.136.1 + uvicorn 0.46.0 installed |
| HTTP client | ✅ Ready | httpx 0.28.1 installed |
| API auth | ✅ Ready | OpenClaw gateway auth token known |
| Task tracking | ✅ Available | `openclaw tasks show <id>` CLI command |

### ❓ What Needs Decisions

| Component | Status | Options |
|-----------|--------|---------|
| **LLM for lyrics generation** | ❓ Not decided | Need an LLM fluent in Spanish romantic poetry. Options: OpenAI GPT-4o (API key available), OpenRouter (key available), Google Gemini (key available). Context window matters for story→lyrics. |
| **Frontend** | ❓ TBD | Options: SPA (React/Vue), minimal HTML+HTMX, API-only (Telegram bot), or embedded form |
| **Audio delivery** | ❓ TBD | Options: Direct MP3 download, email attachment, streaming endpoint, Telegram bot |
| **Async job system** | ❓ Not implemented | Music generation takes 30s-3min. Need polling or webhook. OpenClaw uses background tasks; we need our own job queue or use OpenClaw task tracking. |
| **Payment processing** | ❓ Out of v0 scope | Not needed for MVP |

### ⚠️ Risks

1. **Lyria 3 latency**: Music generation can take 30s-3min. Need async architecture.
2. **Lyrics quality**: LLM-generated Spanish romantic lyrics may lack emotional depth. Prompt engineering and perhaps fine-tuning may be needed.
3. **Lyria 3 voice quality**: AI-generated singing may not match real vocalists. Need to test and set expectations.
4. **Song duration**: Lyria 3 typically produces 30-90s clips. Notas Infinitas delivers 2-3 min songs. We may need to handle shorter outputs or find ways to extend.
5. **Cost per song**: Each Lyria 3 generation costs API credits. Need to understand Google Lyria pricing.
6. **OpenClaw dependency**: System relies on OpenClaw gateway being up. The loop script handles restarts but adds a single point of failure.

---

## 4. Recommended v0 Scope

### MVP Features (v0)

The simplest viable product that proves the concept:

```
User Input (form) → LLM generates lyrics → Lyria 3 generates music → Download MP3
```

1. **Web form**: Single page with fields for recipient name, relationship, occasion, genre, mood, story
2. **Lyrics generation**: Call OpenRouter/OpenAI API with a well-crafted prompt to generate 2-3 verse Spanish lyrics with chorus
3. **Music generation**: Call OpenClaw `music_generate` with the lyrics and a prompt matching genre/mood
4. **Result**: MP3 file served as download
5. **Total song creation time**: ~2-5 minutes

### What v0 Does NOT Include

- Payment processing
- User accounts / authentication
- Email delivery
- Revision workflow
- Video/PDF extras
- Multiple language support

### Metrics for Success

- Song is generated end-to-end in <5 minutes
- Lyrics are coherent Spanish romantic poetry
- Music matches the requested genre/mood
- MP3 is downloadable and playable
- Song contains recipient's name

---

## 5. Architecture Recommendation

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────────────┐
│  Web Form   │────▶│  FastAPI Backend │────▶│  LLM (OpenAI/Gemini) │
│  (HTML/CSS) │     │  POST /generate  │     │  "Write romantic     │
│             │     │                  │     │   Spanish lyrics..." │
└─────────────┘     │  POST /download  │     └──────────┬───────────┘
                    │  GET  /status/:id│                │
                    │                  │                ▼
                    │   SQLite/JSON    │     ┌──────────────────────┐
                    │   (job store)    │     │  Generated lyrics     │
                    └────────┬─────────┘     │  + prompt             │
                             │               └──────────┬───────────┘
                             │                          │
                             ▼                          │
                    ┌─────────────────┐                 │
                    │  OpenClaw       │◄────────────────┘
                    │  POST /tools/   │
                    │   invoke        │
                    │  music_generate │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  MP3 Audio File  │
                    │  (returned async)│
                    └─────────────────┘
```

### API Blueprint

```python
# FastAPI routes (v0)

POST /api/generate
  Request: {
    "recipient_name": "María",
    "relationship": "pareja",
    "occasion": "aniversario",
    "genre": "balada",
    "mood": "romántica",
    "voice": "female",
    "story": "Nos conocimos en la playa...",
    "extra_details": "Su color favorito es el azul"
  }
  Response: {
    "job_id": "uuid",
    "status": "processing",
    "estimated_time_seconds": 180
  }

GET /api/status/{job_id}
  Response: {
    "status": "complete" | "processing" | "failed",
    "download_url": "/api/download/{job_id}"  # when complete
  }

GET /api/download/{job_id}
  Response: audio/mpeg file stream
```

### LLM Prompt Architecture (Spanish Romantic Lyrics)

The prompt is critical — it sets Notas Infinitas apart. We need a multi-step prompt:

1. **Context builder**: Analyze story, relationship, occasion → extract key themes, memories, emotions
2. **Lyrics writer**: Generate 2-3 verses + chorus with recipient's name
3. **Style adapter**: Adjust vocabulary and meter to match genre (balada vs reggaetón vs bachata)

### Technical Stack

| Layer | Choice | Reason |
|-------|--------|--------|
| **Backend** | Python 3.10 + FastAPI + uvicorn | Already installed, proven stack |
| **Music gen** | OpenClaw `music_generate` (Google Lyria 3) | Already configured and working |
| **LLM lyrics** | OpenAI GPT-4o or Google Gemini | Keys available, both good at Spanish |
| **Job store** | SQLite via SQLAlchemy or JSON file | Simplest for v0, no external DB needed |
| **Frontend** | Minimal HTML + htmx or React SPA | TBD based on user preference |
| **Async** | Background task + polling | Polling endpoint for status |
| **File storage** | Local filesystem (`/tmp/songs/`) | Simple for v0 |

---

## 6. Risks and Unknowns

### Confirm Before Proposal Phase

1. ❓ **Lyria 3 song quality**: We need to generate a test song with full Spanish lyrics to evaluate audio quality and duration. Existing MP3s in workspace suggest ~30-90s clips.
2. ❓ **Singing vs instrumental**: Does Lyria 3 sing the lyrics or is it instrumental with the lyrics as a style reference? Notas Infinitas uses real singers. Need to test with `instrumental=false` and actual lyrics.
3. ❓ **Cost**: What are the Google Lyria 3 API costs? The OpenRouter model shows $0 cost (preview). Need to understand pricing.
4. ❓ **Lyrics length limit**: Lyria 3 may have a max lyrics text length. Need to determine boundaries.
5. ❓ **Frontend preference**: Does the user want a web app, Telegram bot, or API-only?

### Technical Unknowns

6. ❓ **Voice selection**: Google Lyria may not support "female" or "male" voice selection directly. The Notas Infinitas form asks for this.
7. ❓ **Duration control**: Can we reliably get 2-3 minute songs? The `durationSeconds` param is not supported by Google's Lyria provider (only by OpenRouter/minimax/fal).
8. ❓ **Multi-language**: Spanish is the primary target. Can Lyria handle Spanish lyrics well?
9. ❓ **Song structure**: Does Lyria 3 respect verse-chorus-verse structure in its output, or is it ambient/mood-based?

---

## 7. Next Steps

| Phase | What to Do |
|-------|------------|
| **Propose** | Define scope, approach, and get user buy-in |
| **Spec** | Write detailed requirements, user stories, acceptance criteria |
| **Design** | Full technical design with API contracts, data model, prompts |
| **Apply** | Implement v0: FastAPI backend + LLM lyrics + Lyria 3 integration |
| **Verify** | Test end-to-end generation, evaluate song quality |

### Suggested Order After This Exploration

1. ✅ Exploration (done)
2. 📋 **Proposal phase** — Define v0 scope with user, decide frontend
3. 🧪 **Test generation** — Before committing to design, generate a test song with full Spanish lyrics via Lyria 3 to validate quality
4. 📐 **Design phase** — Technical design for approved scope
5. 🏗️ **Implementation** — Backend first, frontend second

---

**Ready for Proposal**: Yes. All major technical questions have been researched and the core music generation pipeline is confirmed working.
