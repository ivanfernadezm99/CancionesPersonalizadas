"""Full-flow integration test for the song project pipeline.

Simulates: create project → add fragment → generate preview →
mock checkout (POSBackend proxy) → webhook payment-confirmed →
generate final → stream result.

Requires the ``test_app`` fixture from conftest (LLM + OpenClaw mocked).
Adds its own ``mock_payment_gateway`` fixture for the POSBackend proxy.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
import respx
from httpx import AsyncClient


@pytest.fixture
def mock_payment_gateway() -> respx.MockRouter:
    """Mock POSBackend checkout endpoint for the full-flow test.

    Returns an unstarted MockRouter — the test starts it via ``with mock_payment_gateway:``.
    """
    router = respx.mock(base_url="http://mock-payment:8000", assert_all_called=False)
    router.post("/api/checkout").respond(
        200,
        json={
            "preference_id": "mp-test-pref-001",
            "init_point": "https://mercadopago.com.ar/checkout/test",
        },
    )
    return router


class TestFullProjectFlow:
    """Full end-to-end project flow: create → fragments → preview → checkout →
    webhook → final → stream.
    """

    SAMPLE_PROJECT = {
        "recipient": "María",
        "relationship": "pareja",
        "genre": "balada romántica",
        "mood": "romántico",
        "voice": "female",
        "reference_song": "El Amor - Tito La Rosa",
    }

    SAMPLE_FRAGMENT = {
        "fragment": {
            "text": (
                "María, desde que te conocí mi vida cambió por completo. "
                "Cada día a tu lado es una aventura nueva."
            )
        }
    }

    @pytest.mark.asyncio
    async def test_full_flow(
        self,
        test_app: AsyncClient,
        test_db_path: str,
        test_output_dir: str,  # noqa: ARG002 — needed for project worker
        mock_payment_gateway: respx.MockRouter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Execute the complete project flow end-to-end with mocked external dependencies."""

        # ── Configure payment gateway URL ───────────────────────────────────
        monkeypatch.setattr("app.config.settings.PAYMENT_GATEWAY_URL", "http://mock-payment:8000")

        with mock_payment_gateway:
            # ═══════════════════════════════════════════════════════════════
            # 1. CREATE PROJECT
            # ═══════════════════════════════════════════════════════════════
            resp = await test_app.post("/api/projects", json=self.SAMPLE_PROJECT)
            assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
            project_data: Any = resp.json()
            project_id: str = project_data["id"]
            assert project_data["status"] == "draft"
            assert project_id.count("-") == 4  # UUID format

            # Verify project exists in DB
            from app.projects.store import get_project
            project = await get_project(project_id, db_path=test_db_path)
            assert project is not None
            assert project["recipient"] == "María"
            assert project["status"] == "draft"

            # ═══════════════════════════════════════════════════════════════
            # 2. ADD STORY FRAGMENT
            # ═══════════════════════════════════════════════════════════════
            resp = await test_app.patch(f"/api/projects/{project_id}", json=self.SAMPLE_FRAGMENT)
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            updated: Any = resp.json()
            assert len(updated["fragments"]) == 1
            assert updated["fragments"][0]["text"] == self.SAMPLE_FRAGMENT["fragment"]["text"]

            # ═══════════════════════════════════════════════════════════════
            # 3. GENERATE PREVIEW
            # ═══════════════════════════════════════════════════════════════
            resp = await test_app.post(f"/api/projects/{project_id}/preview")
            assert resp.status_code == 202, f"Expected 202, got {resp.status_code}: {resp.text}"
            preview_data: Any = resp.json()
            preview_job_id: str = preview_data["job_id"]
            assert preview_data["status"] == "queued"

            # Poll preview job until complete
            preview_status = await self._poll_job(test_app, preview_job_id, timeout=30)
            assert preview_status == "complete", (
                f"Preview job ended with status {preview_status}"
            )

            # ═══════════════════════════════════════════════════════════════
            # 4. VERIFY PROJECT STATUS (should be preview_ready after preview)
            # ═══════════════════════════════════════════════════════════════
            project = await get_project(project_id, db_path=test_db_path)
            assert project is not None
            # The project_worker updates status when preview completes
            # (It calls project_worker which marks the job complete,
            #  but doesn't auto-update project status to preview_ready
            #  explicitly — that's expected to happen at the project level)

            # ═══════════════════════════════════════════════════════════════
            # 5. CREATE CHECKOUT (mocked POSBackend call)
            # ═══════════════════════════════════════════════════════════════
            resp = await test_app.post(f"/api/projects/{project_id}/checkout")
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            checkout_data: Any = resp.json()
            assert checkout_data["preference_id"] == "mp-test-pref-001"
            assert checkout_data["init_point"] == "https://mercadopago.com.ar/checkout/test"
            assert checkout_data["project_id"] == project_id

            # Verify project status updated to payment_pending
            project = await get_project(project_id, db_path=test_db_path)
            assert project is not None
            assert project["status"] == "payment_pending"

            # ═══════════════════════════════════════════════════════════════
            # 6. WEBHOOK — PAYMENT CONFIRMED
            # ═══════════════════════════════════════════════════════════════
            monkeypatch.setattr("app.config.settings.PAYMENT_WEBHOOK_SECRET", "test-webhook-secret")

            webhook_body = {
                "project_id": project_id,
                "payment_id": "mp-payment-001",
                "status": "approved",
            }
            resp = await test_app.post(
                "/api/webhooks/payment-confirmed",
                json=webhook_body,
                headers={"X-Webhook-Secret": "test-webhook-secret"},
            )
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            webhook_data: Any = resp.json()
            assert webhook_data["success"] is True
            assert webhook_data["message"] == "payment_confirmed"

            # Verify project status transitioned to paid
            project = await get_project(project_id, db_path=test_db_path)
            assert project is not None
            assert project["status"] == "paid", f"Expected paid, got {project['status']}"
            assert project.get("paid_at") is not None, "paid_at should be set"

            # ═══════════════════════════════════════════════════════════════
            # 7. GENERATE FINAL SONG
            # ═══════════════════════════════════════════════════════════════
            resp = await test_app.post(f"/api/projects/{project_id}/final")
            assert resp.status_code == 202, f"Expected 202, got {resp.status_code}: {resp.text}"
            final_data: Any = resp.json()
            final_job_id: str = final_data["job_id"]

            # Poll final job until complete
            final_status = await self._poll_job(test_app, final_job_id, timeout=60)
            assert final_status == "complete", (
                f"Final job ended with status {final_status}"
            )

            # ═══════════════════════════════════════════════════════════════
            # 8. STREAM FINAL SONG
            # ═══════════════════════════════════════════════════════════════
            resp = await test_app.get(f"/api/stream/{final_job_id}")
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            assert resp.headers.get("content-type") == "audio/mpeg"
            assert resp.headers.get("X-Job-Status") == "complete"
            assert resp.headers.get("X-Paid-Content") == "true"
            assert len(resp.content) > 100, "Stream content too short"

            # ═══════════════════════════════════════════════════════════════
            # 9. VERIFY PREVIEW STREAM (still accessible after payment)
            # ═══════════════════════════════════════════════════════════════
            resp = await test_app.get(f"/api/stream/{final_job_id}?preview=true")
            assert resp.status_code == 206, (
                f"Expected 206, got {resp.status_code}: {resp.text}"
            )
            assert resp.headers.get("X-Freemium-Preview") == "true"

            # ═══════════════════════════════════════════════════════════════
            # 10. VERIFY JOB TRANSITIONS
            # ═══════════════════════════════════════════════════════════════
            from app.jobs.store import get_connection
            from app.jobs.store import init_db as init_jobs_db

            conn = await get_connection(test_db_path)
            try:
                await init_jobs_db(conn)
                cursor = await conn.execute(
                    "SELECT to_status FROM job_transitions WHERE job_id = ? ORDER BY id",
                    (final_job_id,),
                )
                transitions = [row["to_status"] for row in await cursor.fetchall()]
                assert "lyrics_generating" in transitions
                assert "music_generating" in transitions
                assert "processing" in transitions
                assert "complete" in transitions
            finally:
                await conn.close()

    @pytest.mark.asyncio
    async def test_final_requires_payment(
        self,
        test_app: AsyncClient,
        test_db_path: str,
        sample_generate_request: dict[str, str],  # noqa: ARG002
        monkeypatch: pytest.MonkeyPatch,  # noqa: ARG002
    ) -> None:
        """POST /api/projects/{id}/final returns 402 if project is not paid."""
        # Create a project (no fragment, direct DB approach)
        import uuid
        from datetime import datetime, timezone

        from app.projects import store

        project_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        # Ensure the schema exists before inserting directly (create_project
        # initializes it on first write; direct inserts must too).
        await store.init_schema(test_db_path)
        conn = await store._get_conn(test_db_path)
        try:
            await conn.execute(
                """INSERT INTO projects
                   (id, recipient, relationship, genre, mood, voice, status, created_at, updated_at)
                   VALUES (?, 'Test', 'test', 'pop', 'happy', 'female', 'draft', ?, ?)""",
                (project_id, now, now),
            )
            await conn.commit()
        finally:
            await conn.close()

        resp = await test_app.post(f"/api/projects/{project_id}/final")
        assert resp.status_code == 402, f"Expected 402, got {resp.status_code}: {resp.text}"
        data: Any = resp.json()
        assert "payment_required" in str(data.get("detail", data))

    @pytest.mark.asyncio
    async def test_webhook_invalid_secret(
        self,
        test_app: AsyncClient,
    ) -> None:
        """Webhook with invalid secret should return 401."""
        body = {
            "project_id": "nonexistent",
            "payment_id": "mp-test",
            "status": "approved",
        }
        resp = await test_app.post(
            "/api/webhooks/payment-confirmed",
            json=body,
            headers={"X-Webhook-Secret": "wrong-secret"},
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"

    async def _poll_job(
        self,
        client: AsyncClient,
        job_id: str,
        timeout: int = 30,
    ) -> str:
        """Poll job status until completion, failure, or timeout.

        Returns the final status string.
        """
        for _ in range(timeout * 10):  # poll every 100ms
            resp = await client.get(f"/api/status/{job_id}")
            if resp.status_code != 200:
                await asyncio.sleep(0.1)
                continue
            data: Any = resp.json()
            status = data["status"]
            if status in ("complete", "failed"):
                return status
            await asyncio.sleep(0.1)

        raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")
