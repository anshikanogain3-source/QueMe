from datetime import datetime, timedelta, timezone
from functools import wraps

import bcrypt
import jwt
from flask import current_app, g, jsonify, request
from jwt import InvalidTokenError

from .extensions import db
from .models import SystemSetting, User


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def make_token(user: User) -> str:
    payload = {
        "sub": str(user.user_id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=current_app.config.get("JWT_EXP_HOURS", 24)),
    }
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")


def decode_token(token: str):
    return jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])


def current_user() -> User | None:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    try:
        data = decode_token(header.split(" ", 1)[1])
        user_id = int(data["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        return None
    return db.session.get(User, user_id)


def login_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return jsonify({"error": "Authentication required", "code": "unauthorized"}), 401
            if user.account_status != "ACTIVE":
                return jsonify({
                    "error": "Account is not active",
                    "code": "account_inactive",
                    "account_status": user.account_status,
                }), 403
            if roles and user.role not in roles:
                return jsonify({"error": "You do not have permission to access this resource", "code": "forbidden"}), 403
            g.user = user
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def score_weights():
    content = db.session.get(SystemSetting, "content_weight")
    delivery = db.session.get(SystemSetting, "delivery_weight")
    cw = float(content.value) if content else current_app.config.get("CONTENT_WEIGHT", 0.7)
    dw = float(delivery.value) if delivery else current_app.config.get("DELIVERY_WEIGHT", 0.3)
    return cw, dw
