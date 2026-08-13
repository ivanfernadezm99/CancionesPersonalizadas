# Delta for Lyrics Generation

## MODIFIED Requirements

### RQ-LYR-04: Spanish Romantic Quality

The system SHOULD apply prompt engineering optimized for Spanish romantic poetry:

- Instruct the model to use natural Spanish (not Spanglish, not overly formal)
- Encourage genre-appropriate rhyme schemes (asonante for ballads, consonante for bachata)
- Include recipient name naturally in at least the chorus
- Use genre-typical vocabulary and rhythm hints
- When `reference_song` is provided, instruct the model to match that song's style, rhythm, and thematic elements

When `reference_song` is provided, the lyrics prompt MUST use the sanitized song token (artist stripped via the shared tag sanitizer) so the LLM does not echo an artist name into the lyrics that reach Suno.
(Previously: the raw `reference_song` was used verbatim in the prompt, allowing the LLM to echo artist names.)

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

### RQ-LYR-06: Reference Song Influence

The system MUST accept an optional `reference_song` parameter in the lyrics generation context (from project settings). When provided, the LLM prompt MUST include style/melody guidance referencing that song.

The reference used in the prompt MUST be the sanitized song token produced by the shared tag sanitizer. A "no usable reference" result MUST NOT inject any reference guidance.
(Previously: the raw `reference_song` value was injected verbatim as `al estilo de {reference_song}`.)

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
