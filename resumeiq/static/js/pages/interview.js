import { api } from "../core/api.js";
import { fillResumeSelect, targetRole } from "../core/common.js";
import { $, $$, confirmDialog, emptyState, errorState, esc, fmtDate, icon, initTabs, load, loadingState, params, progressBar,
  toast, toastError, withBusy } from "../core/ui.js";

let mode = "prep", session = null;
const box = $("#session");
const CAT = { technical: "Technical", behavioral: "Behavioral", hr: "HR", project: "Project", system_design: "System design", dsa: "DSA" };
const tabs = initTabs(document.querySelector(".tabs"), (t) => { if (t === "history") loadHistory(); });

$$("#mode button").forEach((b) => b.addEventListener("click", () => {
  mode = b.dataset.mode;
  $$("#mode button").forEach((x) => x.setAttribute("aria-pressed", x === b));
  $("#mode-hint").textContent = mode === "mock"
    ? "The interviewer asks one question at a time, evaluates your answer, and may ask a follow-up. You get a report at the end."
    : "Get a question set with what interviewers look for. Answer any question for feedback.";
}));

async function init() {
  $("#n-role").value = params().get("role") || (await targetRole());
  await fillResumeSelect($("#n-version"));
  const jds = await api.get("/api/job-descriptions?per_page=50").catch(() => ({ items: [] }));
  $("#n-jd").insertAdjacentHTML("beforeend", jds.items.map((j) => `<option value="${j.id}">${esc(j.title)}${j.company ? ` - ${esc(j.company)}` : ""}</option>`).join(""));
  if (params().get("jd")) $("#n-jd").value = params().get("jd");
  if (params().get("session")) openSession(+params().get("session"));
  else box.innerHTML = `<div class="card">${emptyState("No active session", "Start a new session or open one from History.", "", "mic")}</div>`;
}

$("#new-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const categories = $$("#cats input:checked").map((c) => c.value);
  if (!categories.length) return toast("Pick at least one category.", "warn");
  const role = $("#n-role").value.trim();
  if (role.length < 2) return $("#n-role").focus();
  await withBusy($("#start-btn"), async () => {
    try {
      const r = await api.post("/api/interview/sessions", { mode, target_role: role, categories, count: Math.min(15, Math.max(1, +$("#n-count").value || 6)),
        resume_version_id: +$("#n-version").value || null, job_description_id: +$("#n-jd").value || null });
      if (r.ai_note) toast(r.ai_note, "warn");
      session = r.session;
      history.replaceState(null, "", `?session=${session.id}`);
      tabs.select("session");
      renderSession();
    } catch (err) { toastError(err); }
  }, "Preparing questions...");
});

async function openSession(id) {
  tabs.select("session");
  box.innerHTML = loadingState();
  try { session = (await api.get(`/api/interview/sessions/${id}`)).session; renderSession(); }
  catch (err) { errorState(box, err, () => openSession(id)); }
}

