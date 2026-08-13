# Lyrics Generation Specification

## Purpose

Generate Spanish romantic song lyrics from user-provided context using a multi-provider LLM pipeline. Produce structured, poetically consistent lyrics (verses + chorus) optimized for Lyria 3 music generation input.

## Requirements

### RQ-LYR-01: Lyrics Input Schema

The system MUST accept the following input fields for lyric generation:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `recipient` | string | Yes | Recipient name (e.g. "María") |
| `relationship` | string | Yes | Relationship type (pareja, amigo, familiar, etc.) |
| `occasion` | string | Yes | Occasion or celebration (cumpleaños, aniversario, etc.) |
| `genre` | string | Yes | Musical genre (balada, bachata, reggaetón, etc.) |
| `mood` | string | Yes | Emotional tone (romántica, festiva, agradecida, etc.) |
| `story` | string | No | Free-text anecdotes, memories, feelings (max 1000 chars) |

#### Scenario: Happy path with all fields

- GIVEN valid input with recipient="María", relationship="pareja", occasion="aniversario", genre="bachata", mood="romántica", and story="Nuestro primer viaje a la playa"
- WHEN the system generates lyrics
- THEN the output MUST include at least 2 verses and 1 chorus
- AND the lyrics MUST include the recipient's name "María"

#### Scenario: Missing optional story field

- GIVEN valid input without the story field
- WHEN the system generates lyrics
- THEN it MUST still produce complete lyrics with correct structure
- AND the content MUST be based solely on the provided fields

#### Scenario: Invalid relationship type

- GIVEN input with relationship="unknown_xyz"
- WHEN the system validates input
- THEN it MUST return a 422 validation error
- AND the error message MUST list valid relationship options

### RQ-LYR-02: Output Structure

The system SHALL output lyrics in a consistent structured format:

```json
{
  "verses": [
    {"number": 1, "lines": ["line1", "line2", "line3", "line4"]},
    {"number": 2, "lines": ["line1", "line2", "line3", "line4"]}
  ],
  "chorus": {"lines": ["line1", "line2", "line3", "line4"]},
  "bridge": {"lines": ["line1", "line2"]},
  "language": "es",
  "title_suggestion": "María, Mi Amor"
}
```

- 2-3 verses (4 lines each), 1 chorus (4 lines), optional bridge (2-4 lines)
- ALL lines MUST be in Spanish
- Lines MUST rhyme or follow rhythmic structure appropriate to the genre

#### Scenario: Structured output parsing

- GIVEN a successful lyrics generation call
- WHEN the system returns the result
- THEN the response MUST conform to the JSON structure above
- AND each line MUST be non-empty Spanish text
- AND the language field MUST be "es"

#### Scenario: Minimum content guarantee

- GIVEN any valid input
- WHEN lyrics are generated
- THEN total lines MUST be >= 10 (2 verses × 4 + chorus × 4 - overlap)
- AND each line MUST be between 10 and 100 characters

### RQ-LYR-03: Multi-Provider Selection

The system SHOULD test multiple LLM providers and pick the best result per quality heuristics:

| Provider | Model | Status |
|----------|-------|--------|
| OpenAI | GPT-4o | Must have API key configured |
| Google | Gemini | Must have API key configured |
| OpenRouter | GPT-4o / Gemini | Fallback if direct providers fail |

Selection logic: prefer highest quality by heuristic (rhyme density, line count, recipient name inclusion). If a provider fails, fall through to the next.

#### Scenario: First provider succeeds

- GIVEN OpenAI GPT-4o returns valid lyrics in < 10s
- WHEN the multi-provider pipeline runs
- THEN the result from OpenAI is used
- AND no fallback providers are called

#### Scenario: First provider fails, second succeeds

- GIVEN OpenAI returns an error (timeout or 5xx)
- WHEN the multi-provider pipeline runs
- THEN it MUST fall back to Google Gemini
- AND the final result MUST come from Gemini

#### Scenario: All providers fail

- GIVEN all three providers return errors
- WHEN the multi-provider pipeline runs
- THEN the system MUST return a 503 error
- AND the error message MUST indicate "all LLM providers unavailable"

### RQ-LYR-04: Spanish Romantic Quality

The system SHOULD apply prompt engineering optimized for Spanish romantic poetry:

- Instruct the model to use natural Spanish (not Spanglish, not overly formal)
- Encourage genre-appropriate rhyme schemes (asonante for ballads, consonante for bachata)
- Include recipient name naturally in at least the chorus
- Use genre-typical vocabulary and rhythm hints
- When `reference_song` is provided, instruct the model to match that song's style, rhythm, and thematic elements

When `reference_song` is provided, the lyrics prompt MUST use the sanitized song token (artist stripped via the shared tag sanitizer) so the LLM does not echo an artist name into the lyrics that reach Suno.

#### Scenario: Genre-appropriate vocabulary

- GIVEN genre="reggaetón"
- WHEN lyrics are generated
- THEN the output SHOULD use informal, rhythmic Spanish with shorter lines
- AND the rhyme scheme SHOULD fit reggaetón flow patterns

