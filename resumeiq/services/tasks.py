"""Background processing for long AI operations.

Tasks are persisted in `background_tasks`, so any web worker can answer status
polls. Each stage is marked done only when the work for it has actually
finished, so the UI shows real processing stages, never a fake percentage.

For a single-host deployment an in-process thread pool is sufficient; the
interface (submit + TaskContext) is deliberately small so it can be swapped for
RQ/Celery without touching the services.
"""
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

from flask import current_app

from ..errors import ApiError
from ..extensions import db
from ..models import BackgroundTask, utcnow
from .ai import AIUnavailable

log = logging.getLogger(__name__)
_executor = None


def _get_executor(app):
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=app.config["TASK_WORKERS"], thread_name_prefix="resumeiq-task")
    return _executor


class TaskContext:
    def __init__(self, task_id, user_id):
        self.task_id = task_id
        self.user_id = user_id

    def _update(self, **values):
        values["updated_at"] = utcnow()
        if db.engine.dialect.name == "sqlite":
            task = db.session.get(BackgroundTask, self.task_id)
            for k, v in values.items():
                setattr(task, k, v)
            db.session.flush()
            return
        with db.engine.begin() as conn:
            conn.execute(BackgroundTask.__table__.update()
                         .where(BackgroundTask.__table__.c.id == self.task_id).values(**values))

    def _stages(self):
        if db.engine.dialect.name == "sqlite":
            return [dict(s) for s in db.session.get(BackgroundTask, self.task_id).stages]
        with db.engine.connect() as conn:
            row = conn.execute(BackgroundTask.__table__.select()
                               .where(BackgroundTask.__table__.c.id == self.task_id)).mappings().first()
        return [dict(s) for s in (row["stages"] if row else [])]

    def stage(self, key):
        """Mark `key` as running and every earlier stage as done."""
        stages = self._stages()
        reached = False
        for s in stages:
            if s["key"] == key:
                s["status"] = "running"
                reached = True
            elif not reached and s["status"] != "skipped":
                s["status"] = "done"
        self._update(status="running", stages=stages)

    def skip(self, key, note=None):
        stages = self._stages()
        for s in stages:
            if s["key"] == key:
                s["status"] = "skipped"
                if note:
                    s["note"] = note
        self._update(stages=stages)

    def succeed(self, result):
        stages = [dict(s, status="skipped" if s["status"] == "skipped" else "done") for s in self._stages()]
        self._update(status="succeeded", stages=stages, result=result)

    def fail(self, code, message):
        stages = [dict(s, status="failed" if s["status"] == "running" else s["status"]) for s in self._stages()]
        self._update(status="failed", stages=stages, error_code=code, error_message=message[:255])


def submit(user_id, kind, stages, fn, *args):
    """Create a task and run fn(ctx, *args). `stages` is a list of (key, label)."""
    task = BackgroundTask(id=str(uuid.uuid4()), user_id=user_id, kind=kind, status="queued",
                          stages=[{"key": k, "label": label, "status": "pending"} for k, label in stages])
    db.session.add(task)
    db.session.commit()
    app = current_app._get_current_object()
    if app.config.get("TASKS_EAGER"):
        _run(app, task.id, user_id, fn, args, eager=True)
        db.session.refresh(task)
    else:
        _get_executor(app).submit(_run, app, task.id, user_id, fn, args)
    return task


def _run(app, task_id, user_id, fn, args, eager=False):
    def body():
        ctx = TaskContext(task_id, user_id)
        try:
            result = fn(ctx, *args)
            db.session.commit()
            ctx.succeed(result)
            db.session.commit()
        except ApiError as exc:
            db.session.rollback()
            ctx.fail(exc.code, exc.message)
            db.session.commit()
        except AIUnavailable as exc:
            db.session.rollback()
            ctx.fail("ai_unavailable", exc.user_message)
            db.session.commit()
        except Exception:
            db.session.rollback()
            log.exception("background_task_failed", extra={"task_id": task_id})
            ctx.fail("internal_error", "Something went wrong while processing. Please try again.")
            db.session.commit()

    if eager:
        body()
        return
    with app.app_context():
        try:
            body()
        finally:
            db.session.remove()
