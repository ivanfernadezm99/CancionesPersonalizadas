# Tag Sanitization Specification

## Purpose

Shared sanitizer that removes artist names from `reference_song` before any value reaches Suno's tags. Used at three layers — input validation (Pydantic 422), generation time (`build_prompt` + lyrics builder, covering legacy projects and both worker paths), and error translation as a safety net for opaque Suno matching. Mirrored client-side.

## Requirements

### RQ-TAG-01: Strip Heuristic

The system MUST strip artist tokens from `reference_song` for the safe patterns `"Song - Artist"`, `"Song de Artist"`, and `"Song (Artist)"`, keeping only the song token. Matching MUST be case-insensitive and whitespace-trimmed.

| Input | Output |
|-------|--------|
| `Bachata Rosa - Juan Luis Guerra` | `Bachata Rosa` |
| `Bailando de Enrique Iglesias` | `Bailando` |
| `La Bamba (Los Lobos)` | `La Bamba` |
| `Despacito` | `Despacito` (unchanged) |

#### Scenario: Dash-separated song artist

- GIVEN `reference_song="Bachata Rosa - Juan Luis Guerra"`
- WHEN the sanitizer runs
- THEN the result MUST be `"Bachata Rosa"`

#### Scenario: de-separated song artist

- GIVEN `reference_song="Bailando de Enrique Iglesias"`
- WHEN the sanitizer runs
- THEN the result MUST be `"Bailando"`

#### Scenario: Parenthesized artist

- GIVEN `reference_song="La Bamba (Los Lobos)"`
- WHEN the sanitizer runs
- THEN the result MUST be `"La Bamba"`

#### Scenario: Song-only input untouched

- GIVEN `reference_song="Despacito"`
- WHEN the sanitizer runs
- THEN the result MUST be `"Despacito"` unchanged

### RQ-TAG-02: Curated Blocklist

The sanitizer MUST include a curated blocklist of popular Argentine artists (including `Los Palmeras` and `La Mona Jiménez`). Any `reference_song` matching a blocklist entry MUST be treated as artist-only, case-insensitively and as a substring.

#### Scenario: Exact blocklist match

- GIVEN `reference_song="Los Palmeras"`
- WHEN the sanitizer runs
- THEN the result MUST indicate no usable reference

#### Scenario: Case-insensitive blocklist match

- GIVEN `reference_song="los palmeras"`
- WHEN the sanitizer runs
- THEN the result MUST indicate no usable reference

#### Scenario: Blocklist name embedded in longer input

- GIVEN `reference_song="Grupo Los Palmeras"`
- WHEN the sanitizer runs
- THEN the result MUST indicate no usable reference

### RQ-TAG-03: No Usable Reference Signal

When stripping leaves no song token (artist-only input), the sanitizer MUST return a "no usable reference" result rather than a partial artist name.

#### Scenario: Artist-only after strip

- GIVEN `reference_song="Juan Luis Guerra"`
- WHEN the sanitizer runs
- THEN the result MUST indicate no usable reference

#### Scenario: Empty input

- GIVEN `reference_song=""` or `None`
- WHEN the sanitizer runs
- THEN the result MUST indicate no usable reference

### RQ-TAG-04: Layered Application

The sanitizer MUST be applied at input validation (422 on no-usable-reference), generation time (both worker paths, covering legacy stored projects), and by the Suno error translator. The frontend MUST mirror the strip heuristic and MUST NOT teach the rejected `"Song - Artist"` format in hint text.

#### Scenario: Input-time rejection

- GIVEN `reference_song="Los Palmeras"` on POST /api/projects
- WHEN the request is validated
- THEN response MUST be 422 with a friendly Spanish message

#### Scenario: Generation-time guard for legacy projects

- GIVEN a stored project with `reference_song="Bachata Rosa - Juan Luis Guerra"` created before the fix
- WHEN `build_prompt` or the lyrics builder runs
- THEN the sanitized song token `"Bachata Rosa"` MUST be used in the prompt

#### Scenario: Error translation safety net

- GIVEN a Suno rejection naming an artist that local heuristics missed
- WHEN the job fails
- THEN the job error MUST contain the friendly Spanish translation

## Dependencies

- **Internal**: consumed by `song-projects` (input validation), `voice-configuration` (`build_prompt`), `lyrics-generation` (lyrics builder), `suno-provider` (error translation), `job-orchestration` (both worker paths).
- **Frontend**: mirrored client-side in POSCuentasCorrientes (`reference-song.ts`).