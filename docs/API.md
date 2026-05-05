# API

All `/api/*` endpoints require `Authorization: Bearer <TASK_TRACKER_API_KEY>`.

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
    "reminder_at": "2026-05-06T08:00:00Z"
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

## Update Status or Assignment

```bash
curl -X PATCH "$TASK_TRACKER_URL/api/tasks/1" \
  -H "Authorization: Bearer $TASK_TRACKER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"assignee": "codex", "status": "in_progress"}'
```

## Delete a Task

```bash
curl -X DELETE "$TASK_TRACKER_URL/api/tasks/1" \
  -H "Authorization: Bearer $TASK_TRACKER_API_KEY"
```
