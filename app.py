import os
import hmac
import hashlib
import secrets
import sqlite3
from datetime import datetime, timezone
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", ""),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "true").lower() == "true",
    WTF_CSRF_TIME_LIMIT=3600,
)
if len(app.config["SECRET_KEY"]) < 32:
    raise RuntimeError("Set SECRET_KEY to a random value of at least 32 characters.")
DB_PATH = os.environ.get("DATABASE_PATH", "keyportal.sqlite3")
csrf = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, default_limits=["300 per hour"], storage_uri="memory://")

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_disabled INTEGER NOT NULL DEFAULT 0,
            is_admin INTEGER NOT NULL DEFAULT 0,
            key_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS license_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash TEXT NOT NULL UNIQUE,
            key_prefix TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            expires_at TEXT,
            max_uses INTEGER NOT NULL DEFAULT 1,
            uses INTEGER NOT NULL DEFAULT 0,
            revoked INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
        """)
        admin_name = os.environ.get("ADMIN_USERNAME", "").strip()
        admin_password = os.environ.get("ADMIN_PASSWORD", "")
        if admin_name and admin_password and not c.execute("SELECT 1 FROM users WHERE is_admin=1").fetchone():
            c.execute(
                "INSERT INTO users(username,password_hash,created_at,is_admin) VALUES(?,?,?,1)",
                (admin_name, generate_password_hash(admin_password), now()),
            )

def key_digest(raw):
    pepper = app.config["SECRET_KEY"].encode()
    return hmac.new(pepper, raw.encode(), hashlib.sha256).hexdigest()

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        with db() as c:
            row = c.execute("SELECT is_admin,is_disabled FROM users WHERE id=?", (session["user_id"],)).fetchone()
        if not row or not row["is_admin"] or row["is_disabled"]:
            abort(403)
        return fn(*args, **kwargs)
    return wrapped

@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
    return response

@app.get("/")
def home():
    return redirect(url_for("dashboard") if session.get("user_id") else url_for("login"))

@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with db() as c:
            user = c.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,)).fetchone()
        if user and not user["is_disabled"] and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("admin_dashboard") if user["is_admin"] else url_for("dashboard"))
        flash("Invalid username or password.")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
@limiter.limit("8 per minute")
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        raw_key = request.form.get("license_key", "").strip()
        if not (3 <= len(username) <= 32) or not all(ch.isalnum() or ch in "_-" for ch in username):
            flash("Username must be 3–32 characters and use only letters, numbers, _ or -.")
        elif len(password) < 12:
            flash("Use a password with at least 12 characters.")
        elif not raw_key:
            flash("A registration key is required.")
        else:
            try:
                with db() as c:
                    key = c.execute("SELECT * FROM license_keys WHERE key_hash=?", (key_digest(raw_key),)).fetchone()
                    if not key or key["revoked"] or key["uses"] >= key["max_uses"] or (key["expires_at"] and key["expires_at"] <= now()):
                        flash("That registration key is invalid, expired, revoked, or already used.")
                    else:
                        c.execute("INSERT INTO users(username,password_hash,created_at,key_id) VALUES(?,?,?,?)",
                                  (username, generate_password_hash(password), now(), key["id"]))
                        c.execute("UPDATE license_keys SET uses=uses+1 WHERE id=?", (key["id"],))
                        flash("Account created. You can now log in.")
                        return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("That username is already taken.")
    return render_template("register.html")

@app.get("/dashboard")
@login_required
def dashboard():
    with db() as c:
        user = c.execute("""SELECT u.username,u.created_at,u.is_disabled,k.key_prefix,k.label,k.expires_at
                            FROM users u LEFT JOIN license_keys k ON u.key_id=k.id WHERE u.id=?""",
                         (session["user_id"],)).fetchone()
    if not user or user["is_disabled"]:
        session.clear()
        return redirect(url_for("login"))
    if user["key_prefix"] is None:
        key_text = "Administrator account"
    else:
        key_text = user["key_prefix"] + "••••••••"
    return render_template("dashboard.html", user=user, key_text=key_text)

@app.get("/admin")
@admin_required
def admin_dashboard():
    q = request.args.get("q", "").strip()[:80]
    with db() as c:
        users = c.execute("""SELECT u.id,u.username,u.created_at,u.is_disabled,u.is_admin,
                             k.key_prefix,k.label,k.expires_at
                             FROM users u LEFT JOIN license_keys k ON u.key_id=k.id
                             WHERE u.username LIKE ? ORDER BY u.id DESC LIMIT 250""", (f"%{q}%",)).fetchall()
        keys = c.execute("SELECT * FROM license_keys ORDER BY id DESC LIMIT 250").fetchall()
        stats = {
            "users": c.execute("SELECT COUNT(*) FROM users WHERE is_admin=0").fetchone()[0],
            "keys": c.execute("SELECT COUNT(*) FROM license_keys").fetchone()[0],
            "available": c.execute("SELECT COUNT(*) FROM license_keys WHERE revoked=0 AND uses<max_uses AND (expires_at IS NULL OR expires_at>?)", (now(),)).fetchone()[0],
        }
    return render_template("admin.html", users=users, keys=keys, stats=stats, q=q)

@app.post("/admin/keys/create")
@admin_required
def create_key():
    label = request.form.get("label", "").strip()[:80]
    try:
        max_uses = int(request.form.get("max_uses", "1"))
        if not 1 <= max_uses <= 10000:
            raise ValueError()
    except ValueError:
        flash("Maximum uses must be between 1 and 10000.")
        return redirect(url_for("admin_dashboard"))
    expiry_date = request.form.get("expires_at", "").strip()
    expires_at = expiry_date + "T23:59:59+00:00" if expiry_date else None
    raw = "KP-" + secrets.token_urlsafe(24)
    with db() as c:
        c.execute("INSERT INTO license_keys(key_hash,key_prefix,label,created_at,expires_at,max_uses) VALUES(?,?,?,?,?,?)",
                  (key_digest(raw), raw[:9], label, now(), expires_at, max_uses))
    flash("New key (copy it now; it cannot be shown again): " + raw)
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/keys/<int:key_id>/revoke")
@admin_required
def revoke_key(key_id):
    with db() as c:
        c.execute("UPDATE license_keys SET revoked=1 WHERE id=?", (key_id,))
    flash("Key revoked.")
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/users/<int:user_id>/toggle")
@admin_required
def toggle_user(user_id):
    if user_id == session["user_id"]:
        flash("You cannot disable your own admin account.")
    else:
        with db() as c:
            c.execute("UPDATE users SET is_disabled=CASE is_disabled WHEN 1 THEN 0 ELSE 1 END WHERE id=? AND is_admin=0", (user_id,))
        flash("Account status updated.")
    return redirect(url_for("admin_dashboard"))

@app.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))

# JSON API for desktop clients. Registration is still validated server-side.
@csrf.exempt
@app.post("/api/register")
@limiter.limit("8 per minute")
def api_register():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    raw_key = str(data.get("license_key", "")).strip()
    if not (3 <= len(username) <= 32) or not all(ch.isalnum() or ch in "_-" for ch in username):
        return jsonify(error="Invalid username format."), 400
    if len(password) < 12:
        return jsonify(error="Password must be at least 12 characters."), 400
    if not raw_key:
        return jsonify(error="Registration key is required."), 400
    try:
        with db() as c:
            key = c.execute("SELECT * FROM license_keys WHERE key_hash=?", (key_digest(raw_key),)).fetchone()
            if not key or key["revoked"] or key["uses"] >= key["max_uses"] or (key["expires_at"] and key["expires_at"] <= now()):
                return jsonify(error="Registration key is invalid, expired, revoked, or already used."), 400
            c.execute("INSERT INTO users(username,password_hash,created_at,key_id) VALUES(?,?,?,?)",
                      (username, generate_password_hash(password), now(), key["id"]))
            c.execute("UPDATE license_keys SET uses=uses+1 WHERE id=?", (key["id"],))
        return jsonify(message="Account created. You can now log in."), 201
    except sqlite3.IntegrityError:
        return jsonify(error="Username already exists."), 409

@csrf.exempt
@app.post("/api/login")
@limiter.limit("10 per minute")
def api_login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    with db() as c:
        user = c.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,)).fetchone()
    if not user or user["is_disabled"] or not check_password_hash(user["password_hash"], password):
        return jsonify(error="Invalid username or password."), 401
    return jsonify(message="Login successful.", username=user["username"])

init_db()

if __name__ == "__main__":
    # For local testing only. Use HTTPS and a production WSGI server for deployment.
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
