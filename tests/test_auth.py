import hashlib

from resumeiq.models import PasswordResetToken, TokenBlocklist, User

from .conftest import PASSWORD, register_and_login


def test_register_validates_input(app):
    c = app.test_client()
    weak = c.post("/api/auth/register", json={"full_name": "A B", "email": "a@example.com", "password": "short",
                                              "confirm_password": "short"})
    assert weak.status_code == 422
    assert any(d["field"] == "password" for d in weak.get_json()["error"]["details"])

    mismatch = c.post("/api/auth/register", json={"full_name": "A B", "email": "a@example.com", "password": "Secret123!",
                                                  "confirm_password": "Secret124!"})
    assert mismatch.status_code == 422

    bad_email = c.post("/api/auth/register", json={"full_name": "A B", "email": "not-an-email", "password": PASSWORD,
                                                   "confirm_password": PASSWORD})
    assert bad_email.status_code == 422
    assert bad_email.get_json()["error"]["details"][0]["field"] == "email"

    common = c.post("/api/auth/register", json={"full_name": "A B", "email": "a@example.com", "password": "password123",
                                                "confirm_password": "password123"})
    assert common.status_code == 422


def test_duplicate_email_is_rejected(app):
    register_and_login(app, "dup@example.com")
    r = app.test_client().post("/api/auth/register", json={"full_name": "X Y", "email": "DUP@example.com",
                                                          "password": PASSWORD, "confirm_password": PASSWORD})
    assert r.status_code == 409
    assert r.get_json()["error"]["code"] == "email_taken"


def test_password_is_hashed_with_bcrypt(app, auth):
    user = User.query.filter_by(email=auth.email).one()
    assert user.password_hash.startswith("$2b$")
    assert PASSWORD not in user.password_hash


def test_login_sets_httponly_cookies(app):
    register_and_login(app, "cookie@example.com")
    c = app.test_client()
    r = c.post("/api/auth/login", json={"email": "cookie@example.com", "password": PASSWORD})
    cookies = r.headers.getlist("Set-Cookie")
    access = next(h for h in cookies if h.startswith("access_token="))
    assert "HttpOnly" in access and "SameSite=Lax" in access
    csrf = next(h for h in cookies if h.startswith("csrf_access_token="))
    assert "HttpOnly" not in csrf  # readable by JS for double-submit


def test_wrong_password_and_unknown_email_give_same_error(app, auth):
    c = app.test_client()
    a = c.post("/api/auth/login", json={"email": auth.email, "password": "Wrong123!"})
    b = c.post("/api/auth/login", json={"email": "nobody@example.com", "password": "Wrong123!"})
    assert a.status_code == b.status_code == 401
    assert a.get_json()["error"]["message"] == b.get_json()["error"]["message"]


def test_account_locks_after_repeated_failures(app, auth):
    c = app.test_client()
    for _ in range(5):
        c.post("/api/auth/login", json={"email": auth.email, "password": "Wrong123!"})
    r = c.post("/api/auth/login", json={"email": auth.email, "password": PASSWORD})
    assert r.status_code == 429
    assert r.get_json()["error"]["code"] == "account_locked"


def test_protected_routes_require_auth(app):
    c = app.test_client()
    assert c.get("/api/resumes").status_code == 401
    assert c.get("/api/analytics/dashboard").status_code == 401
    page = c.get("/dashboard")
    assert page.status_code == 302 and "/login" in page.headers["Location"]


def test_state_changing_requests_require_csrf(auth):
    r = auth.client.put("/api/profile", json={"headline": "x"})  # no X-CSRF-TOKEN header
    assert r.status_code == 401
    assert r.get_json()["error"]["code"] == "csrf_failed"
    assert auth.put("/api/profile", json={"headline": "x"}).status_code == 200


def test_refresh_rotates_and_old_refresh_token_is_revoked(app, auth):
    old_refresh = auth.client.get_cookie("refresh_token").value
    csrf = auth.client.get_cookie("csrf_refresh_token").value
    r = auth.client.post("/api/auth/refresh", headers={"X-CSRF-TOKEN": csrf})
    assert r.status_code == 200
    assert auth.client.get_cookie("refresh_token").value != old_refresh
    # Re-using the old refresh token must fail.
    c2 = app.test_client()
    c2.set_cookie("refresh_token", old_refresh)
    c2.set_cookie("csrf_refresh_token", csrf)
    assert c2.post("/api/auth/refresh", headers={"X-CSRF-TOKEN": csrf}).status_code == 401


def test_logout_revokes_tokens(app, auth):
    access = auth.client.get_cookie("access_token").value
    assert auth.post("/api/auth/logout").status_code == 200
    assert TokenBlocklist.query.count() >= 1
    c2 = app.test_client()
    c2.set_cookie("access_token", access)
    assert c2.get("/api/auth/me").status_code == 401


def test_password_reset_flow(app, auth, monkeypatch):
    sent = {}
    monkeypatch.setattr("resumeiq.api.auth.send_password_reset", lambda user, raw: sent.update(raw=raw))
    c = app.test_client()
    r = c.post("/api/auth/forgot-password", json={"email": auth.email})
    unknown = c.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    assert r.get_json() == unknown.get_json()  # no user enumeration
    token = PasswordResetToken.query.one()
    assert token.token_hash == hashlib.sha256(sent["raw"].encode()).hexdigest()  # only the hash is stored

    r = c.post("/api/auth/reset-password", json={"token": sent["raw"], "password": "NewSecret456!", "confirm_password": "NewSecret456!"})
    assert r.status_code == 200
    # Old session is invalidated (token_version bumped) and old password no longer works.
    assert auth.get("/api/auth/me").status_code == 401
    assert c.post("/api/auth/login", json={"email": auth.email, "password": PASSWORD}).status_code == 401
    assert c.post("/api/auth/login", json={"email": auth.email, "password": "NewSecret456!"}).status_code == 200
    # Token is single-use.
    again = c.post("/api/auth/reset-password", json={"token": sent["raw"], "password": "Another789!", "confirm_password": "Another789!"})
    assert again.status_code == 400


def test_change_password_keeps_current_session_but_invalidates_others(app, auth):
    other_device = app.test_client()
    other_device.post("/api/auth/login", json={"email": auth.email, "password": PASSWORD})
    r = auth.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "Changed123!",
                                                     "confirm_password": "Changed123!"})
    assert r.status_code == 200
    assert auth.get("/api/auth/me").status_code == 200
    assert other_device.get("/api/auth/me").status_code == 401


def test_remember_me_sets_persistent_refresh_cookie(app, auth):
    c = app.test_client()
    short = c.post("/api/auth/login", json={"email": auth.email, "password": PASSWORD, "remember_me": False})
    long = c.post("/api/auth/login", json={"email": auth.email, "password": PASSWORD, "remember_me": True})
    refresh_short = next(h for h in short.headers.getlist("Set-Cookie") if h.startswith("refresh_token="))
    refresh_long = next(h for h in long.headers.getlist("Set-Cookie") if h.startswith("refresh_token="))
    assert "Max-Age" not in refresh_short
    assert "Max-Age" in refresh_long
