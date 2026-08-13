# Voice Configuration Specification

## Purpose

Provide a voice selection abstraction layer for music generation. Support male and female Spanish voices in v0 with a documented extension point for future voice cloning (v1+). Map voice selection to Lyria 3 generation parameters.

## Requirements

### RQ-VOI-01: Voice Selection Input

The system MUST accept a `voice` parameter in the generation request with the following valid options:

| Value | Label | Gender |
|-------|-------|--------|
| `male` | Voz masculina | male |
| `female` | Voz femenina | female |
| `es-latino-male` | Español hombre latino | male |
| `es-espana-male` | Español hombre España | male |
| `es-espana-female` | Mujer española | female |
| `es-latina-female` | Mujer latina | female |
| `es-espana-child` | Voz infantil española | child |

If `voice` is omitted, the system SHOULD default to `female`.

#### Scenario: Explicit male voice

- GIVEN a generate request with `voice: "male"`
- WHEN the request is validated
- THEN the system MUST accept the value
- AND pass it to the voice abstraction layer

#### Scenario: Explicit new regional voice

- GIVEN a generate request with `voice: "es-espana-female"`
- WHEN the request is validated
- THEN the system MUST accept the value
- AND pass it to the voice abstraction layer

#### Scenario: Default voice when omitted

- GIVEN a generate request without a `voice` field
- WHEN the request is validated
- THEN the system MUST use `female` as the default

#### Scenario: Unsupported voice value

- GIVEN a generate request with `voice: "duo"`, `children`, or any value not in the registry
- WHEN the request is validated
- THEN the system MUST return a 422 validation error
- AND the error MUST list the supported voice IDs

### RQ-VOI-02: Lyria 3 Prompt Mapping

The system MUST map each abstract voice selection to a distinct Spanish voice descriptor string (`prompt_es`) injected into the music generation `prompt` field. When `reference_song` is present, it MUST be appended as a style modifier.

#### Scenario: Male voice prompt construction

- GIVEN a voice selection of `male` and genre="bachata"
- WHEN the abstraction layer builds the prompt
- THEN the prompt MUST include a Spanish male voice descriptor (e.g. "voz masculina española")
- AND the prompt SHOULD include "cantante masculino"

#### Scenario: Latino male prompt construction

- GIVEN a voice selection of `es-latino-male` and genre="reggaetón"
- WHEN the abstraction layer builds the prompt
- THEN the prompt MUST include a Latino male descriptor (e.g. "voz masculina latina")
- AND the prompt SHOULD include "hombre latinoamericano"

#### Scenario: Female voice prompt construction

- GIVEN a voice selection of `female` and genre="balada"
- WHEN the abstraction layer builds the prompt
- THEN the prompt MUST include a Spanish female voice descriptor (e.g. "voz femenina española")
- AND the prompt SHOULD include "cantante femenina"

#### Scenario: Child voice prompt construction

- GIVEN a voice selection of `es-espana-child`
- WHEN the abstraction layer builds the prompt
- THEN the prompt MUST include a child voice descriptor (e.g. "voz infantil")

### RQ-VOI-03: Extension Point for v1+

The voice abstraction layer SHALL define a documented extension interface for adding new voice types. The interface MUST include:

1. A registry class or dict mapping voice IDs to prompt builders
2. Each voice entry: id, label, gender, prompt_template, language
3. A `VoiceProvider` abstract base class or Protocol for custom implementations

Documentation MUST be in a `README.md` or inline docstring at `app/voice/` module level.

#### Scenario: Adding a new voice type (v1+)

- GIVEN a developer wants to add "celebrity_x" voice
- WHEN they register it in the voice registry with a prompt template
- THEN the system MUST accept "celebrity_x" as a valid voice type without code changes outside the registry
- AND validation MUST treat it as a supported value

#### Scenario: Registry lives in single module

- GIVEN any valid voice request
- WHEN the system resolves the voice mapping
- THEN all voice definitions MUST be in a single registry module
- AND lookups MUST be O(1) from that registry

### RQ-VOI-04: Voice Validation at Startup

The system MUST validate the voice configuration at startup. If the registry is empty or malformed, the system MUST log a fatal error and refuse to start.

#### Scenario: Empty voice registry

- GIVEN a voice registry with no entries
- WHEN the application starts
- THEN it MUST log a fatal error
- AND the application MUST NOT accept requests

#### Scenario: Healthy voice registry

- GIVEN a voice registry with male and female entries defined
- WHEN the application starts
- THEN it MUST log the available voices
- AND the application MUST start normally

