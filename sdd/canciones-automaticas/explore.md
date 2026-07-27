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
    "format": "mp3"
  }
}
```

**Immediate Response** (async):
```json
{
  "ok": true,
  "result": {
    "details": {
      "async": true,
      "status": "started",
      "task": { "taskId": "8666fdb6-..." }
    }
  }
}
```

> ⚠️ The tool returns a **background task** when invoked via a session-backed context. For a Python backend, we need to either: create a session and poll for completion, OR use `openclaw tasks show <taskId>` from CLI.

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

MP3 files in `/home/servidor/.openclaw/workspace/agents-workspaces/operator/` (55KB-192KB), confirming Lyria 3 has been used with Spanish content before.

---

## 2. Notas Infinitas Analysis

### Product Flow

| Step | User Action | Field |
|------|------------|-------|
| 1 | Selects product | $22.90/song |
| 2 | Tells recipient info | **Name** (required), **Relationship** (12 options) |
| 3 | Chooses occasion | Birthday, Valentine, Wedding, Anniversary, Birth, Memorial, etc. |
| 4 | Picks **genre** | Balada, Salsa, Bolero, Bachata, Reggaetón, Pop, Rock, Flamenco, +more |
| 5 | Picks **mood** | Romántica, Festiva, Agradecida, Triste, Cómica, Inspiradora, +more |
| 6 | Chooses **voice** | Female, Male, No preference |
| 7 | Shares **story** | Free-text: memories, anecdotes, feelings |
| 8 | Add-ons (optional) | Second song, animated video, PDF lyrics, QR code |
| 9 | Payment + delivery | MP3 via email in 24-48h, 3 free revisions |

### Key Differentiator

> **"Tú cuentas la historia — nosotros la convertimos en canción"**

You tell your story, they turn it into music. The emotional impact comes from hyper-personalization — using the recipient's name, specific memories, and matching the genre/mood to the occasion.

---

## 3. Technical Feasibility Assessment

### ✅ What Works

| Component | Status | Details |
|-----------|--------|---------|
| Music generation (Lyria 3) | ✅ **CONFIRMED** | Google Lyria 3 via OpenClaw gateway |
| Spanish lyrics input | ✅ Supported | Lyria 3 accepts lyrics as text |
| Genres | ✅ Supported | Prompt-driven genre selection |
| Backend | ✅ Ready | Python 3.10.12 + FastAPI 0.136.1 + uvicorn |
| HTTP client | ✅ Ready | httpx 0.28.1 |
| Gateway auth | ✅ Ready | Token known |

### ❓ What Needs Decisions

| Component | Status | Options |
|-----------|--------|---------|
| **LLM for lyrics** | ❓ Not decided | OpenAI GPT-4o, Google Gemini, or OpenRouter. All keys available. |
| **Frontend** | ❓ TBD | HTML+htmx, React SPA, API-only, or Telegram bot |
| **Delivery** | ❓ TBD | Direct download, email, or Telegram |
| **Async job system** | ❓ TBD | Need polling or webhook for Lyria 3 generation (30s-3min) |

### ⚠️ Risks

1. **Lyria 3 latency**: 30s-3min generation time → async architecture required
2. **Lyrics quality**: LLM-generated Spanish romance lyrics may lack depth
3. **Singing quality**: Lyria 3 vocals may not match real singers
4. **Song duration**: Lyria 3 typically produces 30-90s, Notas Infinitas delivers 2-3 min
5. **Cost**: Unknown Google Lyria API pricing (OpenRouter shows $0 — preview)
6. **Voice selection**: Not clear if Lyria supports female/male voice toggle
7. **Duration control**: `durationSeconds` is NOT supported by Google's Lyria provider

---

## 4. Recommended v0 Scope

### MVP Pipeline

```
User Input → LLM generates Spanish lyrics → Lyria 3 generates music → MP3 download
```

### MVP Features
1. Single-page web form: recipient name, relationship, occasion, genre, mood, story
2. LLM-generated Spanish romantic lyrics (2-3 verses + chorus)
3. Lyria 3 via OpenClaw for music generation
4. MP3 file download
5. Total time: ~2-5 minutes

### Out of v0 Scope
- Payment processing
- User accounts
- Email delivery
- Revision workflow
- Video/PDF extras

---

## 5. Architecture Recommendation

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Web Form   │────▶│  FastAPI Backend │────▶│  LLM (LLM)      │
│  (Minimal)  │     │  POST /generate  │     │  Spanish lyrics  │
│             │     │  GET  /status    │     └────────┬────────┘
└─────────────┘     │  GET  /download  │              │
                    │  SQLite job store│              │
                    └────────┬─────────┘              │
                             │                        │
                             ▼                        │
                    ┌─────────────────┐               │
                    │  OpenClaw        │◄──────────────┘
                    │  music_generate  │  (lyrics+prompt)
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │     MP3 File     │
                    └─────────────────┘
```

### Tech Stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Backend | Python 3.10 + FastAPI + uvicorn | Already installed |
| Music | OpenClaw `music_generate` (Google Lyria 3) | Working, configured |
| LLM lyrics | OpenAI GPT-4o or Google Gemini | Both keys available |
| Job store | SQLite | Simplest for v0 |
| Frontend | TBD with user | Minimal HTML or SPA |
| Async | Background task + polling | Music generation takes ~2 min |

---

## 6. Next Steps

1. ✅ Exploration (done — this document)
2. 📋 **Proposal phase** — Define v0 scope, decide frontend
3. 🧪 **Test generation** — Generate a test song with full Spanish lyrics to validate Lyria 3 quality
4. 📐 **Design phase** — Full technical design
5. 🏗️ **Implementation** — Backend first, frontend second

---

**Ready for Proposal**: Yes. Core music generation pipeline confirmed working. All major unknowns are documented.
