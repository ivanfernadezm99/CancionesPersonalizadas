# Design: Canciones Automáticas

AI-powered romantic song generator in Spanish. API-only FastAPI backend. Freemium audio preview in v0.

## Technical Approach

Greenfield FastAPI app with 5 capability modules orchestrated by async background jobs. Generation starts synchronously (returns 202 + job_id), then orchestrates: LLM lyrics (multi-provider cascade) → OpenClaw/Lyria 3 music → post-processing → MP3 output. Status polling via SQLite. Streaming via HTTP Range.

## Architecture Decisions

| Option | Tradeoffs | Decision |
|--------|-----------|----------|
| Background worker: `asyncio.create_task` vs Celery/ARQ | create_task: simple, zero infra, lost on restart. Celery: Redis dep, overkill for v0 | **asyncio.create_task** — greenfield v0, restart loss acceptable (jobs stay queued) |
| LLM selection: cascade vs parallel-and-pick-best | Cascade: faster, fewer API calls. Parallel: better quality at 3x cost | **Cascade** — try OpenAI → Gemini → OpenRouter; stop on first valid result |
| Voice control: prompt injection vs structured param | Lyria 3 only supports prompt injection; no structured voice param | **Prompt injection** — voice descriptor string baked into OpenClaw `prompt` field |
| Duration extension: crossfade-loop vs stitch vs ffmpeg concat | Loop: simple, artifacts at join. Stitch: smoother, needs multiple generations | **Smart crossfade loop** (primary) → **simple loop** (fallback) — one generation, pydub crossfade |
| Streaming: `StreamingResponse` async generator vs `FileResponse` | Both support Range. `StreamingResponse` gives manual disconnect control | **StreamingResponse** with async generator + disconnect detection |
| Rate limiting: in-memory semaphore vs SQLite COUNT | Semaphore: fast, lost on restart. SQLite: survives restart, atomic | **asyncio.Semaphore(5)** — simple, job store already has status for visibility |

## Data Flow

```
POST /api/generate {recipient, ...voice}
  │
  ▼
┌─────────────────────────────────────────────────────┐
│  FastAPI route: validate → create job → launch worker │
│  Return 202 {job_id, status:"queued", endpoints}     │
└──────────────────────┬──────────────────────────────┘
                       │ asyncio.create_task(job_worker)
                       ▼
┌───────────────────────────────────────────────────┐
│  job_worker(job_id)                               │
│                                                    │
│  status → lyrics_generating                        │
│    ├─ lyrics.generate(recipient, ...) → lyrics     │
│    └─ fail → status=failed, return                 │
│                                                    │
│  status → music_generating                         │
│    ├─ voice.build_prompt(voice, genre) → v_prompt  │
│    ├─ music.generate(lyrics, v_prompt)              │
│    │   ├─ openclaw.invoke() → taskId               │
│    │   ├─ poll(taskId, 5s interval, 5min timeout)  │
│    │   └─ download_mp3(url) → local path           │
│    └─ fail → status=failed, return                 │
│                                                    │
│  status → processing                               │
│    ├─ music.extend_duration(path, target=150s)     │
│    └─ move to {output_dir}/{job_id}/final.mp3      │
│                                                    │
│  status → complete                                  │
└───────────────────────────────────────────────────┘

GET /api/status/{id} → SQLite → job state JSON
GET /api/stream/{id} → validate job=complete → StreamingResponse(final.mp3)
```

## Module Structure

```
app/
├── __init__.py
├── main.py              # FastAPI app, lifespan, router registration
├── config.py            # pydantic-settings BaseSettings (env vars)
├── models.py            # Shared Pydantic models (GenerateRequest, JobStatusResponse, LyricsOutput)
├── lyrics/
│   ├── __init__.py      # generate() — public interface
│   ├── providers.py     # OpenAI/Gemini/OpenRouter clients + cascade logic
│   └── prompts.py       # Spanish romantic prompt templates per genre
├── music/
│   ├── __init__.py      # generate(), extend_duration() — public interface
│   ├── openclaw.py      # OpenClaw HTTP client (invoke, poll, download)
│   └── durext.py        # Duration extension via pydub (crossfade loop, simple loop)
├── stream/
│   ├── __init__.py      # stream_generator() — async file reader with disconnect guard
│   └── router.py        # GET /api/stream/{id} route
├── voice/
│   ├── __init__.py      # build_prompt(), get_available_voices() — public interface
│   └── registry.py      # VoiceConfig dict registry + PromptBuilder
└── jobs/
    ├── __init__.py      # create_job(), get_job(), update_status() — public interface
    ├── store.py         # SQLite connection manager, queries, state machine guard
    ├── worker.py        # job_worker() — orchestrates lyrics→music→processing pipeline
    └── cleanup.py       # Periodic TTL-based cleanup of old jobs + files
tests/
├── conftest.py          # Fixtures: test DB, mock OpenClaw, mock LLM providers
├── test_lyrics/
│   ├── test_generate.py
│   └── test_providers.py
├── test_music/
│   ├── test_openclaw.py
│   └── test_durext.py
├── test_stream/
│   └── test_router.py
├── test_voice/
│   ├── test_registry.py
│   └── test_prompt.py
└── test_jobs/
    ├── test_store.py
    ├── test_worker.py
    └── test_cleanup.py
```

