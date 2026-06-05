# API

All `/api/*` endpoints require `Authorization: Bearer <TASK_TRACKER_API_KEY>` or
an authenticated browser session. Do not expose an instance without a real API
key and session secret.

If `due_at` is omitted when a task is created, the server estimates DD from
priority:

- P1: about 1 day
- P2: about 3 days
- P3: about 7 days
- P4: about 14 days
- P5: about 30 days

## Connector Adapters

Personal Task Assistant exposes a connector contract; it does not include
ready-made credentials or source-specific clients for Jira, Asana, YouTrack,
Linear, Trello, Slack, Telegram, email, or similar systems.

Users should implement their own adapters for each source:

- Webhook adapters receive events from task trackers or chat tools and call
  `POST /api/agent/ingest/context`.
- Polling adapters periodically read source APIs and call `POST /api/agent/tasks`
  or `POST /api/ingest/context`.
- Sync adapters read `GET /api/agent/queue` and update external trackers through
  the external tool's own API.

Keep credentials in the adapter runtime or secret manager. Do not send API keys,
OAuth tokens, service-account files, or raw private exports into the repository.

## Create a Task

```bash
curl -X POST "$TASK_TRACKER_URL/api/tasks" \
  -H "Authorization: Bearer $TASK_TRACKER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Reply to partner about contract",
    "description": "Extracted from Slack thread.",
    "assignee": "me",
    "origin": "slack",
    "priority": 2,
    "source_name": "Slack #partners",
    "source_url": "https://example.slack.com/archives/...",
    "due_at": "2026-05-08T15:00:00Z",
    "reminder_at": "2026-05-06T08:00:00Z"
  }'
```

Use `/api/agent/tasks` for the same create contract when the caller is another
agent. The endpoint records the task event with the `agent_api` note.

```bash
curl -X POST "$TASK_TRACKER_URL/api/agent/tasks" \
  -H "Authorization: Bearer $TASK_TRACKER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Audit stale tasks in the PM queue",
    "assignee": "codex",
    "origin": "codex",
    "priority": 2
  }'
```

## Ingest Tasks From Context

Codex should read Slack, Telegram, Gmail, or local context, extract concrete tasks, and
send normalized records:

```bash
curl -X POST "$TASK_TRACKER_URL/api/ingest/context" \
  -H "Authorization: Bearer $TASK_TRACKER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "origin": "email",
    "source_name": "Gmail thread from Alice",
    "source_url": "https://mail.google.com/...",
    "source_context": "Alice asked for revised numbers by Friday.",
    "tasks": [
      {
        "title": "Send Alice revised numbers",
        "assignee": "me",
        "priority": 2,
        "reminder_at": "2026-05-07T09:00:00Z"
      }
    ]
  }'
```

The same context-ingest contract is also available at
`POST /api/agent/ingest/context` for external agent clients.

## Read Agent Queue

Use the agent queue endpoint when another agent needs the next execution list
without scraping the UI:

```bash
curl "$TASK_TRACKER_URL/api/agent/queue?assignee=codex&sort=smart&limit=25" \
  -H "Authorization: Bearer $TASK_TRACKER_API_KEY"
```

Supported query parameters:

- `status`: `backlog`, `in_progress`, `waiting_review`, `blocked`, `done`, or `cancelled`
- `assignee`: `me`, `codex`, or `unassigned`
- `include_done`: `true` or `false`
- `limit`: 1-250
- `sort`: `smart`, `due`, `created`, `updated`, `priority`, or `owner`

Response shape:

```json
{
  "summary": {
    "active": 42,
    "overdue": 3,
    "due_soon": 4,
    "codex_ready": 12,
    "human_input": 18,
    "review": 5,
    "blocked": 2,
    "unassigned": 1
  },
  "tasks": []
}
```

## Claim Parallel Agent Work

Use this when an external runner is ready to start multiple Codex workers at the
same time. The endpoint picks Codex-owned `backlog` tasks, sorts them, marks them
`in_progress`, stores the active `agent_id` and `run_id`, and returns one task
per agent id. The claim write is conditional, so concurrent runners should not
receive the same task.

```bash
curl -X POST "$TASK_TRACKER_URL/api/agent/parallel/claim" \
  -H "Authorization: Bearer $TASK_TRACKER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "limit": 3,
    "agent_ids": ["codex-a", "codex-b", "codex-c"],
    "sort": "smart"
  }'
```

Response shape:

```json
{
  "run_id": "f0b6f49d-19f9-4e2a-8e78-6b9e9bcf7b9f",
  "assignments": [
    {
      "agent_id": "codex-a",
      "task": {
        "id": 12,
        "title": "Draft reply to partner",
        "status": "in_progress",
        "assignee": "codex",
        "agent_id": "codex-a",
        "agent_run_id": "f0b6f49d-19f9-4e2a-8e78-6b9e9bcf7b9f"
      }
    }
  ]
}
```

If `agent_ids` is omitted, the server generates `codex-agent-1`,
`codex-agent-2`, and so on up to `limit`.

## Report Agent Work

Each worker should report back when its assigned task is complete, blocked, or
needs review. The report is appended to the task description in a structured
block and rendered in the UI as a collapsible `Codex work report`. The report
must include the same `agent_id` and `run_id` returned by the claim endpoint.

```bash
curl -X POST "$TASK_TRACKER_URL/api/agent/tasks/12/report" \
  -H "Authorization: Bearer $TASK_TRACKER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "codex-a",
    "run_id": "f0b6f49d-19f9-4e2a-8e78-6b9e9bcf7b9f",
    "status": "draft",
    "summary": "Prepared a concise approval email and left it unsent for review.",
    "external_status": "draft",
    "artifact_url": "https://mail.google.com/mail/u/0/#drafts",
    "message_text": "Hi Alice,\\n\\nThanks for the update...",
    "chat_report": "Draft is ready in Gmail. I did not send it."
  }'
```

Report status values are `completed`, `sent`, `draft`, `blocked`, `failed`, and
`skipped`.

`artifact_url` must use `http`, `https`, `mailto`, or `slack`. Unsafe schemes are
rejected server-side, and the UI also renders unknown schemes as plain text.

Default task status after a report:

- `completed`, `sent`, and `draft` move the task to `waiting_review`.
- `blocked` and `failed` move it to `blocked`.
- `skipped` moves it back to `backlog`.

The response includes the updated task and `chat_report`. If the request did not
provide `chat_report`, the server generates one from the task title, summary,
artifact link, external status, and message text.

## Update Status or Assignment

```bash
curl -X PATCH "$TASK_TRACKER_URL/api/tasks/1" \
  -H "Authorization: Bearer $TASK_TRACKER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"assignee": "codex", "status": "in_progress"}'
```

Task status values are `backlog`, `in_progress`, `waiting_review`, `blocked`, `done`, and `cancelled`.

## Delete a Task

```bash
curl -X DELETE "$TASK_TRACKER_URL/api/tasks/1" \
  -H "Authorization: Bearer $TASK_TRACKER_API_KEY"
```
