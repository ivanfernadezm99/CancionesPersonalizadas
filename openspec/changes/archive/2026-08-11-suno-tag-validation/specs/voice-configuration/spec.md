# Delta for Voice Configuration

## MODIFIED Requirements

### RQ-VOI-05: Reference Song in Prompt Building

The `build_prompt` function MUST accept an optional `reference_song: str | None` parameter. When provided, the reference song style description MUST be appended to the generated prompt.

Before appending, `build_prompt` MUST sanitize `reference_song` with the shared tag sanitizer: safe `"Song - Artist"` patterns MUST be stripped to the song token, and a "no usable reference" result MUST append NO style reference. This generation-time guard covers legacy projects stored before input validation existed.
(Previously: `reference_song` was injected verbatim as `Inspirada en el estilo de {reference_song}.`)

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