## Key Interfaces

```python
# --- app/lyrics/__init__.py ---
async def generate(
    recipient: str, relationship: str, occasion: str,
    genre: str, mood: str, story: str | None
) -> LyricsResult:
    """Cascade through providers, return first valid LyricsResult."""

class LyricsResult(BaseModel):
    verses: list[Verse]          # 2-3 verses, 4 lines each
    chorus: Chorus               # 4 lines
    bridge: Bridge | None        # optional, 2-4 lines
    language: str = "es"
    title_suggestion: str
    provider: str                # which LLM was used

class Verse(BaseModel):
    number: int
    lines: list[str]             # 4 lines, each 10-100 chars, Spanish

# --- app/music/__init__.py ---
async def generate(lyrics: str, voice_prompt: str) -> Path:
    """Invoke OpenClaw, poll, download MP3, return local file path."""

async def extend_duration(mp3_path: Path, target_seconds: int = 150) -> Path:
    """Extend via smart crossfade loop. Return path to extended file."""

# --- app/music/openclaw.py ---
class OpenClawClient:
    def __init__(self, base_url: str, token: str): ...
    async def invoke(self, lyrics: str, prompt: str) -> str: ...   # returns task_id
    async def poll(self, task_id: str, timeout: int = 300) -> str: ...  # returns download_url
    async def download(self, url: str) -> bytes: ...

# --- app/music/durext.py ---
def smart_crossfade_loop(audio: AudioSegment, target_ms: int) -> AudioSegment: ...
def simple_loop(audio: AudioSegment, target_ms: int) -> AudioSegment: ...

# --- app/voice/__init__.py ---
VOICE_REGISTRY: dict[str, VoiceConfig] = {
    "female": VoiceConfig(id="female", label="Voz Femenina", gender="female",
                          prompt_es="cantante femenina española"),
    "male": VoiceConfig(id="male", label="Voz Masculina", gender="male",
                        prompt_es="cantante masculino español"),
}

def build_prompt(voice_id: str, genre: str, mood: str) -> str:
    """Combine voice descriptor + genre + mood into Lyria 3 prompt."""

# --- app/jobs/__init__.py ---
async def create_job(params: GenerateRequest) -> str: ...   # returns job_id
async def get_job(job_id: str) -> JobRecord | None: ...
async def update_status(job_id: str, new_status: str,
                         error: str | None = None, **extra) -> None: ...
async def count_active_jobs() -> int: ...

# --- app/jobs/worker.py ---
async def job_worker(job_id: str) -> None:
    """Pipeline: lyrics → music → processing → complete. Sets status=queued on exit."""

class JobStateMachine:
    transitions = {
        "queued": ["lyrics_generating"],
        "lyrics_generating": ["music_generating", "failed"],
        "music_generating": ["processing", "failed"],
        "processing": ["complete", "failed"],
        "complete": [],
        "failed": [],
    }
    @classmethod
    def validate(cls, from_: str, to_: str) -> bool: ...
```

## Database Schema

```sql
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS jobs (
    job_id          TEXT PRIMARY KEY,
    status          TEXT NOT NULL DEFAULT 'queued'
                    CHECK(status IN ('queued','lyrics_generating','music_generating',
                                     'processing','complete','failed')),
    params          TEXT NOT NULL,               -- JSON: full GenerateRequest
    progress        REAL NOT NULL DEFAULT 0.0,
    estimated_remaining INTEGER DEFAULT 180,
    error           TEXT,
    metadata        TEXT DEFAULT '{}',           -- JSON: recipient, genre, duration_extended etc.
    created_at      TEXT NOT NULL,               -- ISO 8601
    updated_at      TEXT NOT NULL,               -- ISO 8601
    completed_at    TEXT                         -- ISO 8601, NULL until complete/failed
);

CREATE TABLE IF NOT EXISTS job_transitions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT NOT NULL REFERENCES jobs(job_id),
    from_status     TEXT,
    to_status       TEXT NOT NULL,
    timestamp       TEXT NOT NULL,               -- ISO 8601
    error           TEXT                         -- populated on failed transitions
);

CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created ON jobs(created_at);
CREATE INDEX idx_transitions_job ON job_transitions(job_id);
```

## API Contract

