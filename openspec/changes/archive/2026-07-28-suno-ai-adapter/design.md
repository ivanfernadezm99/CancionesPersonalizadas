# Design: Suno AI Music Provider Adapter

## Technical Approach

Mirror `app/lyrics/providers.py`: `BaseMusicProvider(ABC)` with `async generate()`. `OpenClawProvider` wraps existing `OpenClawClient` (no changes). `SunoProvider` implements Suno REST API (generate → poll → download). Config-level selection via `MUSIC_PROVIDER` env var. `app/music/__init__.py` calls `_select_music_provider()` at call time — no cascade.

## Architecture

```
app/music/
├── __init__.py        [MODIFY] — _select_music_provider(), generate() delegates
├── providers.py       [NEW]    — BaseMusicProvider ABC, OpenClawProvider, SunoProvider, MusicGenerationError
├── openclaw.py        [UNCHANGED]
├── clipchain.py       [UNCHANGED]
└── durext.py          [UNCHANGED]

app/config.py          [MODIFY] — MUSIC_PROVIDER, SUNO_API_KEY, SUNO_BASE_URL, SUNO_DEFAULT_MODEL

app/projects/
├── __init__.py        [MODIFY] — reference_audio_url in metadata, bypass chaining for suno
├── router.py          [MODIFY] — keep ref audio for Suno Cover, serve via GET /api/ref-audio/{id}
├── store.py           [UNCHANGED]
└── ref_audio.py       [NEW]    — store/serve/cleanup reference audio files

Flow:
POST /api/projects/{id}/reference-audio
  ├─ MUSIC_PROVIDER=openclaw → analyze → delete file (current behavior)
  └─ MUSIC_PROVIDER=suno     → analyze → save to ref-audio/{id}/reference.mp3 → return URL

POST /api/projects/{id}/final
  └─ project_worker()
       ├─ lyrics_generate()
       ├─ build_prompt()
       └─ music_generate(lyrics, voice_prompt, model, job_id, reference_audio=url)
            └─ _select_music_provider()
                 ├─ MUSIC_PROVIDER=openclaw → OpenClawProvider
                 └─ MUSIC_PROVIDER=suno     → SunoProvider
```


## Architecture Decisions

### Decision: BaseMusicProvider signature — `model` as optional kwarg

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Omit `model` from ABC | Forces branching in `generate()` or hacky constructor params | REJECTED — leaks provider type to caller |
| Include `model: str \| None = None` | OpenClaw uses it, Suno ignores it; clean delegation | ✅ SELECTED |

OpenClawProvider uses `model or self.default_model`. SunoProvider always uses `settings.SUNO_DEFAULT_MODEL`.

### Decision: Reference audio serving — local files + FastAPI route

| Option | Tradeoff | Decision |
|--------|----------|----------|
| S3 upload | Requires AWS setup, creds, billing | REJECTED — overengineered for local deployment |
| Local file + route | Requires public URL reachable from Suno | ✅ SELECTED — simplest, matches existing patterns |

Reference audio stored at `{OUTPUT_DIR}/ref-audio/{project_id}/reference.mp3`. Served via `GET /api/ref-audio/{project_id}`. URL exposed to Suno uses `PUBLIC_BASE_URL` config (or Host header fallback).

### Decision: Error model — raised exceptions, not None returns

Music generation is expensive (no cascade). Errors propagate as exceptions. Single `MusicGenerationError` base. Suno and OpenClaw each have typed subclasses.

### Decision: Chaining guard for Suno

If `chaining_enabled=True` and `MUSIC_PROVIDER=suno`, `project_worker` logs a warning and disables chaining. The clipchain code path never enters for Suno.

## Data Flow

### Text-to-Music (Suno generate)

```
generate(lyrics, voice_prompt, job_id)
  │
  ▼
SunoProvider.generate(lyrics, voice_prompt, job_id)
  │
  ├─ POST /api/v1/generate
  │   { prompt: voice_prompt, customMode: true, style: voice_prompt,
  │     title: "", model: SUNO_DEFAULT_MODEL, lyrics: lyrics }
  │   Headers: Authorization: Bearer {key}
  │
  ▼ returns task_id
  │
  ├─ Poll GET /api/v1/generate/record-info?taskId={task_id}
  │   Every 5s (exp backoff cap 30s), timeout 300s
  │
  ▼ returns {audio_url, stream_audio_url, ...}
  │
  ├─ Download GET audio_url → MP3 bytes
  │
  ▼
  └─ Write {OUTPUT_DIR}/{job_id}/generated.mp3
```

### Cover Mode (reference audio + lyrics)

```
generate(lyrics, voice_prompt, reference_audio="https://.../ref.mp3", job_id)
  │
  ▼
SunoProvider.generate()
  ├─ HEAD reference_audio → verify HTTP 200
  │   (fail fast: "reference audio unavailable")
  │
  ├─ POST /api/v1/generate
  │   { ..., reference_audio_url: "https://.../ref.mp3" }
  │
  ▼ (same poll + download flow)
```

### OpenClow path (unchanged)