const evalHtml = (a) => `<div class="stack" style="gap:8px">
  <div class="flex between"><strong>Score ${a.overall_score}/100</strong><span class="${a.evaluation_method === "ai" ? "ai-label" : "data-label"}">${a.evaluation_method === "ai" ? "AI evaluation" : "Rule-based evaluation"}</span></div>
  ${Object.entries(a.scores).map(([k, v]) => `<div class="meter-row small"><span>${esc(k.replace("_", " "))}</span>${progressBar(v * 10, "sm")}<span class="val">${v}/10</span></div>`).join("")}
  <p class="small" style="color:var(--text)">${esc(a.feedback)}</p>
  ${a.missing_concepts?.length ? `<div class="small"><strong>Missing:</strong> ${esc(a.missing_concepts.join("; "))}</div>` : ""}
  ${(a.improvements || a.textual_indicators?.improvements || []).length ? `<ul class="bullets small">${(a.improvements || a.textual_indicators.improvements).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
  <div class="tiny faint">${a.textual_indicators || a.indicators ? indicators(a.textual_indicators || a.indicators) : ""}</div></div>`;

const indicators = (t) => `Text indicators: ${t.word_count} words · ${t.hedging_phrases} hedging phrase(s) · STAR elements ${Object.values(t.star_elements || {}).filter(Boolean).length}/4 · ${esc(t.note || "")}`;

function renderSession() {
  if (session.mode === "prep") return renderPrep();
  return renderMock();
}

function renderPrep() {
  box.innerHTML = `<div class="flex between mb-3 flex-wrap"><h2>${esc(session.target_role)} · ${session.questions.length} questions</h2>
    <a class="btn btn-ghost btn-sm" href="/reports/interview?id=${session.id}" target="_blank" rel="noopener">${icon("printer")} Export</a></div>
    <div class="stack">${session.questions.map((q, i) => `<details class="card q-card" data-q="${q.id}" ${i === 0 ? "open" : ""}>
      <summary><span class="badge accent">${esc(CAT[q.category] || q.category)}</span><span class="grow"><strong>${esc(q.question)}</strong></span><span class="badge">${esc(q.difficulty)}</span></summary>
      <div class="grid-2">
        <div><h4 class="mb-2">Why the interviewer asks this</h4><p class="small">${esc(q.why_asked || "")}</p></div>
        <div><h4 class="mb-2">A strong answer contains</h4><ul class="bullets small">${q.strong_answer_points.map((p) => `<li>${esc(p)}</li>`).join("")}</ul></div>
        <div class="span-2"><h4 class="mb-2">Common mistakes</h4><ul class="bullets small">${q.common_mistakes.map((p) => `<li>${esc(p)}</li>`).join("")}</ul></div>
      </div>
      <div class="field mt-3"><label for="ans-${q.id}">Your answer</label><textarea class="textarea" id="ans-${q.id}" rows="5" maxlength="10000">${esc(q.answer?.answer_text || "")}</textarea></div>
      <button class="btn btn-primary btn-sm mt-2" data-eval="${q.id}">${icon("check")} Get feedback</button>
      <div class="mt-3" data-feedback>${q.answer ? evalHtml(q.answer) : ""}</div>
    </details>`).join("")}</div>`;
  box.querySelectorAll("[data-eval]").forEach((b) => (b.onclick = async () => {
    const id = +b.dataset.eval, text = $(`#ans-${id}`).value.trim();
    if (text.length < 3) return toast("Write an answer first.", "warn");
    await withBusy(b, async () => {
      try {
        const r = await api.post(`/api/interview/sessions/${session.id}/answers`, { question_id: id, answer: text });
        b.closest("details").querySelector("[data-feedback]").innerHTML = evalHtml({ ...r.evaluation, overall_score: r.evaluation.overall_score, evaluation_method: r.evaluation.method });
      } catch (err) { toastError(err); }
    }, "Evaluating...");
  }));
}

function renderMock() {
  const answered = session.questions.filter((q) => q.answer);
  const next = session.questions.find((q) => !q.answer);
  if (session.status === "completed") return renderSummary();
  box.innerHTML = `<div class="card"><div class="flex between mb-3 flex-wrap"><h2>Mock interview · ${esc(session.target_role)}</h2>
      <span class="small muted">${answered.length} answered</span></div>
    <div class="chat" id="chat">${answered.map((q) => `
      <div class="bubble ai">${q.is_follow_up ? `<span class="tiny muted">Follow-up</span><br>` : ""}${esc(q.question)}</div>
      <div class="bubble me">${esc(q.answer.answer_text)}</div>
      <div class="bubble eval">${evalHtml(q.answer)}</div>`).join("")}
      ${next ? `<div class="bubble ai"><span class="tiny muted">${esc(CAT[next.category] || next.category)}${next.is_follow_up ? " · follow-up" : ""}</span><br><strong>${esc(next.question)}</strong></div>` : ""}
    </div>
    ${next ? `<div class="field mt-3"><label for="mock-answer">Your answer</label><textarea class="textarea" id="mock-answer" rows="6" maxlength="10000" placeholder="Type your answer as you would say it. Use specific examples."></textarea></div>
      <div class="flex mt-2 flex-wrap"><button class="btn btn-grad" id="send">${icon("arrow")} Submit answer</button><button class="btn btn-ghost" id="finish">End interview & see report</button></div>`
    : `<button class="btn btn-grad mt-3" id="finish">${icon("chart")} See interview report</button>`}</div>`;
  $("#send")?.addEventListener("click", async (e) => {
    const text = $("#mock-answer").value.trim();
    if (text.length < 3) return toast("Write an answer first.", "warn");
    await withBusy(e.target.closest("button"), async () => {
      try {
        await api.post(`/api/interview/sessions/${session.id}/answers`, { question_id: next.id, answer: text });
        session = (await api.get(`/api/interview/sessions/${session.id}`)).session;
        renderMock();
        $("#chat").lastElementChild?.scrollIntoView({ behavior: "smooth", block: "center" });
      } catch (err) { toastError(err); }
    }, "Evaluating...");
  });
  $("#finish").onclick = async (e) => {
    if (next && !(await confirmDialog("End interview?", "Unanswered questions won't be scored.", { confirmLabel: "End & report" }))) return;
    await withBusy(e.target.closest("button"), async () => {
      try { session = (await api.post(`/api/interview/sessions/${session.id}/finish`)).session; renderSummary(); } catch (err) { toastError(err); }
    }, "Building report...");
  };
}

