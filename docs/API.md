# REST API

A machine-readable index of every route is served at **`GET /api/docs`** (generated from the URL map, so it
never drifts from the code).

## Conventions

- **Auth:** sign in with `POST /api/auth/login`, which sets HTTP-only cookies. On `POST/PUT/PATCH/DELETE`, send the
  header `X-CSRF-TOKEN` with the value of the `csrf_access_token` cookie. When an access token expires the API
  returns `401 {"error":{"code":"token_expired"}}`. Call `POST /api/auth/refresh` (CSRF: `csrf_refresh_token`)
  and retry.
- **Errors:** `{"error": {"code": "...", "message": "...", "details": [...], "request_id": "..."}}`.
  Status codes: `400` bad input · `401` unauthenticated · `403` forbidden · `404` not found (also for other
  users' resources) · `409` conflict · `413` too large · `422` validation · `429` rate limited · `503` dependency down.
- **Pagination:** `?page=1&per_page=20`, returning `{items, page, per_page, total, pages}`.

## Endpoints

| Area | Method & path | Purpose |
|---|---|---|
| Auth | `POST /api/auth/register` · `login` · `refresh` · `logout` · `forgot-password` · `reset-password` · `change-password`, `GET /api/auth/me` | Accounts and sessions |
| Users | `GET/PATCH/DELETE /api/users/me`, `GET /api/users/me/export` | Account, deletion, data export |
| Profile | `GET/PUT /api/profile`, `POST/GET/DELETE /api/profile/avatar`, `POST/PUT/DELETE /api/profile/{goals,education,experience,projects,certifications}[/<id>]`, `POST/DELETE /api/profile/skills` | Career profile |
| Resumes | `GET/POST /api/resumes`, `GET/PATCH/DELETE /api/resumes/<id>`, `POST /api/resumes/<id>/primary`, `POST /api/resumes/<id>/versions`, `GET/DELETE /api/resumes/versions/<vid>`, `GET /api/resumes/versions/<vid>/download`, `GET /api/resumes/compare?from=&to=` | Storage and versioning |
| Analysis | `POST /api/analysis` (202 + task), `GET /api/tasks/<id>`, `GET/DELETE /api/analysis[/<id>]`, `POST /api/analysis/ats`, `POST /api/analysis/improve`, `POST /api/analysis/tips` | Scoring, ATS, improvement |
| Job descriptions | `GET/POST /api/job-descriptions`, `GET/DELETE /api/job-descriptions/<id>` | JD analyzer |
| Jobs | `GET /api/jobs` (filters: `q, location, work_type, salary_min, experience_level, company, skills, posted_within, saved, sort`), `GET /api/jobs/<id>`, `POST/DELETE /api/jobs/<id>/save`, `POST /api/jobs/<id>/apply` | Search and actions |
| Matches | `GET /api/matches`, `GET /api/matches/<job_id>` | Explained match scores |
| Salary | `GET /api/salary`, `POST /api/salary/interpret` | Data vs AI interpretation |
| Skills | `GET /api/skills`, `GET /api/skills/gap?role=`, `GET /api/skills/graph?role=`, `GET /api/skills/detail?name=` | Gap analysis and graph |
| Roadmap | `GET/POST /api/roadmap`, `PATCH /api/roadmap/items/<id>`, `GET /api/roadmap/projects` | Plan and projects |
| Learning | `GET /api/learning/resources`, `PUT /api/learning/progress/<resource_id>`, `GET /api/learning/progress`, `GET /api/learning/stats`, `POST /api/learning/projects` | Tracker |
| Interview | `GET/POST /api/interview/sessions`, `GET/DELETE /api/interview/sessions/<id>`, `POST .../answers`, `POST .../finish` | Prep and mock interviews |
| Applications | `GET/POST /api/applications`, `GET/PATCH/DELETE /api/applications/<id>`, `POST /api/applications/<id>/move` | Kanban tracker |
| Cover letters | `GET/POST /api/cover-letter`, `GET/PUT/DELETE /api/cover-letter/<id>` | Generator |
| Analytics | `GET /api/analytics/{dashboard,applications,insights,charts}` | Dashboards |
| Notifications | `GET /api/notifications`, `GET /api/notifications/unread-count`, `POST .../<id>/read`, `POST .../read-all`, `DELETE .../<id>` | Inbox |
| Search | `GET /api/search?q=` | Global search |
| Admin | `GET /api/admin/overview`, `GET /api/admin/users`, `PATCH /api/admin/users/<id>` | Aggregates only |
| Health | `GET /health` → `{"status": "healthy"}` (503 if the DB is down), `GET /health/live` | Probes |

## Example: analyse a resume

```bash
# 1. sign in (stores cookies in jar)
curl -c jar -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"Secret123!"}' http://localhost:5000/api/auth/login
CSRF=$(grep csrf_access_token jar | awk '{print $7}')

# 2. upload
curl -b jar -H "X-CSRF-TOKEN: $CSRF" -F resume=@resume.pdf http://localhost:5000/api/resumes

# 3. start the analysis, then poll the task
curl -b jar -H "X-CSRF-TOKEN: $CSRF" -H 'Content-Type: application/json' \
  -d '{"resume_version_id":1,"target_role":"Backend Developer"}' http://localhost:5000/api/analysis
curl -b jar http://localhost:5000/api/tasks/<task_id>
```
