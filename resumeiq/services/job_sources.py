"""Job data providers. Only legitimate public APIs are used, and listings are never fabricated.

* Remotive (https://remotive.com/api/remote-jobs) - public API. Their terms ask for attribution and
  infrequent requests, so results are cached (JOB_CACHE_HOURS) and each listing links back to Remotive.
* Arbeitnow (https://www.arbeitnow.com/api/job-board-api) - free public job-board API.
* Adzuna (https://developer.adzuna.com) - requires ADZUNA_APP_ID / ADZUNA_APP_KEY; also provides salary data.
"""
import html
import logging
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

import requests
from flask import current_app

from ..extensions import db
from ..models import Job, JobSkill, JobSourceFetch, utcnow
from .jd_service import SALARY_RX, detect_work_type
from .observability import record_event
from .skill_extraction import classify_requirements, extract_education_level, extract_years_required, skill_rows

log = logging.getLogger(__name__)
UA = {"User-Agent": "ResumeIQ/1.0 (career-intelligence portfolio project)"}


class _Stripper(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "tr"}

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCK:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("• ")

    def handle_data(self, data):
        self.parts.append(data)


def html_to_text(raw):
    if not raw:
        return ""
    stripper = _Stripper()
    try:
        stripper.feed(raw)
        text = "".join(stripper.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()[:20000]


def parse_salary(text):
    """Parse '$80k - $100k', '$45/hour', '€60,000' into (min, max, currency) annual integers when possible."""
    if not text:
        return None, None, None
    m = SALARY_RX.search(text)
    if not m:
        return None, None, None
    s = m.group(1)
    currency = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR"}.get(s.strip()[0])
    nums = []
    for n in re.findall(r"(\d[\d,]*(?:\.\d+)?)\s?([kK])?", s):
        value = float(n[0].replace(",", ""))
        if n[1]:
            value *= 1000
        nums.append(value)
    if not nums:
        return None, None, currency
    hourly = re.search(r"(hour|hr)", s, re.I)
    monthly = re.search(r"month", s, re.I)
    factor = 2080 if hourly else 12 if monthly else 1
    lo, hi = min(nums) * factor, max(nums) * factor
    if lo < 5000 or hi > 2_000_000:  # not a plausible annual salary
        return None, None, currency
    return int(lo), int(hi), currency


def infer_level(title, description, years):
    t = (title or "").lower()
    if re.search(r"\b(intern|internship|junior|jr\.?|entry[\s-]level|graduate|new grad|trainee|associate)\b", t):
        return "entry"
    if re.search(r"\b(senior|sr\.?|lead|principal|staff|architect|head|manager|director)\b", t):
        return "senior"
    if years is not None:
        return "entry" if years <= 2 else "mid" if years <= 5 else "senior"
    return "mid" if re.search(r"\b(mid|intermediate|ii)\b", t) else None


def _dt(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class Provider:
    name = "base"

    def enabled(self):
        return True

    def fetch(self, query, location):  # pragma: no cover - interface
        raise NotImplementedError


class RemotiveProvider(Provider):
    name = "remotive"
    URL = "https://remotive.com/api/remote-jobs"

    def fetch(self, query, location):
        params = {"limit": 100}
        if query:
            params["search"] = query
        resp = requests.get(self.URL, params=params, headers=UA, timeout=current_app.config["JOB_HTTP_TIMEOUT"])
        resp.raise_for_status()
        out = []
        for j in resp.json().get("jobs", []):
            lo, hi, cur = parse_salary(j.get("salary"))
            out.append({"external_id": str(j.get("id")), "title": j.get("title"), "company": j.get("company_name"),
                        "location": j.get("candidate_required_location") or "Remote", "work_type": "remote",
                        "employment_type": (j.get("job_type") or "").replace("_", " ") or None,
                        "salary_text": (j.get("salary") or "")[:120] or None, "salary_min": lo, "salary_max": hi,
                        "salary_currency": cur, "description": html_to_text(j.get("description")),
                        "url": j.get("url"), "posted_at": _dt(j.get("publication_date"))})
        return out


class ArbeitnowProvider(Provider):
    name = "arbeitnow"
    URL = "https://www.arbeitnow.com/api/job-board-api"

    def fetch(self, query, location):
        terms = [t for t in re.findall(r"[a-z0-9+#]+", (query or "").lower()) if len(t) > 1]
        out = []
        for page in (1, 2):
            resp = requests.get(self.URL, params={"page": page}, headers=UA, timeout=current_app.config["JOB_HTTP_TIMEOUT"])
            resp.raise_for_status()
            for j in resp.json().get("data", []):
                hay = f"{j.get('title', '')} {' '.join(j.get('tags') or [])}".lower()
                if terms and not all(t in hay for t in terms):
                    continue
                if location and location.lower() not in (j.get("location") or "").lower() and not j.get("remote"):
                    continue
                desc = html_to_text(j.get("description"))
                detected = detect_work_type(desc)
                out.append({"external_id": str(j.get("slug")), "title": j.get("title"), "company": j.get("company_name"),
                            "location": j.get("location"),
                            "work_type": "remote" if j.get("remote") else (detected if detected != "remote" else "unknown"),
                            "employment_type": ", ".join(j.get("job_types") or []) or None,
                            "salary_text": None, "salary_min": None, "salary_max": None, "salary_currency": None,
                            "description": desc, "url": j.get("url"), "posted_at": _dt(j.get("created_at"))})
        return out


class AdzunaProvider(Provider):
    name = "adzuna"

    def enabled(self):
        return bool(current_app.config.get("ADZUNA_APP_ID") and current_app.config.get("ADZUNA_APP_KEY"))

    def _base(self):
        return f"https://api.adzuna.com/v1/api/jobs/{current_app.config['ADZUNA_COUNTRY']}"

    def _auth(self):
        return {"app_id": current_app.config["ADZUNA_APP_ID"], "app_key": current_app.config["ADZUNA_APP_KEY"]}

    def currency(self):
        return {"us": "USD", "gb": "GBP", "in": "INR", "de": "EUR", "fr": "EUR", "ca": "CAD", "au": "AUD"}.get(
            current_app.config["ADZUNA_COUNTRY"])

    def fetch(self, query, location):
        params = {**self._auth(), "results_per_page": 50, "content-type": "application/json"}
        if query:
            params["what"] = query
        if location:
            params["where"] = location
        resp = requests.get(f"{self._base()}/search/1", params=params, headers=UA,
                            timeout=current_app.config["JOB_HTTP_TIMEOUT"])
        resp.raise_for_status()
        out = []
        for j in resp.json().get("results", []):
            desc = html_to_text(j.get("description"))
            out.append({"external_id": str(j.get("id")), "title": html_to_text(j.get("title")),
                        "company": (j.get("company") or {}).get("display_name"),
                        "location": (j.get("location") or {}).get("display_name"), "work_type": detect_work_type(desc),
                        "employment_type": j.get("contract_time"), "salary_text": None,
                        "salary_min": int(j["salary_min"]) if j.get("salary_min") else None,
                        "salary_max": int(j["salary_max"]) if j.get("salary_max") else None,
                        "salary_currency": self.currency(), "salary_is_predicted": str(j.get("salary_is_predicted")) == "1",
                        "description": desc, "url": j.get("redirect_url"), "posted_at": _dt(j.get("created"))})
        return out

    def histogram(self, query, location):
        params = {**self._auth(), "what": query, "content-type": "application/json"}
        if location:
            params["where"] = location
        resp = requests.get(f"{self._base()}/histogram", params=params, headers=UA,
                            timeout=current_app.config["JOB_HTTP_TIMEOUT"])
        resp.raise_for_status()
        return resp.json().get("histogram", {})


PROVIDERS = {p.name: p for p in (RemotiveProvider(), ArbeitnowProvider(), AdzunaProvider())}


def ingest(source, items, query):
    """Upsert normalised postings. Returns number of new jobs."""
    created = 0
    now = utcnow()
    for item in items:
        if not item.get("title") or not item.get("url") or not item.get("external_id"):
            continue
        if not str(item["url"]).startswith(("http://", "https://")):
            continue
        job = Job.query.filter_by(source=source, external_id=item["external_id"][:120]).first()
        is_new = job is None
        if is_new:
            job = Job(source=source, external_id=item["external_id"][:120])
            db.session.add(job)
        desc = item.get("description") or ""
        years = extract_years_required(desc)
        job.title = item["title"][:255]
        job.company = (item.get("company") or "")[:255] or None
        job.location = (item.get("location") or "")[:255] or None
        job.work_type = item.get("work_type") or "unknown"
        job.employment_type = (item.get("employment_type") or "")[:40] or None
        job.salary_min, job.salary_max = item.get("salary_min"), item.get("salary_max")
        job.salary_currency = item.get("salary_currency")
        job.salary_text = item.get("salary_text")
        job.salary_is_predicted = bool(item.get("salary_is_predicted"))
        job.description = desc
        job.url = item["url"][:1000]
        job.posted_at = item.get("posted_at") or job.posted_at or now
        job.fetched_at = now
        job.experience_min_years = years
        job.experience_level = infer_level(job.title, desc, years)
        job.education_level = extract_education_level(desc)
        job.search_terms = (query or "")[:255]
        db.session.flush()
        if is_new:
            created += 1
            required, preferred = classify_requirements(f"{job.title}\n{desc}")
            rows = skill_rows(required + preferred)
            for name, skill in rows.items():
                db.session.add(JobSkill(job_id=job.id, skill_id=skill.id,
                                        importance="preferred" if name in preferred else "required"))
    db.session.flush()
    return created


def refresh(query, location=None, force=False):
    """Fetch from enabled providers unless cached. Returns per-provider status for the UI."""
    statuses = {}
    query_key = f"{(query or '').strip().lower()}|{(location or '').strip().lower()}"[:255]
    cache_cutoff = utcnow() - timedelta(hours=current_app.config["JOB_CACHE_HOURS"])
    for name in current_app.config.get("JOB_PROVIDERS", []):
        provider = PROVIDERS.get(name)
        if provider is None:
            continue
        if not provider.enabled():
            statuses[name] = "not_configured"
            continue
        recent = JobSourceFetch.query.filter(JobSourceFetch.source == name, JobSourceFetch.query_key == query_key,
                                             JobSourceFetch.fetched_at >= cache_cutoff,
                                             JobSourceFetch.status == "ok").first()
        if recent and not force:
            statuses[name] = "cached"
            continue
        try:
            items = provider.fetch(query, location)
            new = ingest(name, items, query)
            db.session.add(JobSourceFetch(source=name, query_key=query_key, fetched_at=utcnow(), status="ok",
                                          result_count=len(items)))
            db.session.commit()
            statuses[name] = f"ok ({new} new)"
        except (requests.RequestException, ValueError) as exc:
            db.session.rollback()
            db.session.add(JobSourceFetch(source=name, query_key=query_key, fetched_at=utcnow(), status="error"))
            db.session.commit()
            record_event("job_api", f"{name}: {type(exc).__name__}", level="warning")
            log.warning("job_provider_failed", extra={"provider": name, "error_type": type(exc).__name__})
            statuses[name] = "unavailable"
    return statuses