### RQ-VOI-05: Reference Song in Prompt Building

The `build_prompt` function MUST accept an optional `reference_song: str | None` parameter. When provided, the reference song style description MUST be appended to the generated prompt.

Before appending, `build_prompt` MUST sanitize `reference_song` with the shared tag sanitizer: safe `"Song - Artist"` patterns MUST be stripped to the song token, and a "no usable reference" result MUST append NO style reference. This generation-time guard covers legacy projects stored before input validation existed.

#### Scenario: Reference song appended

- GIVEN voice="male", genre="bachata", and reference_song="Bachata Rosa - Juan Luis Guerra"
- WHEN `build_prompt` constructs the Lyria 3 prompt
- THEN the prompt MUST include "voz masculina española"
- AND the prompt MUST end with "al estilo de Bachata Rosa" (artist stripped)

#### Scenario: No reference song

- GIVEN voice="female", genre="balada", and reference_song=None
- WHEN `build_prompt` is called
- THEN the prompt MUST NOT contain style references
- AND output MUST match existing prompt behavior

#### Scenario: Artist-only reference produces no style modifier

- GIVEN voice="male", genre="cumbia", and reference_song="Los Palmeras"
- WHEN `build_prompt` is called
- THEN the prompt MUST NOT append any style reference
- AND the prompt MUST still include the voice descriptor

#### Scenario: Legacy stored artist format sanitized at generation

- GIVEN a legacy project stored with reference_song="Bachata Rosa - Juan Luis Guerra"
- WHEN `build_prompt` runs at generation time
- THEN the appended style reference MUST use the sanitized "Bachata Rosa"
- AND no artist token MUST appear in the prompt

### RQ-VOICE-01: Available Voices Endpoint

The system MUST expose `GET /api/voices` returning the full voice registry as an array of `{id, label, gender}` objects. This endpoint MUST be the single source of truth for the frontend voice selector; the frontend MUST NOT hard-code its own voice options.

#### Scenario: Return available voices

- GIVEN a healthy voice registry
- WHEN GET /api/voices is called
- THEN response MUST be 200 with an array of ~7 entries
- AND each entry MUST include `id`, `label`, and `gender`

#### Scenario: Reflects registry exactly

- GIVEN the registry defines `es-latino-male`
- WHEN GET /api/voices is called
- THEN the response MUST include `es-latino-male`
- AND the list MUST exactly match the registry (no drift)

### RQ-VOICE-02: Fail-Fast Voice Validation

The system MUST validate the `voice` field against the voice registry at the API boundary (request validation) and MUST return a 422 error for unknown IDs. Voice validation MUST NOT be deferred to job execution, and MUST NOT let an unknown voice crash a job.

#### Scenario: Unknown voice rejected at request time

- GIVEN a request with `voice: "celebrity_x"`
- WHEN the project create/update or generate request is validated
- THEN response MUST be 422
- AND no job MUST be created

#### Scenario: Legacy duo/children rejected

- GIVEN a request with `voice: "duo"` or `voice: "children"`
- WHEN the request is validated
- THEN response MUST be 422
- AND the error MUST list valid voice IDs

#### Scenario: New valid voice accepted

- GIVEN a request with `voice: "es-latino-male"`
- WHEN the request is validated
- THEN response MUST be accepted
- AND the job MUST run without voice-related failure

## Edge Cases

| Condition | Behavior |
|-----------|----------|
| Voice value has leading/trailing whitespace | Trim before validation |
| Voice value case mismatch ("Male" vs "male") | Case-insensitive comparison |
| Lyria 3 ignores voice prompt (model limitation) | Accept output as-is; log voice guidance was provided |
| Both male and female produce identical output | Accept — Lyria 3 voice control is a best-effort prompt |
| Registry updated at runtime | Not supported in v0 — requires restart |

## Dependencies

- **Internal**: `music-generation` — consumes the voice prompt from this module
- **Design**: VoiceProvider interface to be defined in design phase
- **Future**: Voice cloning service API (v1+) — will plug into the extension point

## Acceptance Criteria

- [ ] voice="male" and voice="female" accepted as valid
- [ ] Missing voice defaults to "female"
- [ ] Unsupported voice returns 422 with valid options list
- [ ] Male voice prompt includes Spanish male descriptor
- [ ] Female voice prompt includes Spanish female descriptor
- [ ] Voice registry has documented extension interface
- [ ] Empty registry prevents app startup
- [ ] Genre and voice combine into coherent Lyria 3 prompt
