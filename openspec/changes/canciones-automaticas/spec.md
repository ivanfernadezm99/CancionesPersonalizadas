# Change Spec: canciones-automaticas

> Greenfield project — AI-powered personalized romantic song generator in Spanish.
> All 5 capabilities are NEW (no existing specs to delta against).

## Capability Map

| Capability | Spec File | Role in Pipeline |
|------------|-----------|-----------------|
| `lyrics-generation` | `openspec/specs/lyrics-generation/spec.md` | LLM Spanish lyrics from user input |
| `music-generation` | `openspec/specs/music-generation/spec.md` | Lyria 3 async generation + duration extension |
| `audio-streaming` | `openspec/specs/audio-streaming/spec.md` | Freemium audio preview endpoint |
| `voice-configuration` | `openspec/specs/voice-configuration/spec.md` | Male/female voice abstraction for Lyria 3 |
| `job-orchestration` | `openspec/specs/job-orchestration/spec.md` | Background tasks, SQLite, status polling |

## Pipeline Flow

```
POST /api/generate
  ↓
[job-orchestration] creates job (status: queued)
  ↓
[lyrics-generation] Multi-LLM → structured Spanish lyrics
  ↓
[music-generation] OpenClaw music_generate → async poll → MP3
  ↓
[music-generation] Duration extension (2-3 min target)
  ↓
[job-orchestration] marks complete (status: complete)
  ↓
GET /api/stream/{id} → [audio-streaming] → audio/mpeg
```

## Cross-Cutting Constraints

| Constraint | Applies To | Enforcement |
|------------|-----------|-------------|
| All lyrics in Spanish | lyrics-generation | Validation in output schema |
| Async only (no sync generation) | job-orchestration, music-generation | Architecture decision |
| Freemium — no download in v0 | audio-streaming | No download endpoint, no static file serving |
| TDD — tests before code | ALL | pytest, strict mode |
| Voice is best-effort prompt | voice-configuration, music-generation | Cannot guarantee Lyria 3 honors it |

## Spec Inventory

| # | Requirement | Domain | Priority | Testable |
|---|-------------|--------|----------|----------|
| RQ-LYR-01 | Lyrics Input Schema | lyrics-generation | P0 | ✅ |
| RQ-LYR-02 | Output Structure | lyrics-generation | P0 | ✅ |
| RQ-LYR-03 | Multi-Provider Selection | lyrics-generation | P1 | ✅ |
| RQ-LYR-04 | Spanish Romantic Quality | lyrics-generation | P1 | ✅ |
| RQ-LYR-05 | Provider Key Validation | lyrics-generation | P0 | ✅ |
| RQ-MUS-01 | OpenClaw Invocation | music-generation | P0 | ✅ |
| RQ-MUS-02 | Async Polling | music-generation | P0 | ✅ |
| RQ-MUS-03 | Duration Extension | music-generation | P1 | ✅ |
| RQ-MUS-04 | Output Storage | music-generation | P0 | ✅ |
| RQ-STR-01 | Stream Endpoint | audio-streaming | P0 | ✅ |
| RQ-STR-02 | Range Request Support | audio-streaming | P1 | ✅ |
| RQ-STR-03 | Freemium Preview Restriction | audio-streaming | P0 | ✅ |
| RQ-STR-04 | Streaming Performance | audio-streaming | P1 | ✅ |
| RQ-VOI-01 | Voice Selection Input | voice-configuration | P0 | ✅ |
| RQ-VOI-02 | Lyria 3 Prompt Mapping | voice-configuration | P0 | ✅ |
| RQ-VOI-03 | Extension Point for v1+ | voice-configuration | P2 | ✅ |
| RQ-VOI-04 | Voice Validation at Startup | voice-configuration | P0 | ✅ |
| RQ-JOB-01 | Generate Endpoint | job-orchestration | P0 | ✅ |
| RQ-JOB-02 | Status Endpoint | job-orchestration | P0 | ✅ |
| RQ-JOB-03 | Status State Machine | job-orchestration | P0 | ✅ |
| RQ-JOB-04 | SQLite Persistence | job-orchestration | P0 | ✅ |
| RQ-JOB-05 | Job Cleanup | job-orchestration | P1 | ✅ |
| RQ-JOB-06 | Error Handling and Retries | job-orchestration | P1 | ✅ |

## Key Decisions

1. **Lyrics generation**: multi-provider with cascade fallback; test all, pick best quality
2. **Music generation**: OpenClaw gateway with async polling (5s interval, 5min timeout)
3. **Duration extension**: smart crossfade loop as primary, simple loop as fallback
4. **Voice**: prompt-based only (Lyria 3 limitation); abstraction layer for future cloning
5. **Job store**: SQLite with strict state machine; WAL mode for concurrent reads
6. **Streaming**: FastAPI StreamingResponse with Range support — no download in v0
7. **Rate limiting**: max 5 concurrent queued/processing jobs; 429 beyond that

## Risks and Mitigations

| Risk | Likelihood | Mitigation | Spec Reference |
|------|-----------|------------|---------------|
| Lyria 3 max duration hard-limited | High | pydub looping/stitching fallback | RQ-MUS-03 |
| Voice selection unsupported by Lyria 3 | Medium | Abstraction layer; prompt-based only | RQ-VOI-02 |
| Spanish lyrics quality varies by LLM | Medium | Multi-provider test harness | RQ-LYR-03 |
| Duration extension degrades audio quality | Medium | Quality check; return original if bad | RQ-MUS-03 |
| OpenClaw single point of failure | Low | Retries + clear error messages | RQ-MUS-01, RQ-JOB-06 |

## Acceptance Criteria (Change-Level)

- [ ] POST /api/generate: 202 with job_id (5s max response time)
- [ ] GET /api/status/{id}: queued → processing → complete/failed
- [ ] GET /api/stream/{id}: playable MP3 audio with Range support
- [ ] Spanish lyrics ≥7/10 native quality for 3 test scenarios
- [ ] Generated song reaches 2-3 min (via extension if needed)
- [ ] Voice selection switches between male and female samples
- [ ] All endpoints covered by pytest integration tests
