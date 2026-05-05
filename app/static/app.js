const statuses = ["backlog", "in_progress", "waiting_review", "blocked", "done"];
const form = document.querySelector("#taskForm");
let dragState = null;

function headers() {
  const apiKey = localStorage.getItem("taskTrackerApiKey");
  const values = { "Content-Type": "application/json" };
  if (apiKey) values.Authorization = `Bearer ${apiKey}`;
  return values;
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...headers(),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

function localDateTimeToIso(value) {
  if (!value) return null;
  return new Date(value).toISOString();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(form);
  const payload = Object.fromEntries(data.entries());
  payload.priority = Number(payload.priority);
  payload.origin = "manual";
  payload.reminder_at = localDateTimeToIso(payload.reminder_at);
  if (!payload.description) payload.description = null;
  try {
    await request("/api/tasks", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    form.reset();
    form.querySelector("[name=priority]").value = "3";
    await loadTasks();
  } catch (error) {
    alert(`Could not create task: ${error.message}`);
  }
});

async function updateTask(id, patch) {
  await request(`/api/tasks/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
  await loadTasks();
}

function isOverdue(task) {
  const targets = [task.due_at, task.reminder_at].filter(Boolean).map((value) => new Date(value));
  return targets.some((value) => !Number.isNaN(value.valueOf()) && value < new Date());
}

function isNeutralTask(task) {
  if (task.priority <= 2) return false;
  const text = `${task.title} ${task.description || ""}`.toLowerCase();
  return /\b(thanks?|thank you|reply thanks|simple feedback)\b|спасибо|поблагодар|простой фидбек|ответить спасибо/.test(text);
}

function priorityClass(task) {
  const classes = ["task"];
  if (!isNeutralTask(task)) {
    if (task.priority <= 1) classes.push("priority-urgent");
    else if (task.priority === 2) classes.push("priority-important");
    else classes.push("priority-normal");
  }
  if (isOverdue(task)) classes.push("is-overdue");
  return classes.join(" ");
}

function formatDateTime(value) {
  return new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function titleCaseStatus(value) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function buttonClass(isActive) {
  return isActive ? "is-active" : "secondary";
}

function clearDropTargets() {
  document.querySelectorAll(".column.is-drop-target").forEach((column) => column.classList.remove("is-drop-target"));
}

function columnAtPoint(x, y, draggedNode) {
  const previousPointerEvents = draggedNode.style.pointerEvents;
  draggedNode.style.pointerEvents = "none";
  const column = document.elementFromPoint(x, y)?.closest(".column");
  draggedNode.style.pointerEvents = previousPointerEvents;
  return column;
}

function resetDragNode(node) {
  node.classList.remove("is-dragging");
  node.style.transform = "";
  node.style.zIndex = "";
}

function setupTaskDrag(node, task) {
  node.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || event.target.closest("button, input, select, textarea, a")) return;
    dragState = {
      taskId: task.id,
      pointerId: event.pointerId,
      node,
      startX: event.clientX,
      startY: event.clientY,
      active: false,
    };
    node.setPointerCapture(event.pointerId);
  });

  node.addEventListener("pointermove", (event) => {
    if (!dragState || dragState.pointerId !== event.pointerId || dragState.node !== node) return;
    const deltaX = event.clientX - dragState.startX;
    const deltaY = event.clientY - dragState.startY;
    if (!dragState.active && Math.hypot(deltaX, deltaY) < 8) return;
    dragState.active = true;
    node.classList.add("is-dragging");
    node.style.zIndex = "10";
    node.style.transform = `translate(${deltaX}px, ${deltaY}px)`;
    clearDropTargets();
    columnAtPoint(event.clientX, event.clientY, node)?.classList.add("is-drop-target");
  });

  node.addEventListener("pointerup", async (event) => {
    if (!dragState || dragState.pointerId !== event.pointerId || dragState.node !== node) return;
    const { active, taskId } = dragState;
    const column = active ? columnAtPoint(event.clientX, event.clientY, node) : null;
    dragState = null;
    clearDropTargets();
    resetDragNode(node);
    node.releasePointerCapture(event.pointerId);
    const status = column?.dataset.status;
    if (!active || !status || status === task.status) return;
    try {
      await updateTask(taskId, { status });
    } catch (error) {
      alert(`Could not move task: ${error.message}`);
    }
  });

  node.addEventListener("pointercancel", (event) => {
    if (!dragState || dragState.pointerId !== event.pointerId || dragState.node !== node) return;
    dragState = null;
    clearDropTargets();
    resetDragNode(node);
  });
}

function taskNode(task) {
  const node = document.createElement("article");
  node.className = priorityClass(task);
  node.dataset.taskId = task.id;
  node.setAttribute("aria-label", `${task.title}, ${titleCaseStatus(task.status)}`);
  const source = task.source_name ? `<span class="pill">${escapeHtml(task.source_name)}</span>` : "";
  const reminder = task.reminder_at
    ? `<span class="pill date-pill" title="${escapeHtml(new Date(task.reminder_at).toLocaleString())}">📅 ${escapeHtml(formatDateTime(task.reminder_at))}</span>`
    : "";
  const assigneeLabel = task.assignee === "me" ? "Me" : task.assignee === "codex" ? "Codex" : "Unassigned";
  node.innerHTML = `
    <h3>${escapeHtml(task.title)}</h3>
    ${task.description ? `<p>${escapeHtml(task.description)}</p>` : ""}
    <div class="meta">
      <span class="pill">P${task.priority}</span>
      <span class="pill">${escapeHtml(assigneeLabel)}</span>
      <span class="pill">${escapeHtml(task.origin)}</span>
      ${source}
      ${reminder}
    </div>
    <div class="actions">
      <button class="${buttonClass(task.assignee === "me")}" data-action="me" aria-pressed="${task.assignee === "me"}">Me</button>
      <button class="${buttonClass(task.assignee === "codex")}" data-action="codex" aria-pressed="${task.assignee === "codex"}">Codex</button>
      <button class="${buttonClass(task.status === "in_progress")}" data-action="start" aria-pressed="${task.status === "in_progress"}">Start</button>
      <button class="${buttonClass(task.status === "waiting_review")}" data-action="review" aria-pressed="${task.status === "waiting_review"}">Review</button>
      <button class="${buttonClass(task.status === "done")}" data-action="done" aria-pressed="${task.status === "done"}">Done</button>
    </div>
  `;
  setupTaskDrag(node, task);
  node.querySelector('[data-action="me"]').addEventListener("click", () => updateTask(task.id, { assignee: "me" }));
  node.querySelector('[data-action="codex"]').addEventListener("click", () => updateTask(task.id, { assignee: "codex" }));
  node.querySelector('[data-action="start"]').addEventListener("click", () => updateTask(task.id, { status: "in_progress" }));
  node.querySelector('[data-action="review"]').addEventListener("click", () => updateTask(task.id, { status: "waiting_review" }));
  node.querySelector('[data-action="done"]').addEventListener("click", () => updateTask(task.id, { status: "done" }));
  return node;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function loadTasks() {
  for (const status of statuses) {
    document.querySelector(`#${status}`).innerHTML = "";
  }
  try {
    const tasks = await request("/api/tasks?include_done=true");
    for (const status of statuses) {
      const bucket = document.querySelector(`#${status}`);
      const items = tasks.filter((task) => task.status === status);
      if (items.length === 0) {
        bucket.innerHTML = '<div class="empty">No tasks</div>';
      } else {
        for (const task of items) bucket.appendChild(taskNode(task));
      }
    }
  } catch (error) {
    for (const status of statuses) {
      document.querySelector(`#${status}`).innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
    }
  }
}

loadTasks();
