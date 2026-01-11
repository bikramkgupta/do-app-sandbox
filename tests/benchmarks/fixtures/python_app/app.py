#!/usr/bin/env python3
"""Flask benchmark app with SQLAlchemy, Pydantic, and auth libs.

This app is used to benchmark snapshot restore times. It includes
real dependencies that exercise various Python ecosystems.

Endpoints:
- GET /health - Simple health check
- GET /verify - Full verification (DB, validation, auth libs, numpy)
- POST /users - Create user (exercises full stack)
"""

import time

import bcrypt
import numpy as np
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from jose import jwt
from pydantic import BaseModel, ValidationError

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///benchmark.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# Track startup time
STARTUP_TIME = time.time()
SECRET_KEY = "benchmark-secret-key-for-testing"


class User(db.Model):
    """User model for database operations."""

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))


class UserCreate(BaseModel):
    """Pydantic model for user creation validation."""

    username: str
    password: str


@app.route("/health")
def health():
    """Simple health check endpoint."""
    return jsonify(
        {
            "status": "healthy",
            "uptime_seconds": round(time.time() - STARTUP_TIME, 2),
        }
    )


@app.route("/verify")
def verify():
    """Full verification endpoint - proves all dependencies work.

    This endpoint exercises:
    - SQLAlchemy: DB query
    - Pydantic: Validation
    - passlib: Password hashing
    - python-jose: JWT encoding
    - numpy: Array operations
    """
    try:
        # Verify SQLAlchemy DB connection
        user_count = User.query.count()

        # Verify Pydantic validation
        test_user = UserCreate(username="test", password="test123")
        pydantic_ok = test_user.username == "test"

        # Verify bcrypt hashing
        hash_result = bcrypt.hashpw(b"test", bcrypt.gensalt())
        bcrypt_ok = bcrypt.checkpw(b"test", hash_result)

        # Verify python-jose JWT
        token = jwt.encode({"sub": "test"}, SECRET_KEY, algorithm="HS256")
        decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        jose_ok = decoded["sub"] == "test"

        # Verify numpy
        arr = np.array([1, 2, 3, 4, 5])
        numpy_ok = bool(np.sum(arr) == 15)

        return jsonify(
            {
                "status": "verified",
                "db_user_count": user_count,
                "pydantic_ok": pydantic_ok,
                "bcrypt_ok": bcrypt_ok,
                "jose_ok": jose_ok,
                "numpy_ok": numpy_ok,
                "all_ok": all([pydantic_ok, bcrypt_ok, jose_ok, numpy_ok]),
                "timestamp": time.time(),
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/users", methods=["POST"])
def create_user():
    """Create a user - exercises full validation and DB stack."""
    try:
        data = UserCreate(**request.json)
        password_hash = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()
        user = User(username=data.username, password_hash=password_hash)
        db.session.add(user)
        db.session.commit()
        return jsonify({"id": user.id, "username": user.username}), 201
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Initialize database
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    print("Starting Flask benchmark app on port 5000...")
    app.run(host="0.0.0.0", port=5000, debug=False)  # noqa: S104
