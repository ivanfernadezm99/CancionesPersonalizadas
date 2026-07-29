# Delta for music-generation

## MODIFIED Requirements

### RQ-MUS-05: Model Selection by Job Type

OpenClaw: `lyria-3-clip-preview` for previews, clip-chaining or pro-preview for finals. Suno: uses V4/V4_5/V4_5ALL/V5 — no clip-chaining.
(Previously: unconditional OpenClaw model selection)

| Scenario | GIVEN | WHEN | THEN |
|----------|-------|------|------|
| OpenClaw preview | preview job, OpenClaw | music_generate invoked | model=`lyria-3-clip-preview` |
| OpenClaw final chained | final, `chaining_enabled`, OpenClaw | generation starts | clip-chain, NOT pro-preview |
| OpenClaw final fallback | final, no chaining, OpenClaw | starts | use `lyria-3-pro-preview` |
| OpenClaw existing gen | POST /api/generate, OpenClaw | invoked | model=`lyria-3-clip-preview` |

### RQ-MUS-06: Reference Song in Prompt

OpenClaw: include ref as "al estilo de {song}". Suno: handled via Cover mode (RQ-SUNO-02).
(Previously: always appended unconditionally)

| Scenario | GIVEN | WHEN | THEN |
|----------|-------|------|------|
| OpenClaw with ref | `reference_song` set, OpenClaw | prompt built | include "al estilo de {song}" |
| OpenClaw no ref | no `reference_song`, OpenClaw | prompt built | no style reference added |

## ADDED Requirements

### RQ-MUS-07: Provider Abstraction

Implement `BaseMusicProvider(ABC)` with `async generate(lyrics, voice_prompt, *, reference_audio=None) -> Path`.

- GIVEN BaseMusicProvider subclass WHEN instantiated THEN MUST implement `generate()`
- GIVEN subclass without `generate()` WHEN instantiated THEN TypeError raised

### RQ-MUS-08: Config-Level Selection

`MUSIC_PROVIDER` env var (`openclaw`|`suno`, default `openclaw`). `app/music/__init__.py` delegates to configured provider. `openclaw` = pre-change behavior.

- GIVEN `MUSIC_PROVIDER=openclaw` WHEN `generate()` called THEN behavior matches pre-abstraction
- GIVEN invalid provider WHEN Settings init THEN config error raised

### RQ-MUS-09: OpenClawProvider Wrapper

Wraps `OpenClawClient` without modifying it. Behavior identical to pre-abstraction.

- GIVEN `OpenClawProvider` WHEN `generate()` called THEN client methods called with same params AND Path matches pre-abstraction