function renderSummary() {
  const s = session.summary || {};
  if (!s.scores) { box.innerHTML = `<div class="card">${emptyState("No answers", s.note || "This session has no answers.", "", "mic")}</div>`; return; }
  const ai = s.ai_summary;
  box.innerHTML = `<div class="card glow mb-3"><div class="flex between flex-wrap"><div><h2>Interview report · ${esc(session.target_role)}</h2>
      <p class="small">${s.answered} of ${s.total} questions answered · ${fmtDate(session.completed_at)}</p></div>
      <div class="flex"><span class="stat-value grad-text">${session.overall_score}</span><a class="btn btn-ghost btn-sm" href="/reports/interview?id=${session.id}" target="_blank" rel="noopener">${icon("printer")} Export</a></div></div></div>
    <div class="grid-2 mb-3">
      <div class="card"><h3 class="mb-2">Scores</h3>${Object.entries(s.scores).map(([k, v]) => `<div class="meter-row"><span>${esc(k.replace("_", " "))}</span>${progressBar(v)}<span class="val">${v}</span></div>`).join("")}
        <p class="tiny faint mt-2">${esc(s.text_indicators.note)} Average ${s.text_indicators.avg_words_per_answer} words per answer; ${s.text_indicators.hedging_phrases_total} hedging phrase(s) in total.</p></div>
      <div class="card"><h3 class="mb-2">Missing concepts</h3>${s.missing_concepts.length ? `<ul class="bullets small">${s.missing_concepts.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>` : `<p class="small">None flagged.</p>`}
        <h3 class="mt-3 mb-2">Suggested improvements</h3>${s.improvements.length ? `<ul class="bullets small">${s.improvements.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>` : `<p class="small">Keep practising with new questions.</p>`}</div>
    </div>
    ${ai ? `<div class="card mb-3"><div class="card-head"><h3>Summary</h3><span class="ai-label">AI-generated</span></div><p style="color:var(--text)">${esc(ai.summary)}</p>
      <div class="grid-2 mt-2"><div><h4 class="mb-2">Strengths</h4><ul class="bullets small">${ai.strengths.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
      <div><h4 class="mb-2">Improvements</h4><ul class="bullets small">${ai.improvements.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div></div></div>` : ""}
    <button class="btn btn-grad" id="again">${icon("refresh")} Practise again</button>`;
  $("#again").onclick = () => tabs.select("new");
}

function loadHistory() {
  const el = $("#history");
  load(el, () => api.get("/api/interview/sessions?per_page=30"), (d) => {
    el.innerHTML = d.items.length ? `<div class="list">${d.items.map((s) => `<div class="list-item" data-id="${s.id}"><span class="list-icon">${icon("mic")}</span>
      <div class="grow"><strong>${esc(s.target_role)}</strong> <span class="badge">${s.mode === "mock" ? "Mock" : "Practice"}</span>
        <div class="tiny muted">${fmtDate(s.created_at)} · ${s.question_count} questions · ${esc(s.status)}${s.overall_score !== null ? ` · score ${s.overall_score}` : ""}</div></div>
      <button class="btn btn-ghost btn-sm" data-open>Open</button><button class="btn btn-ghost btn-sm" data-del aria-label="Delete">${icon("trash")}</button></div>`).join("")}</div>`
      : emptyState("No sessions yet", "Start a practice set or mock interview.", "", "mic");
    el.querySelectorAll("[data-open]").forEach((b) => (b.onclick = () => openSession(+b.closest("[data-id]").dataset.id)));
    el.querySelectorAll("[data-del]").forEach((b) => (b.onclick = async () => {
      if (!(await confirmDialog("Delete session?", "Questions and answers will be removed.", { danger: true, confirmLabel: "Delete" }))) return;
      try { await api.del(`/api/interview/sessions/${b.closest("[data-id]").dataset.id}`); loadHistory(); } catch (err) { toastError(err); }
    }));
  });
}

init().catch(toastError);