| Method | Path | Status | Response |
|--------|------|--------|----------|
| POST | `/api/generate` | 202 | `{job_id, status:"queued", estimated_total_seconds:180, endpoints:{status, stream}}` |
| POST | `/api/generate` | 422 | Validation error detail |
| POST | `/api/generate` | 429 | `{error:"too_many_requests"}` + Retry-After |
| GET | `/api/status/{job_id}` | 200 | Full `JobStatusResponse` (status, progress, error, metadata) |
| GET | `/api/status/{job_id}` | 404 | `{error:"job_not_found"}` |
| GET | `/api/stream/{job_id}` | 200 | `audio/mpeg` streaming with Range support |
| GET | `/api/stream/{job_id}` | 206 | Partial content (`audio/mpeg`) |
| GET | `/api/stream/{job_id}` | 409 | Job in progress (`Retry-After` header) |
| GET | `/api/stream/{job_id}` | 410 | Job failed (`error` in body) |
| GET | `/api/stream/{job_id}` | 416 | Range Not Satisfiable |
| GET | `/api/stream/{job_id}` | 404 | Job not found |

**All responses include** `X-Job-Status` header. Stream responses include `X-Freemium-Preview: true`.

## OpenClaw Integration

```
OpenClawClient(base_url="http://localhost:18789", token=env("OPENCLAW_TOKEN"))

1. POST /tools/invoke {tool:"music_generate", args:{prompt, lyrics, ...}}
   → 200 {ok:true, result:{details:{async:true, status:"started", task:{taskId}}}}
   → Non-200 → retry (2 attempts, 10s linear backoff) → fail job

2. Poll: GET /tools/tasks/{taskId} (or CLI openclaw tasks show)
   Interval: 5s, exponential backoff cap 30s. Timeout: 300s.
   Status: "started"|"completed"|"failed"
   → completed → extract download_url from result

3. Download the MP3 from download_url
   Retry: 3 attempts, exponential 2/4/8s backoff
   Validate: size > 1KB, MP3 header check

4. Token stored in OPENCLAW_TOKEN env var. Validated at startup.
```

## Duration Extension Strategy

```python
def smart_crossfade_loop(audio: AudioSegment, target_ms: int) -> AudioSegment:
    """Crossfade-loop the segment for natural extension.
    1. Take last 10% as crossfade intro
    2. Take first 10% as crossfade outro
    3. Loop full segment N times
    4. Apply 2s crossfade between each join
    5. Fade out last 2s of final loop
    """

def simple_loop(audio: AudioSegment, target_ms: int) -> AudioSegment:
    """Fallback: naive repeat with fade-out. Use if crossfade artifacts detected."""

def extend_duration(path: Path, target_seconds: int = 150) -> ExtendResult:
    if ffmpeg not found: return ExtendResult(path=path, extended=False)
    audio = AudioSegment.from_mp3(path)
    if audio.duration_seconds >= target_seconds: return ExtendResult(path=path, extended=False)
    try:
        extended = smart_crossfade_loop(audio, target_seconds * 1000)
        out = path.parent / "final.mp3"
        extended.export(out, format="mp3", bitrate="192k")
        return ExtendResult(path=out, extended=True)
    except Exception:
        return ExtendResult(path=path, extended=False)
```

## Testing Strategy

| Layer | What | How |
|-------|------|-----|
| **Unit** | OpenClawClient.invoke/poll | `httpx_mock` — stub HTTP responses. Test retry logic, timeout, malformed tasks |
| **Unit** | Duration extension | Test with 5s synthetic MP3 → verify 120-180s output. Mock pydub if needed |
| **Unit** | Voice prompt builder | Assert `build_prompt("male", "bachata", "romántica")` contains expected Spanish tokens |
| **Unit** | Job state machine | Test all valid and invalid transitions (Table-driven) |
| **Unit** | LLM cascade | Mock each provider; test OpenAI succeeds → no fallback called |
| **Integration** | POST /api/generate → 202 | Full pipeline with all mocks. Verify DB row created |
| **Integration** | GET /api/stream/{id} Range | Create real MP3 fixture → assert 206 with correct Content-Range |
| **Integration** | Job cleanup | Insert old job → trigger cleanup → assert deleted |
| **Integration** | Rate limiting | Create 6 concurrent requests → assert 5 succeed, 1 gets 429 |

**Mock fixtures** (conftest.py): `mock_openclaw`, `mock_llm_providers`, `test_db`, `test_output_dir`, `sample_mp3`.

## Storage Layout

```
{OUTPUT_DIR:-./output}/
└── {job_id}/
    ├── generated.mp3        # Raw from OpenClaw
    └── final.mp3            # After duration extension (or symlink if not extended)
```

## Migration / Rollout

No migration required — greenfield project. Startup auto-creates SQLite tables and validates voice registry. OpenClaw gateway is independent.

## Open Questions

- [ ] OpenClaw task polling API path — confirmed `/tools/invoke` but need exact task status endpoint (`GET /tools/tasks/{id}` or via CLI). Spec says poll, exact HTTP endpoint TBD.
- [ ] ffmpeg installed on target system? pydub needs it for duration extension.
- [ ] Freemium preview duration limit — indefinite stream or time-boxed (e.g. 60s)? Spec says streaming-only, no download. Confirm intent.
