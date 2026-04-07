"""Authentication — bcrypt passwords and login_required decorator."""

import functools
import bcrypt
from flask import g, jsonify, session


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def login_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Login required"}), 401
        g.user_id = user_id
        return f(*args, **kwargs)
    return wrapper
