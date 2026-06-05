from datetime import datetime, timezone
from textwrap import indent

from app.schemas import AgentTaskReport, TaskRead


REPORT_START = "<!-- codex-work-report:start -->"
REPORT_END = "<!-- codex-work-report:end -->"


def append_agent_report(description: str | None, report: AgentTaskReport) -> str:
    existing = (description or "").rstrip()
    block = format_report_block(report)
    if existing:
        return f"{existing}\n\n{block}"
    return block


def build_chat_report(task: TaskRead, report: AgentTaskReport) -> str:
    if report.chat_report and report.chat_report.strip():
        return report.chat_report.strip()
    lines = [
        f"Task #{task.id}: {task.title}",
        f"Status: {report.status.value}",
        f"Work: {report.summary.strip()}",
    ]
    if report.artifact_url:
        lines.append(f"Link: {report.artifact_url.strip()}")
    if report.external_status:
        lines.append(f"External status: {report.external_status.strip()}")
    if report.message_text:
        lines.append("Message text:")
        lines.append(report.message_text.strip())
    return "\n".join(lines)


def format_report_block(report: AgentTaskReport) -> str:
    reported_at = datetime.now(timezone.utc).isoformat()
    lines = [
        REPORT_START,
        f"reported_at: {reported_at}",
        f"agent_id: {_clean_scalar(report.agent_id)}",
        f"status: {report.status.value}",
    ]
    if report.external_status:
        lines.append(f"external_status: {_clean_scalar(report.external_status)}")
    if report.artifact_url:
        lines.append(f"artifact_url: {_clean_scalar(report.artifact_url)}")
    lines.append("summary:")
    lines.append(_indent_multiline(_clean_multiline(report.summary)))
    if report.message_text:
        lines.append("message_text:")
        lines.append(_indent_multiline(_clean_multiline(report.message_text)))
    lines.append(REPORT_END)
    return "\n".join(lines)


def _clean_scalar(value: str) -> str:
    return _clean_multiline(value).replace("\n", " ").strip()


def _clean_multiline(value: str) -> str:
    return value.replace(REPORT_START, "").replace(REPORT_END, "").strip()


def _indent_multiline(value: str) -> str:
    return indent(value, "  ", predicate=lambda _: True)
