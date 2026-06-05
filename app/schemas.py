from datetime import datetime
from enum import StrEnum
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from app.models import TaskAssignee, TaskOrigin, TaskStatus


class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    status: TaskStatus = TaskStatus.backlog
    assignee: TaskAssignee = TaskAssignee.unassigned
    origin: TaskOrigin = TaskOrigin.manual
    priority: int = Field(default=3, ge=1, le=5)
    source_name: str | None = Field(default=None, max_length=160)
    source_url: str | None = None
    source_context: str | None = None
    due_at: datetime | None = None
    reminder_at: datetime | None = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = None
    status: TaskStatus | None = None
    assignee: TaskAssignee | None = None
    origin: TaskOrigin | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    source_name: str | None = Field(default=None, max_length=160)
    source_url: str | None = None
    source_context: str | None = None
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    reminder_last_sent_at: datetime | None = None


class TaskRead(TaskBase):
    id: int
    reminder_last_sent_at: datetime | None = None
    completed_at: datetime | None = None
    agent_id: str | None = None
    agent_run_id: str | None = None
    agent_claimed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContextIngest(BaseModel):
    origin: TaskOrigin
    source_name: str | None = None
    source_url: str | None = None
    source_context: str | None = None
    tasks: list[TaskCreate]


class ContextIngestResult(BaseModel):
    created: list[TaskRead]


class AgentQueueSummary(BaseModel):
    active: int
    overdue: int
    due_soon: int
    codex_ready: int
    human_input: int
    review: int
    blocked: int
    unassigned: int


class AgentQueueRead(BaseModel):
    summary: AgentQueueSummary
    tasks: list[TaskRead]


class AgentReportStatus(StrEnum):
    completed = "completed"
    sent = "sent"
    draft = "draft"
    blocked = "blocked"
    failed = "failed"
    skipped = "skipped"


class AgentParallelClaim(BaseModel):
    limit: int = Field(default=4, ge=1, le=20)
    agent_ids: list[str] = Field(default_factory=list, max_length=20)
    sort: str = Field(default="smart", pattern="^(smart|due|created|updated|priority|owner)$")


class AgentTaskAssignment(BaseModel):
    agent_id: str
    task: TaskRead


class AgentParallelClaimResult(BaseModel):
    run_id: str
    assignments: list[AgentTaskAssignment]


class AgentTaskReport(BaseModel):
    agent_id: str = Field(default="codex", min_length=1, max_length=120)
    run_id: str = Field(min_length=1, max_length=120)
    status: AgentReportStatus
    summary: str = Field(min_length=1, max_length=2000)
    artifact_url: str | None = None
    external_status: str | None = Field(default=None, max_length=120)
    message_text: str | None = None
    chat_report: str | None = None
    next_status: TaskStatus | None = None

    @field_validator("artifact_url")
    @classmethod
    def validate_artifact_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        scheme = urlparse(value).scheme.lower()
        if scheme not in {"http", "https", "mailto", "slack"}:
            raise ValueError("artifact_url must use http, https, mailto, or slack")
        return value


class AgentTaskReportResult(BaseModel):
    task: TaskRead
    chat_report: str