```
generate(lyrics, voice_prompt, model, job_id)
  │
  ▼
OpenClawProvider.generate(lyrics, voice_prompt, model=model, job_id)
  ├─ OpenClawClient.invoke() → task_id
  ├─ OpenClawClient.poll() → download_url
  ├─ OpenClawClient.download() → MP3 bytes
  └─ Write {OUTPUT_DIR}/{job_id}/generated.mp3
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/music/providers.py` | **Create** | `BaseMusicProvider(ABC)`, `OpenClawProvider`, `SunoProvider`, `MusicGenerationError`, `SunoError` |
| `app/music/__init__.py` | Modify | `_select_music_provider()`, `generate()` delegates to provider, preserve signature |
| `app/config.py` | Modify | Add `MUSIC_PROVIDER`, `SUNO_API_KEY`, `SUNO_BASE_URL`, `SUNO_DEFAULT_MODEL`, `PUBLIC_BASE_URL` |
| `app/projects/__init__.py` | Modify | Pass `reference_audio_url` to `generate()`, chaining guard for Suno |
| `app/projects/router.py` | Modify | Keep reference audio file when `MUSIC_PROVIDER=suno`, add `GET /api/ref-audio/{id}` |
| `tests/test_music/test_providers.py` | **Create** | Unit tests for providers |
| `tests/test_music/test_generate.py` | Modify | Add tests for abtract provider delegation |

## Interfaces

### Provider ABC

```python
class BaseMusicProvider(ABC):
    """Abstract base for music generation providers."""

    def __init__(self, name: str, api_key: str, base_url: str) -> None:
        self.name = name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    @abstractmethod
    async def generate(
        self,
        lyrics: str,
        voice_prompt: str,
        *,
        model: str | None = None,
        reference_audio: str | None = None,
        job_id: str | None = None,
    ) -> Path:
        ...
```

### OpenClowProvider

```python
class OpenClawProvider(BaseMusicProvider):
    def __init__(self, token: str, base_url: str) -> None:
        super().__init__("openclaw", token, base_url)
        self._client = OpenClawClient(base_url, token)

    async def generate(self, lyrics, voice_prompt, *, model=None,
                       reference_audio=None, job_id=None) -> Path:
        # reference_audio is ignored — OpenClaw doesn't support it
        ...
```

### SunoProvider

```python
class SunoProvider(BaseMusicProvider):
    def __init__(self, api_key: str, base_url: str) -> None:
        super().__init__("suno", api_key, base_url)

    async def generate(self, lyrics, voice_prompt, *, model=None,
                       reference_audio=None, job_id=None) -> Path:
        if reference_audio:
            await self._health_check(reference_audio)
        task_id = await self._invoke(lyrics, voice_prompt, reference_audio)
        audio_url = await self._poll(task_id)
        mp3_bytes = await self._download(audio_url)
        output_path = Path(settings.OUTPUT_DIR) / (job_id or uuid.uuid4().hex) / "generated.mp3"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(mp3_bytes)
        return output_path
```

### Selection function in `__init__.py`

```python
def _select_music_provider() -> BaseMusicProvider:
    if settings.MUSIC_PROVIDER == "suno":
        if not settings.SUNO_API_KEY or not settings.SUNO_BASE_URL:
            raise MusicGenerationError(
                "SUNO_API_KEY and SUNO_BASE_URL required when MUSIC_PROVIDER=suno"
            )
        return SunoProvider(settings.SUNO_API_KEY, settings.SUNO_BASE_URL)
    return OpenClawProvider(settings.OPENCLAW_TOKEN, settings.OPENCLAW_BASE_URL)
```

### Suno API request/response shapes

**POST /api/v1/generate** (text-to-music):
```json
{
  "prompt": "voice_prompt text",
  "customMode": true,
  "style": "voice_prompt text",
  "title": "",
  "model": "V4_5",
  "lyrics": "..."
}
```

**POST /api/v1/generate** (cover):
```json
{
  "prompt": "voice_prompt text",
  "customMode": true,
  "style": "voice_prompt text",
  "title": "",
  "model": "V4_5",
  "lyrics": "...",
  "reference_audio_url": "https://..."
}
```

**Response** (both): `{ "id": "task-xxx" }`

**GET /api/v1/generate/record-info?taskId=task-xxx**:
```json
{
  "id": "task-xxx",
  "status": "complete" | "failed" | "generating" | "pending",
  "audio_url": "https://...",
  "stream_audio_url": "https://...",
  "image_url": "...",
  "title": "...",
  "tags": "...",
  "duration": 240.0
}
```

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | SunoProvider._invoke | respx mock POST → assert task_id |
| Unit | SunoProvider._poll | respx mock GET (pending→complete→failed) |
| Unit | SunoProvider.generate | respx mock POST+GET+download → assert Path |
| Unit | Cover mode | respx mock HEAD + POST with reference_audio_url |
| Unit | Health check fail | mock HEAD 404 → assert error |
| Unit | OpenClowProvider wraps client | mock OpenClawClient → assert delegation |
| Unit | _select_music_provider | monkeypatch MUSIC_PROVIDER → assert type |
| Integration | generate() with suno | mock SunoProvider → full generate() path |
| Integration | Reference audio upload | upload → assert file exists when suno |
| Integration | Reference audio serving | GET /api/ref-audio/{id} → assert MP3 bytes |

## Migration / Rollout

No migration required. Add env vars: `MUSIC_PROVIDER` defaults to `openclaw` — identical behavior. Suno only activates when explicitly configured.

## Open Questions

- [ ] Need to confirm exact Suno API endpoints (v1 vs v2) and auth header format (Bearer vs x-api-key)