#### Scenario: Recipient name integration

- GIVEN recipient="Carlos"
- WHEN lyrics are generated
- THEN the recipient name "Carlos" MUST appear in the chorus
- AND the name SHOULD appear at least once in the verses

#### Scenario: Reference song overrides genre defaults

- GIVEN reference_song="El Amor - José José" and genre="balada romántica"
- WHEN the prompt includes the reference
- THEN lyrics SHOULD match the romantic ballad style of the reference
- AND the sanitized song token "El Amor" MUST appear in the prompt
- AND the artist "José José" MUST NOT appear in the prompt

#### Scenario: Artist-only reference yields no style guidance

- GIVEN reference_song="Los Palmeras"
- WHEN the lyrics prompt is constructed
- THEN the prompt MUST NOT include style guidance for the reference
- AND lyrics MUST be generated from genre/mood alone

### RQ-LYR-05: Provider Key Validation

The system MUST validate that at least one LLM provider API key is configured at startup. If none are configured, the /api/generate endpoint MUST return 503 with a clear setup error.

#### Scenario: No API keys configured

- GIVEN no LLM provider keys are set (OPENAI_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY all empty)
- WHEN the application starts
- THEN the system MUST log a fatal error
- AND the /api/generate endpoint MUST return 503

#### Scenario: Partial key configuration

- GIVEN only OPENAI_API_KEY is set, others are empty
- WHEN the system starts
- THEN it MUST log a warning about missing Gemini and OpenRouter keys
- BUT it MUST still accept /api/generate requests
- AND only attempt OpenAI for lyrics generation

### RQ-LYR-06: Reference Song Influence

The system MUST accept an optional `reference_song` parameter in the lyrics generation context (from project settings). When provided, the LLM prompt MUST include style/melody guidance referencing that song.

The reference used in the prompt MUST be the sanitized song token produced by the shared tag sanitizer. A "no usable reference" result MUST NOT inject any reference guidance.

#### Scenario: Reference song in lyrics prompt

- GIVEN a project with reference_song="Bachata Rosa - Juan Luis Guerra"
- WHEN the lyrics prompt is constructed
- THEN the prompt MUST include "al estilo de Bachata Rosa" (artist stripped)
- AND the output SHOULD reflect bachata romantic structure

#### Scenario: No reference song

- GIVEN lyrics generation without reference_song
- WHEN the prompt is constructed
- THEN the prompt MUST NOT include style references
- AND behavior MUST match existing lyrics generation

#### Scenario: Artist-only reference in legacy project

- GIVEN a legacy project with stored reference_song="La Mona Jiménez"
- WHEN the lyrics prompt is constructed
- THEN the prompt MUST NOT include the artist name
- AND no style reference guidance MUST be added

### RQ-LYR-07: Idea Seed in Lyrics Prompt

The lyrics generation MUST accept an optional `idea` input and MUST include it as a thematic seed in the LLM prompt alongside the accumulated `story` fragments. When `idea` is absent, generation MUST behave exactly as today.

#### Scenario: Idea included in prompt

- GIVEN lyrics generation with `idea="agradecer a mi madre"`
- WHEN the prompt is constructed
- THEN the prompt MUST include the `idea` text as thematic guidance
- AND the output SHOULD reflect the idea's theme

#### Scenario: No idea, current behavior

- GIVEN lyrics generation without `idea`
- WHEN the prompt is constructed
- THEN the prompt MUST NOT include idea guidance
- AND output MUST match existing generation

## Edge Cases

| Condition | Behavior |
|-----------|----------|
| Story exceeds 1000 chars | Truncate to 1000 with warning in response metadata |
| Recipient name > 50 chars | Return 422 validation error |
| Genre not in supported list | Return 422 with list of supported genres |
| LLM returns malformed JSON (no structured output) | Retry once with stricter prompt; if fails again, return 502 |
| Lyrics fail rhyme/vibe self-check | Re-generate with different provider; if all fail, return result with quality warning |
| Empty story + minimal fields | Generate generic romantic lyrics based on genre and mood only |
| Special characters in recipient (accents, ñ) | Preserve in output — Spanish orthography is required |

## Dependencies

- **External**: OpenAI API key, Google Gemini API key, OpenRouter API key (≥1 required)
- **Internal**: `job-orchestration` (calls lyrics generation as pipeline step)
- **Internal**: `voice-configuration` (voice type may influence pronoun gender in lyrics)

## Acceptance Criteria

- [ ] All input fields validated with clear 422 errors for invalid values
- [ ] Output structure matches the JSON schema exactly
- [ ] Spanish text: no English lines, no Spanglish (except proper names)
- [ ] Provider fallback works: A → B → C cascade
- [ ] Lyrics always include recipient name in chorus
- [ ] ≥10 lines per generation
- [ ] Each line between 10-100 chars
- [ ] All providers produce at least 2 verses + 1 chorus
