"""Notification creation (respecting user preferences) and reminder generation."""
from datetime import datetime, timedelta, timezone

from ..extensions import db
from ..models import Application, Notification, Profile, SavedJob

PREF_FIELD = {"analysis": "notify_analysis", "learning": "notify_learning", "application": "notify_applications",
              "interview": "notify_interviews", "job": "notify_jobs"}


def notify(user_id, ntype, title, body=None, link=None, dedupe_key=None):
    profile = Profile.query.filter_by(user_id=user_id).first()
    field = PREF_FIELD.get(ntype)
    if profile is not None and field and not getattr(profile, field):
        return None
    if dedupe_key and Notification.query.filter_by(user_id=user_id, dedupe_key=dedupe_key).first():
        return None
    n = Notification(user_id=user_id, type=ntype, title=title[:200], body=body, link=link, dedupe_key=dedupe_key)
    db.session.add(n)
    db.session.flush()
    return n


def generate_reminders(user_id, now=None):
    """Idempotent reminder sweep (dedupe keys prevent duplicates). Returns number created."""
    now = now or datetime.now(timezone.utc)
    created = 0
    upcoming = Application.query.filter(
        Application.user_id == user_id, Application.interview_date.isnot(None),
        Application.interview_date >= now, Application.interview_date <= now + timedelta(hours=48),
        Application.stage.in_(("assessment", "interview")),
    ).limit(20).all()
    for app in upcoming:
        when = app.interview_date if app.interview_date.tzinfo else app.interview_date.replace(tzinfo=timezone.utc)
        if notify(user_id, "interview", f"Interview soon: {app.position} at {app.company}",
                  f"Scheduled for {when.strftime('%a %d %b, %H:%M UTC')}. Practise with a mock interview.",
                  "/interview", dedupe_key=f"interview-{app.id}-{when:%Y%m%d%H%M}"):
            created += 1

    stale_cutoff = now - timedelta(days=14)
    stale = Application.query.filter(Application.user_id == user_id, Application.stage == "applied",
                                     Application.updated_at <= stale_cutoff).limit(20).all()
    for app in stale:
        if notify(user_id, "application", f"Follow up with {app.company}?",
                  f"Your application for {app.position} hasn't changed in 14+ days.", "/applications",
                  dedupe_key=f"followup-{app.id}"):
            created += 1

    old_saved = (SavedJob.query.join(SavedJob.job)
                 .filter(SavedJob.user_id == user_id, SavedJob.created_at <= now - timedelta(days=21)).limit(20).all())
    for saved in old_saved:
        if notify(user_id, "job", f"Saved job may have closed: {saved.job.title}",
                  f"You saved this {saved.job.company or ''} role 3+ weeks ago. Check whether it is still open.",
                  "/jobs?saved=1", dedupe_key=f"saved-stale-{saved.id}"):
            created += 1
    return created
