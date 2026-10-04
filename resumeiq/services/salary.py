"""Salary insights. DATA (real postings / Adzuna) is kept strictly separate from AI INTERPRETATION."""
import re
import statistics
import time
from collections import Counter

from flask import current_app
import requests

from ..models import Job
from .ai import SYSTEM_GUARDRAILS, AIUnavailable, get_ai
from .ai.schemas import SalaryInterpretation
from .job_sources import PROVIDERS
from .skill_extraction import resolve_role

MIN_SAMPLE = 5
_hist_cache = {}


def _quantiles(values):
    values = sorted(values)
    if len(values) == 1:
        return values[0], values[0], values[0]
    q = statistics.quantiles(values, n=4, method="inclusive")
    return int(q[0]), int(statistics.median(values)), int(q[2])


def posting_data(role, location=None, experience_level=None, company=None):
    q = Job.query.filter((Job.salary_min.isnot(None)) | (Job.salary_max.isnot(None)))
    if location:
        q = q.filter(Job.location.ilike(f"%{location}%"))
    if company:
        q = q.filter(Job.company.ilike(f"%{company}%"))
    jobs = q.order_by(Job.posted_at.desc().nullslast()).limit(2000).all()
    role_name = resolve_role(role)
    terms = [t for t in re.findall(r"[a-z]+", (role or "").lower()) if len(t) > 2]
    jobs = [j for j in jobs if (role_name and resolve_role(j.title) == role_name) or
            (terms and all(t in j.title.lower() for t in terms))]
    if not jobs:
        return {"levels": {}, "sample_size": 0, "currency": None, "sources": [], "date_range": None,
                "predicted_share": 0}
    currency = Counter(j.salary_currency for j in jobs if j.salary_currency).most_common(1)
    currency = currency[0][0] if currency else None
    jobs = [j for j in jobs if j.salary_currency == currency]
    levels = {}
    for level in ("entry", "mid", "senior"):
        if experience_level and level != experience_level:
            continue
        mids = [((j.salary_min or j.salary_max) + (j.salary_max or j.salary_min)) / 2 for j in jobs if j.experience_level == level]
        if len(mids) >= MIN_SAMPLE:
            p25, med, p75 = _quantiles(mids)
            levels[level] = {"n": len(mids), "p25": p25, "median": med, "p75": p75, "sufficient": True}
        else:
            levels[level] = {"n": len(mids), "sufficient": False}
    dates = [j.posted_at for j in jobs if j.posted_at]
    return {
        "levels": levels, "sample_size": len(jobs), "currency": currency,
        "sources": sorted({Job.SOURCE_LABELS.get(j.source, j.source) for j in jobs}),
        "date_range": {"from": min(dates).date().isoformat(), "to": max(dates).date().isoformat()} if dates else None,
        "predicted_share": round(sum(1 for j in jobs if j.salary_is_predicted) / len(jobs), 2),
        "unclassified_level": sum(1 for j in jobs if not j.experience_level),
    }


def adzuna_histogram(role, location=None):
    provider = PROVIDERS["adzuna"]
    if not provider.enabled():
        return {"available": False, "reason": "Adzuna API keys are not configured."}
    key = (role.lower(), (location or "").lower())
    cached = _hist_cache.get(key)
    if cached and time.time() - cached[0] < current_app.config["JOB_CACHE_HOURS"] * 3600:
        return cached[1]
    try:
        hist = provider.histogram(role, location)
    except requests.RequestException:
        return {"available": False, "reason": "Adzuna is temporarily unavailable."}
    buckets = sorted((int(k), int(v)) for k, v in hist.items())
    result = {"available": True, "currency": provider.currency(), "buckets": [{"from": k, "count": v} for k, v in buckets],
              "total": sum(v for _, v in buckets), "fetched_at": time.strftime("%Y-%m-%d", time.gmtime()),
              "source": "Adzuna salary histogram (live job adverts)"}
    _hist_cache[key] = (time.time(), result)
    return result


def insights(role, location=None, experience_level=None, company=None):
    return {"role": role, "filters": {"location": location, "experience_level": experience_level, "company": company},
            "postings": posting_data(role, location, experience_level, company),
            "adzuna": adzuna_histogram(role, location),
            "method_note": "Ranges are computed from salaries stated in real job postings we've stored (midpoint of each "
                           "posting's range), grouped by seniority inferred from the title/years required. Levels with "
                           f"fewer than {MIN_SAMPLE} postings are not reported."}


def interpret(user_id, data):
    try:
        res = get_ai().generate(
            service="salary_interpretation", user_id=user_id, schema=SalaryInterpretation, system=SYSTEM_GUARDRAILS,
            temperature=0.3,
            prompt=("Interpret ONLY the following salary data for a job seeker. Do not introduce outside salary figures. "
                    "Point out sample-size limitations and what the data can and cannot tell them.\n\n" + str(data)[:6000]))
        return {"available": True, **res.model_dump()}
    except AIUnavailable as exc:
        return {"available": False, "reason": exc.user_message}
