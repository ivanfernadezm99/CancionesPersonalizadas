# Proposal: Suno AI Music Provider Adapter

## Intent

Add Suno AI as a second music generation provider alongside Google Lyria 3, using the same provider abstraction pattern already established for lyrics. Suno's "Upload & Cover" mode preserves reference audio style while applying new lyrics — the key new capability for melody/style transfer.

## Scope

### In Scope
- `BaseMusicProvider` ABC in `app/music/providers.py` matching lyrics `BaseProvider` pattern
- `OpenClawProvider` — wraps existing `OpenClawClient` (additive, no changes to existing code)
- `SunoProvider` — new async client with generate (text-to-music) and cover (reference audio + lyrics)
- Config-level provider selection via `MUSIC_PROVIDER` env var (`openclaw` | `suno`)
- Reference audio storage for Suno Cover mode (design decision deferred)
- `app/music/__init__.py` refactor: `generate()` delegates to configured provider; existing signature preserved
- Suno generates full-length songs (~4 min) — no clip chaining needed

### Out of Scope
- Provider cascade/fallback (generation is too expensive — config-level only)
- Modifying existing OpenClaw code (additive change only)
- Frontend provider selection UI
- Suno webhook callbacks (v1 uses polling only)
- Suno account provisioning or API key procurement

## Capabilities

> This section is the CONTRACT between proposal and specs phases.

### New Capabilities
- `suno-provider`: Suno AI music generation — text-to-music and cover (reference audio + lyrics) via Suno REST API, with async polling for completion

### Modified Capabilities
- `music-generation`: provider abstraction via `BaseMusicProvider` ABC; OpenClaw wrapped as `OpenClawProvider`; Suno added as second provider; `generate()` selects provider by config
- `song-projects`: reference audio storage concern for Cover mode; `chaining_enabled` toggle is irrelevant when provider=suno

## Approach

Mirror `app/lyrics/providers.py`. `BaseMusicProvider(ABC)` with `async generate(lyrics, voice_prompt, *, reference_audio=None) -> Path`. `OpenClawProvider` delegates to existing `OpenClawClient` (invoke → poll → download). `SunoProvider` implements Suno REST API (invoke → poll → download). Config via `MUSIC_PROVIDER` in `Settings`. `app/music/__init__.py` selects provider at call time from config. No cascade — generation cost prohibits fallback.

Suno Cover requires reference audio at a public URL. Options: serve via existing stream endpoint or upload to S3. Decision deferred to design phase.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `app/music/providers.py` | New | ABC + OpenClawProvider + SunoProvider |
| `app/music/__init__.py` | Modified | Delegate `generate()` to configured provider |
| `app/config.py` | Modified | Add `MUSIC_PROVIDER`, `SUNO_API_KEY`, `SUNO_BASE_URL` |
| `music-generation` spec | Modified | Delta for provider abstraction |
| `song-projects` spec | Modified | Delta for reference audio / cover mode |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Suno API rate limits | Med | Queue + configurable polling backoff |
| Reference audio URL unavailable | Low | Health-check before starting cover job |
| Suno API key exposure | Low | Env var management + rotation support |

## Rollback Plan

Set `MUSIC_PROVIDER=openclaw` (default). Suno code path is never entered. All existing OpenClaw codepaths untouched. Entirely additive change.

## Dependencies

- Suno API access (base URL + API key)
- Reference audio public URL (local serving or S3 — design decision)

## Success Criteria

- [ ] `MUSIC_PROVIDER=suno` generates a valid MP3 via Suno API
- [ ] Suno Cover produces a song from reference audio URL + new lyrics
- [ ] `MUSIC_PROVIDER=openclaw` behaves identically to pre-change
- [ ] All existing tests pass without modification
