const statuses = ["backlog", "in_progress", "blocked", "done"];
const form = document.querySelector("#taskForm");

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

function taskNode(task) {
  const node = document.createElement("article");
  node.className = "task";
  const source = task.source_name ? `<span class="pill">${escapeHtml(task.source_name)}</span>` : "";
  const reminder = task.reminder_at
    ? `<span class="pill">reminder ${new Date(task.reminder_at).toLocaleString()}</span>`
    : "";
  node.innerHTML = `
    <h3>${escapeHtml(task.title)}</h3>
    ${task.description ? `<p>${escapeHtml(task.description)}</p>` : ""}
    <div class="meta">
      <span class="pill">P${task.priority}</span>
      <span class="pill">${escapeHtml(task.assignee)}</span>
      <span class="pill">${escapeHtml(task.origin)}</span>
      ${source}
      ${reminder}
    </div>
    <div class="actions">
      <button class="secondary" data-action="me">Me</button>
      <button class="secondary" data-action="codex">Codex</button>
      <button class="secondary" data-action="start">Start</button>
      <button data-action="done">Done</button>
    </div>
  `;
  node.querySelector('[data-action="me"]').addEventListener("click", () => updateTask(task.id, { assignee: "me" }));
  node.querySelector('[data-action="codex"]').addEventListener("click", () => updateTask(task.id, { assignee: "codex" }));
  node.querySelector('[data-action="start"]').addEventListener("click", () => updateTask(task.id, { status: "in_progress" }));
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
