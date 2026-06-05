import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor


_temp_dir = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{_temp_dir.name}/task_tracker.db"
os.environ["TASK_STORE"] = "sqlite"
os.environ["TASK_TRACKER_API_KEY"] = "test-key"
os.environ["SESSION_SECRET_KEY"] = "test-session-secret-for-local-agent-tests"

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


class AgentParallelApiTest(unittest.TestCase):
    def setUp(self) -> None:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer test-key"}

    def create_task(self, title: str, *, assignee: str = "codex", status: str = "backlog") -> dict:
        response = self.client.post(
            "/api/agent/tasks",
            headers=self.headers,
            json={
                "title": title,
                "assignee": assignee,
                "status": status,
                "origin": "codex",
                "priority": 2,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_claims_ready_codex_tasks_for_different_agents(self) -> None:
        self.create_task("Draft partner reply")
        self.create_task("Summarize launch thread")
        self.create_task("Human-only decision", assignee="me")

        response = self.client.post(
            "/api/agent/parallel/claim",
            headers=self.headers,
            json={"limit": 2, "agent_ids": ["codex-a", "codex-b"]},
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(["codex-a", "codex-b"], [item["agent_id"] for item in payload["assignments"]])
        self.assertEqual(["in_progress", "in_progress"], [item["task"]["status"] for item in payload["assignments"]])
        self.assertEqual(["codex-a", "codex-b"], [item["task"]["agent_id"] for item in payload["assignments"]])
        self.assertTrue(all(item["task"]["agent_run_id"] == payload["run_id"] for item in payload["assignments"]))

    def test_claims_codex_in_progress_task_without_active_agent(self) -> None:
        task = self.create_task("Handle assigned Codex task", status="in_progress")

        response = self.client.post(
            "/api/agent/parallel/claim",
            headers=self.headers,
            json={"limit": 1, "agent_ids": ["codex-resume"]},
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(1, len(payload["assignments"]))
        assignment = payload["assignments"][0]
        self.assertEqual(task["id"], assignment["task"]["id"])
        self.assertEqual("in_progress", assignment["task"]["status"])
        self.assertEqual("codex-resume", assignment["task"]["agent_id"])
        self.assertEqual(payload["run_id"], assignment["task"]["agent_run_id"])

    def test_does_not_claim_started_task_when_resume_is_disabled(self) -> None:
        self.create_task("Manual in-progress Codex task", status="in_progress")

        response = self.client.post(
            "/api/agent/parallel/claim",
            headers=self.headers,
            json={"limit": 1, "agent_ids": ["codex-resume"], "claim_started_without_agent": False},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([], response.json()["assignments"])

    def test_concurrent_claims_do_not_duplicate_the_same_task(self) -> None:
        self.create_task("Single worker task")

        def claim(agent_id: str) -> dict:
            with TestClient(app) as client:
                response = client.post(
                    "/api/agent/parallel/claim",
                    headers=self.headers,
                    json={"limit": 1, "agent_ids": [agent_id]},
                )
                self.assertEqual(response.status_code, 200, response.text)
                return response.json()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(claim, ["codex-a", "codex-b"]))

        assignments = [item for result in results for item in result["assignments"]]
        self.assertEqual(1, len(assignments))
        self.assertEqual("in_progress", assignments[0]["task"]["status"])

    def test_agent_report_appends_card_report_and_chat_text(self) -> None:
        task = self.create_task("Draft approval email")
        claim = self.client.post(
            "/api/agent/parallel/claim",
            headers=self.headers,
            json={"limit": 1, "agent_ids": ["codex-mail"]},
        ).json()
        task_id = claim["assignments"][0]["task"]["id"]
        run_id = claim["run_id"]
        self.assertEqual(task["id"], task_id)

        response = self.client.post(
            f"/api/agent/tasks/{task_id}/report",
            headers=self.headers,
            json={
                "agent_id": "codex-mail",
                "run_id": run_id,
                "status": "draft",
                "summary": "Prepared a short email and left it unsent for review.",
                "external_status": "draft",
                "artifact_url": "https://mail.google.com/mail/u/0/#drafts",
                "message_text": "Hi Alice,\n\nThe draft is ready for your review.",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual("waiting_review", payload["task"]["status"])
        self.assertIsNone(payload["task"]["agent_id"])
        self.assertIsNone(payload["task"]["agent_run_id"])
        self.assertIsNone(payload["task"]["agent_claimed_at"])
        self.assertIn("<!-- codex-work-report:start -->", payload["task"]["description"])
        self.assertIn("external_status: draft", payload["task"]["description"])
        self.assertIn("  Hi Alice,\n  \n  The draft is ready for your review.", payload["task"]["description"])
        self.assertIn("Message text:", payload["chat_report"])
        self.assertIn("Status: draft", payload["chat_report"])

    def test_agent_report_can_ask_for_user_input(self) -> None:
        self.create_task("Ask user for missing invoice context")
        claim = self.client.post(
            "/api/agent/parallel/claim",
            headers=self.headers,
            json={"limit": 1, "agent_ids": ["codex-question"]},
        ).json()
        task_id = claim["assignments"][0]["task"]["id"]

        response = self.client.post(
            f"/api/agent/tasks/{task_id}/report",
            headers=self.headers,
            json={
                "agent_id": "codex-question",
                "run_id": claim["run_id"],
                "status": "needs_input",
                "summary": "I found the thread but need approval before contacting the vendor.",
                "question_text": "Should I draft a reply only, or also prepare the invoice dispute details?",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual("blocked", payload["task"]["status"])
        self.assertIn("status: needs_input", payload["task"]["description"])
        self.assertIn("question_text:", payload["task"]["description"])
        self.assertIn("Should I draft a reply only", payload["chat_report"])
        self.assertIn("Question:", payload["chat_report"])

    def test_needs_input_requires_question_text(self) -> None:
        self.create_task("Missing decision task")
        claim = self.client.post(
            "/api/agent/parallel/claim",
            headers=self.headers,
            json={"limit": 1, "agent_ids": ["codex-question"]},
        ).json()
        task_id = claim["assignments"][0]["task"]["id"]

        response = self.client.post(
            f"/api/agent/tasks/{task_id}/report",
            headers=self.headers,
            json={
                "agent_id": "codex-question",
                "run_id": claim["run_id"],
                "status": "needs_input",
                "summary": "I need a decision but did not include the question.",
            },
        )

        self.assertEqual(422, response.status_code)

    def test_report_clears_claim_so_answered_blocked_task_can_be_reclaimed(self) -> None:
        self.create_task("Ask then resume")
        claim = self.client.post(
            "/api/agent/parallel/claim",
            headers=self.headers,
            json={"limit": 1, "agent_ids": ["codex-question"]},
        ).json()
        task_id = claim["assignments"][0]["task"]["id"]

        report = self.client.post(
            f"/api/agent/tasks/{task_id}/report",
            headers=self.headers,
            json={
                "agent_id": "codex-question",
                "run_id": claim["run_id"],
                "status": "needs_input",
                "summary": "Need the missing approval before continuing.",
                "question_text": "Can I proceed with the draft?",
            },
        )
        self.assertEqual(200, report.status_code, report.text)
        reported_task = report.json()["task"]
        self.assertEqual("blocked", reported_task["status"])
        self.assertIsNone(reported_task["agent_id"])
        self.assertIsNone(reported_task["agent_run_id"])

        resumed = self.client.patch(
            f"/api/tasks/{task_id}",
            headers=self.headers,
            json={"status": "in_progress"},
        )
        self.assertEqual(200, resumed.status_code, resumed.text)

        next_claim = self.client.post(
            "/api/agent/parallel/claim",
            headers=self.headers,
            json={"limit": 1, "agent_ids": ["codex-resume"]},
        )
        self.assertEqual(200, next_claim.status_code, next_claim.text)
        next_assignment = next_claim.json()["assignments"][0]
        self.assertEqual(task_id, next_assignment["task"]["id"])
        self.assertEqual("codex-resume", next_assignment["task"]["agent_id"])

    def test_report_requires_matching_active_claim(self) -> None:
        task = self.create_task("Unclaimed Codex task")

        unclaimed = self.client.post(
            f"/api/agent/tasks/{task['id']}/report",
            headers=self.headers,
            json={
                "agent_id": "codex-a",
                "run_id": "missing-run",
                "status": "completed",
                "summary": "Tried to report without a claim.",
            },
        )
        self.assertEqual(409, unclaimed.status_code)

        claim = self.client.post(
            "/api/agent/parallel/claim",
            headers=self.headers,
            json={"limit": 1, "agent_ids": ["codex-a"]},
        ).json()
        task_id = claim["assignments"][0]["task"]["id"]
        wrong_agent = self.client.post(
            f"/api/agent/tasks/{task_id}/report",
            headers=self.headers,
            json={
                "agent_id": "codex-b",
                "run_id": claim["run_id"],
                "status": "completed",
                "summary": "Wrong worker report.",
            },
        )
        self.assertEqual(409, wrong_agent.status_code)

    def test_report_rejects_unsafe_artifact_url(self) -> None:
        self.create_task("Unsafe link task")
        claim = self.client.post(
            "/api/agent/parallel/claim",
            headers=self.headers,
            json={"limit": 1, "agent_ids": ["codex-link"]},
        ).json()
        response = self.client.post(
            f"/api/agent/tasks/{claim['assignments'][0]['task']['id']}/report",
            headers=self.headers,
            json={
                "agent_id": "codex-link",
                "run_id": claim["run_id"],
                "status": "completed",
                "summary": "Unsafe link should not be accepted.",
                "artifact_url": "javascript:alert(1)",
            },
        )
        self.assertEqual(422, response.status_code)


if __name__ == "__main__":
    unittest.main()
