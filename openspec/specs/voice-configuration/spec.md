# Voice Configuration Specification

## Purpose

Provide a voice selection abstraction layer for music generation. Support male and female Spanish voices in v0 with a documented extension point for future voice cloning (v1+). Map voice selection to Lyria 3 generation parameters.

## Requirements

### RQ-VOI-01: Voice Selection Input

The system MUST accept a `voice` parameter in the generation request with the following valid options:

| Value | Description |
|-------|-------------|
| `male` | Male Spanish voice |
| `female` | Female Spanish voice |

If `voice` is omitted, the system SHOULD default to `female`.

#### Scenario: Explicit male voice

- GIVEN a generate request with `voice: "male"`
- WHEN the request is validated
- THEN the system MUST accept the value
- AND pass it to the voice abstraction layer

#### Scenario: Explicit female voice

- GIVEN a generate request with `voice: "female"`
- WHEN the request is validated
- THEN the system MUST accept the value
- AND pass it to the voice abstraction layer

#### Scenario: Default voice when omitted

- GIVEN a generate request without a `voice` field
- WHEN the request is validated
- THEN the system MUST use `female` as the default

#### Scenario: Unsupported voice value

- GIVEN a generate request with `voice: "celebrity_x"` or any unsupported value
- WHEN the request is validated
- THEN the system MUST return a 422 validation error
- AND the error MUST list the supported values (male, female)

### RQ-VOI-02: Lyria 3 Prompt Mapping

The system MUST map the abstract voice selection to concrete OpenClaw prompt parameters. The mapping layer MUST produce a voice prompt string injected into the music generation `prompt` field. When `reference_song` is present, it MUST be appended as a style modifier.

#### Scenario: Male voice prompt construction

- GIVEN a voice selection of `male` and genre="bachata"
- WHEN the abstraction layer builds the prompt
- THEN the prompt MUST include a Spanish male voice descriptor (e.g. "voz masculina española")
- AND the prompt SHOULD include "cantante masculino"

#### Scenario: Female voice prompt construction

- GIVEN a voice selection of `female` and genre="balada"
- WHEN the abstraction layer builds the prompt
- THEN the prompt MUST include a Spanish female voice descriptor (e.g. "voz femenina española")
- AND the prompt SHOULD include "cantante femenina"

#### Scenario: Genre+voice prompt combination

- GIVEN voice="male" and genre="reggaetón"
- WHEN the abstraction layer builds the prompt
- THEN the final prompt MUST include both the voice descriptor and genre-appropriate style
- AND the prompt MUST be in natural language suitable for Lyria 3

#### Scenario: Male voice with reference song

- GIVEN voice="male", genre="bachata", reference_song="Bachata Rosa"
- WHEN the abstraction layer builds the prompt
- THEN the prompt MUST include "voz masculina española"
- AND the prompt MUST include reference song style guidance

#### Scenario: Female voice without reference

- GIVEN voice="female", genre="balada", no reference_song
- WHEN the abstraction layer builds the prompt
- THEN the prompt MUST include "voz femenina española"
- AND the prompt MUST NOT include any style reference

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

#### Scenario: Reference song appended

- GIVEN voice="male", genre="bachata", and reference_song="Bachata Rosa - Juan Luis Guerra"
- WHEN `build_prompt` constructs the Lyria 3 prompt
- THEN the prompt MUST include "voz masculina española"
- AND the prompt MUST end with "al estilo de Bachata Rosa - Juan Luis Guerra"

#### Scenario: No reference song

- GIVEN voice="female", genre="balada", and reference_song=None
- WHEN `build_prompt` is called
- THEN the prompt MUST NOT contain style references
- AND output MUST match existing prompt behavior

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
