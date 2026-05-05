from datetime import datetime, timezone

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth import current_user, is_allowed_email, require_api_key_or_user
from app.config import get_settings
from app.db import Base, engine, get_db
from app.models import Task, TaskStatus, utc_now
from app.schemas import ContextIngest, ContextIngestResult, TaskCreate, TaskRead, TaskUpdate


settings = get_settings()
app = FastAPI(title=settings.app_name)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    same_site="lax",
    https_only=False,
)
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

oauth = OAuth()
if settings.google_oauth_enabled:
    oauth.register(
        name="google",
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> Response:
    if not settings.google_oauth_enabled:
        return templates.TemplateResponse(
            "auth_setup.html",
            {
                "request": request,
                "app_name": settings.app_name,
            },
            status_code=503,
        )
    user = current_user(request)
    if user is None:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "user": user,
        },
    )


@app.get("/login", response_class=HTMLResponse)
async def login(request: Request) -> Response:
    if not settings.google_oauth_enabled:
        return templates.TemplateResponse(
            "auth_setup.html",
            {
                "request": request,
                "app_name": settings.app_name,
            },
            status_code=503,
        )
    redirect_uri = request.url_for("google_auth_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/google/callback")
async def google_auth_callback(request: Request) -> RedirectResponse:
    if not settings.google_oauth_enabled:
        return RedirectResponse(url="/")
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError:
        return RedirectResponse(url="/login")
    userinfo = token.get("userinfo")
    if userinfo is None:
        userinfo = await oauth.google.userinfo(token=token)
    email = str(userinfo.get("email", "")).lower()
    if not email or not is_allowed_email(email):
        request.session.clear()
        return RedirectResponse(url="/login?denied=1")
    request.session["user"] = {
        "email": email,
        "name": str(userinfo.get("name") or email),
        "picture": str(userinfo.get("picture") or ""),
    }
    return RedirectResponse(url="/")


@app.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/api/me", dependencies=[Depends(require_api_key_or_user)])
def me(request: Request) -> dict[str, str] | None:
    return current_user(request)


@app.get("/api/tasks", response_model=list[TaskRead], dependencies=[Depends(require_api_key_or_user)])
def list_tasks(
    db: Session = Depends(get_db),
    status: TaskStatus | None = None,
    assignee: str | None = None,
    include_done: bool = Query(default=False),
) -> list[Task]:
    statement = select(Task).order_by(Task.priority.asc(), Task.due_at.asc().nullslast(), Task.created_at.desc())
    if status is not None:
        statement = statement.where(Task.status == status)
    elif not include_done:
        statement = statement.where(Task.status.not_in([TaskStatus.done, TaskStatus.cancelled]))
    if assignee:
        statement = statement.where(Task.assignee == assignee)
    return list(db.scalars(statement).all())


@app.post("/api/tasks", response_model=TaskRead, dependencies=[Depends(require_api_key_or_user)])
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> Task:
    task = Task(**payload.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@app.patch("/api/tasks/{task_id}", response_model=TaskRead, dependencies=[Depends(require_api_key_or_user)])
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Task not found")

    updates = payload.model_dump(exclude_unset=True)
    if updates.get("status") == TaskStatus.done and task.completed_at is None:
        task.completed_at = utc_now()
    if "status" in updates and updates["status"] != TaskStatus.done:
        task.completed_at = None
    for key, value in updates.items():
        setattr(task, key, value)
    db.commit()
    db.refresh(task)
    return task


@app.delete("/api/tasks/{task_id}", dependencies=[Depends(require_api_key_or_user)])
def delete_task(task_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    task = db.get(Task, task_id)
    if task is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return {"deleted": True}


@app.post("/api/ingest/context", response_model=ContextIngestResult, dependencies=[Depends(require_api_key_or_user)])
def ingest_context(payload: ContextIngest, db: Session = Depends(get_db)) -> ContextIngestResult:
    created: list[Task] = []
    for item in payload.tasks:
        data = item.model_dump()
        data["origin"] = payload.origin
        data["source_name"] = data.get("source_name") or payload.source_name
        data["source_url"] = data.get("source_url") or payload.source_url
        data["source_context"] = data.get("source_context") or payload.source_context
        task = Task(**data)
        db.add(task)
        created.append(task)
    db.commit()
    for task in created:
        db.refresh(task)
    return ContextIngestResult(created=created)


@app.get("/api/reminders/due", response_model=list[TaskRead], dependencies=[Depends(require_api_key_or_user)])
def due_reminders(db: Session = Depends(get_db), now: datetime | None = None) -> list[Task]:
    current = now or datetime.now(timezone.utc)
    statement = (
        select(Task)
        .where(Task.status.not_in([TaskStatus.done, TaskStatus.cancelled]))
        .where(
            or_(
                (Task.reminder_at.is_not(None)) & (Task.reminder_at <= current),
                (Task.due_at.is_not(None)) & (Task.due_at <= current),
            )
        )
        .where(
            or_(
                Task.reminder_last_sent_at.is_(None),
                (Task.reminder_at.is_not(None)) & (Task.reminder_last_sent_at < Task.reminder_at),
                (Task.due_at.is_not(None)) & (Task.reminder_last_sent_at < Task.due_at),
            )
        )
        .order_by(Task.reminder_at.asc(), Task.priority.asc())
    )
    return list(db.scalars(statement).all())
