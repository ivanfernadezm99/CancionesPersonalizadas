# Delta for Song Projects

## ADDED Requirements

### RQ-PRJ-09: Asynchronous Preview UI Re-render

The preview UI MUST re-render the template whenever async subscription callbacks (initial project load and job-status polling) mutate render state (`project`, `loading`, `streamUrl`). This MUST hold under zoneless change detection; polling/spinner state MUST reflect real subscription outcomes. (Scope: `canciones-personalizadas/preview`, plus defensive audit of `download`/`create`.)

#### Scenario: Existing complete preview renders player without regeneration

- GIVEN a stored project whose latest preview job has `status: complete`
- WHEN the preview page loads and the initial project subscription resolves
- THEN the template MUST render the sample player showing the preview stream URL
- AND MUST NOT re-queue or regenerate the preview
- AND `loading` MUST become `false`

#### Scenario: Queued preview shows spinner then player on completion

- GIVEN a project with a `queued`/`processing` preview job for the first visit
- WHEN the page loads
- THEN the template MUST show a "Generating preview…" spinner (`loading: true`)
- WHEN the polling subscription observes the job transition to `complete`
- THEN the template MUST swap the spinner for the player within the same change detection cycle
- AND `loading` MUST become `false` and `streamUrl` MUST be set

#### Scenario: Subscription error updates the view

- GIVEN a project whose initial load or poll fails
- WHEN the `error` handler runs and mutates state
- THEN the template MUST reflect the error state (no stale spinner)
- AND the UI MUST offer retry/back navigation

#### Scenario: Defensive CDR across preview/download/create async handlers

- GIVEN any in-subscription field mutation in the `preview`, `download`, or `create` components
- WHEN the subscription callback completes synchronously
- THEN the affected template region MUST re-render within the same change-detection cycle
- AND the component MUST NOT rely on data that remains stale under zoneless change detection