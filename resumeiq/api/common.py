from flask import g, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from flask_limiter.util import get_remote_address
from pydantic import ValidationError

from ..errors import ValidationFailed, pydantic_details


def body(model):
    """Validate the JSON request body against a Pydantic model (422 on failure)."""
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValidationFailed("Request body must be a JSON object.")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ValidationFailed("Some fields are invalid.", details=pydantic_details(exc)) from exc


def pagination(default=20, maximum=100):
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(maximum, max(1, int(request.args.get("per_page", default))))
    except ValueError as exc:
        raise ValidationFailed("page and per_page must be integers.") from exc
    return page, per_page


def paginate(query, page, per_page, serialize):
    total = query.order_by(None).count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return {"items": [serialize(i) for i in items], "page": page, "per_page": per_page, "total": total,
            "pages": max(1, -(-total // per_page))}


def user_or_ip():
    """Rate-limit key: the authenticated user if any, else the client IP."""
    uid = getattr(g, "user_id", None)
    if uid is None:
        try:
            verify_jwt_in_request(optional=True)
            uid = get_jwt_identity()
        except Exception:
            uid = None
    return f"user:{uid}" if uid else f"ip:{get_remote_address()}"


def int_arg(name, default=None, minimum=None, maximum=None):
    raw = request.args.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValidationFailed(f"{name} must be an integer.") from exc
    if minimum is not None and value < minimum:
        value = minimum
    if maximum is not None and value > maximum:
        value = maximum
    return value
