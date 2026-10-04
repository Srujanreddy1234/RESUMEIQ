// Poll a background task and render its REAL processing stages (no fake percentages).
import { api } from "./api.js";
import { esc } from "./ui.js";

export function renderStages(el, stages) {
  el.innerHTML = `<div class="stages" role="list">${stages.map((s) => `
    <div class="stage ${s.status}" role="listitem">
      <span class="dot">${s.status === "done" ? "✓" : s.status === "failed" ? "!" : ""}</span>
      <span>${esc(s.label)}${s.status === "skipped" && s.note ? ` <span class="tiny faint">(${esc(s.note)})</span>` : ""}</span>
    </div>`).join("")}</div>`;
}

export async function pollTask(task, el, { interval = 900, timeoutMs = 180000 } = {}) {
  const started = Date.now();
  let current = task;
  let delay = interval;
  while (true) {
    renderStages(el, current.stages);
    if (current.status === "succeeded") return current.result;
    if (current.status === "failed") {
      const err = new Error(current.error?.message || "Processing failed.");
      err.code = current.error?.code;
      throw err;
    }
    if (Date.now() - started > timeoutMs) throw new Error("This is taking longer than expected. Check Analysis History in a minute.");
    await new Promise((r) => setTimeout(r, delay));
    delay = Math.min(delay * 1.25, 3000);
    current = await api.get(`/api/tasks/${current.id}`);
  }
}
