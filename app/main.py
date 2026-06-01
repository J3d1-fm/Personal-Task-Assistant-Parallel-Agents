from datetime import datetime

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session

from app.auth import current_user, is_allowed_email, require_api_key_or_user
from app.config import get_settings
from app.db import Base, engine, get_db
from app.history import choose_update_action, record_task_event
from app.models import TaskStatus
from app.schemas import ContextIngest, ContextIngestResult, TaskCreate, TaskRead, TaskUpdate
from app.store import get_task_store


settings = get_settings()
settings.validate_runtime_config()
app = FastAPI(title=settings.app_name)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    same_site="lax",
    https_only=settings.session_cookie_https,
    max_age=60 * 60 * 24 * 30,
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
    if not settings.use_firestore:
        Base.metadata.create_all(bind=engine)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> Response:
    if settings.local_dev_auth_enabled:
        request.session["user"] = {
            "email": settings.local_dev_user_email,
            "name": "Local Dev",
            "picture": "",
        }
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "app_name": settings.app_name,
                "app_version": settings.app_version,
                "user": current_user(request),
            },
        )
    if not settings.google_oauth_enabled:
        return templates.TemplateResponse(
            "auth_setup.html",
            {
                "request": request,
                "app_name": settings.app_name,
                "redirect_uri": oauth_redirect_uri(request),
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
            "app_version": settings.app_version,
            "user": user,
        },
    )


@app.get("/login", response_class=HTMLResponse)
async def login(request: Request) -> Response:
    if settings.local_dev_auth_enabled:
        request.session["user"] = {
            "email": settings.local_dev_user_email,
            "name": "Local Dev",
            "picture": "",
        }
        return RedirectResponse(url="/")
    if not settings.google_oauth_enabled:
        return templates.TemplateResponse(
            "auth_setup.html",
            {
                "request": request,
                "app_name": settings.app_name,
                "redirect_uri": oauth_redirect_uri(request),
            },
            status_code=503,
        )
    return await oauth.google.authorize_redirect(request, oauth_redirect_uri(request))


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


def oauth_redirect_uri(request: Request) -> str:
    if settings.normalized_public_base_url:
        return f"{settings.normalized_public_base_url}/auth/google/callback"
    return str(request.url_for("google_auth_callback"))


@app.get("/api/me", dependencies=[Depends(require_api_key_or_user)])
def me(request: Request) -> dict[str, str] | None:
    return current_user(request)


@app.get("/api/tasks", response_model=list[TaskRead], dependencies=[Depends(require_api_key_or_user)])
def list_tasks(
    db: Session = Depends(get_db),
    status: TaskStatus | None = None,
    assignee: str | None = None,
    include_done: bool = Query(default=False),
) -> list[TaskRead]:
    return get_task_store(db).list_tasks(status=status, assignee=assignee, include_done=include_done)


@app.post("/api/tasks", response_model=TaskRead, dependencies=[Depends(require_api_key_or_user)])
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> TaskRead:
    task = get_task_store(db).create_task(payload)
    record_task_event("created", task)
    return task


@app.patch("/api/tasks/{task_id}", response_model=TaskRead, dependencies=[Depends(require_api_key_or_user)])
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)) -> TaskRead:
    store = get_task_store(db)
    previous = store.get_task(task_id)
    task = store.update_task(task_id, payload)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    record_task_event(choose_update_action(task, previous), task, previous=previous)
    return task


@app.delete("/api/tasks/{task_id}", dependencies=[Depends(require_api_key_or_user)])
def delete_task(task_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    store = get_task_store(db)
    previous = store.get_task(task_id)
    deleted = store.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    if previous is not None:
        record_task_event("dismissed", previous)
    return {"deleted": True}


@app.post("/api/ingest/context", response_model=ContextIngestResult, dependencies=[Depends(require_api_key_or_user)])
def ingest_context(payload: ContextIngest, db: Session = Depends(get_db)) -> ContextIngestResult:
    created: list[Task] = []
    store = get_task_store(db)
    for item in payload.tasks:
        data = item.model_dump()
        data["origin"] = payload.origin
        data["source_name"] = data.get("source_name") or payload.source_name
        data["source_url"] = data.get("source_url") or payload.source_url
        data["source_context"] = data.get("source_context") or payload.source_context
        task = store.create_task(TaskCreate(**data))
        record_task_event("created", task, note="context_ingest")
        created.append(task)
    return ContextIngestResult(created=created)


@app.get("/api/reminders/due", response_model=list[TaskRead], dependencies=[Depends(require_api_key_or_user)])
def due_reminders(db: Session = Depends(get_db), now: datetime | None = None) -> list[TaskRead]:
    return get_task_store(db).due_reminders(now=now)
