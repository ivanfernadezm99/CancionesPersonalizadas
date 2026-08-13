# Lyrics Autodraft Specification

## Purpose

Let users seed a project with a free-text "idea" and generate editable draft lyrics in one click, reusing the existing multi-provider lyrics pipeline. The draft fills the fragments editor for review before preview generation.

## Requirements

### RQ-DRAFT-01: Lyrics Draft Endpoint

The system MUST expose `POST /api/projects/{id}/lyrics-draft` that generates editable draft lyrics for the project and returns the structured result. It MUST combine the project's `recipient`, accumulated `story` fragments, and `idea`.

#### Scenario: Happy path draft

- GIVEN a draft project with fragments and an `idea`
- WHEN POST /api/projects/{id}/lyrics-draft is called
- THEN response MUST be 200 with a structured lyrics object (verses/chorus)
- AND the draft MUST include the recipient name

#### Scenario: Project not found

- GIVEN a non-existent project_id
- WHEN POST /api/projects/{id}/lyrics-draft is called
- THEN response MUST be 404

#### Scenario: All LLM providers unavailable

- GIVEN all configured LLM providers fail
- WHEN POST /api/projects/{id}/lyrics-draft is called
- THEN response MUST be 503
- AND the error MUST indicate "all LLM providers unavailable"

### RQ-DRAFT-02: Idea Seed Integration

When the project has an `idea`, draft generation MUST use it as the primary thematic seed, combined with the accumulated story fragments. When no `idea` is present, the draft MUST generate from fragments alone.

#### Scenario: Idea drives draft

- GIVEN a project with idea="canción de agradecimiento por mi hija"
- WHEN a draft is generated
- THEN the returned lyrics MUST reflect the gratitude theme
- AND the idea text MUST be included in the LLM prompt

#### Scenario: No idea, fragments only

- GIVEN a project with fragments but no `idea`
- WHEN a draft is generated
- THEN the returned lyrics MUST be based on the fragments alone

### RQ-DRAFT-03: Draft Output Structure

The draft MUST conform to the existing lyrics output schema (verses, chorus, optional bridge, `language="es"`). Each line MUST be non-empty Spanish text, and total lines MUST be >= 10.

#### Scenario: Conforms to schema

- GIVEN a successful draft generation
- WHEN the result is returned
- THEN the response MUST match the verses/chorus JSON structure
- AND `language` MUST be "es"
- AND total lines MUST be >= 10

### RQ-DRAFT-04: Frontend Autodraft Flow

The frontend MUST provide an "idea" textarea and an "Autogenerar letra" button on the create/edit form. On success, the returned draft MUST populate the fragments editor via the existing fragments replace endpoint. While generating, the button MUST show a loading state and MUST NOT double-submit.

#### Scenario: Draft fills fragments editor

- GIVEN a user typed an idea and clicks "Autogenerar letra"
- WHEN the draft endpoint resolves successfully
- THEN the fragments editor MUST be filled with the generated verses/chorus
- AND the user MUST be able to edit them before preview

#### Scenario: Generation failure shows error

- GIVEN the draft endpoint returns 503
- WHEN the user clicks "Autogenerar letra"
- THEN the button MUST stop loading
- AND an error message MUST be shown without clearing existing fragments
