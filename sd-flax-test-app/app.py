from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import os
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = "sd_leads_secret_key_2026"

DB_PATH = "leads.db"

ADMIN_ID = "admin"
ADMIN_PASSWORD = "durga123@"


# ──────────────────────────────────────────
# DB INIT
# ──────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                email      TEXT NOT NULL,
                phone      TEXT,
                message    TEXT,
                source     TEXT DEFAULT 'website',
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()


# ──────────────────────────────────────────
# AUTH DECORATOR
# ──────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


# ──────────────────────────────────────────
# PUBLIC: LANDING PAGE (Lead Form)
# ──────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    success = request.args.get("success")
    return render_template("index.html", success=success)


@app.route("/submit-lead", methods=["POST"])
def submit_lead():
    name    = request.form.get("name", "").strip()
    email   = request.form.get("email", "").strip()
    phone   = request.form.get("phone", "").strip()
    message = request.form.get("message", "").strip()

    if not name or not email:
        return redirect(url_for("index"))

    with get_db() as conn:
        conn.execute(
            "INSERT INTO leads (name, email, phone, message, source, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (name, email, phone, message, "website", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()

    return redirect(url_for("index", success=1))


# ──────────────────────────────────────────
# ADMIN: LOGIN
# ──────────────────────────────────────────
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        uid  = request.form.get("username", "")
        pwd  = request.form.get("password", "")
        if uid == ADMIN_ID and pwd == ADMIN_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        else:
            error = "Invalid credentials. Please try again."
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


# ──────────────────────────────────────────
# ADMIN: DASHBOARD
# ──────────────────────────────────────────
@app.route("/admin")
@login_required
def admin_dashboard():
    search = request.args.get("q", "").strip()
    page   = int(request.args.get("page", 1))
    per_page = 10

    with get_db() as conn:
        total_leads = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        today_leads = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE DATE(created_at) = DATE('now')"
        ).fetchone()[0]

        if search:
            base_q = "FROM leads WHERE name LIKE ? OR email LIKE ? OR phone LIKE ?"
            params = [f"%{search}%", f"%{search}%", f"%{search}%"]
        else:
            base_q = "FROM leads"
            params = []

        count_row = conn.execute(f"SELECT COUNT(*) {base_q}", params).fetchone()[0]
        offset    = (page - 1) * per_page

        leads = conn.execute(
            f"SELECT * {base_q} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [per_page, offset]
        ).fetchall()

    total_pages = (count_row + per_page - 1) // per_page

    return render_template(
        "admin_dashboard.html",
        leads=leads,
        total_leads=total_leads,
        today_leads=today_leads,
        search=search,
        page=page,
        total_pages=total_pages,
        count_row=count_row,
    )


# ──────────────────────────────────────────
# ADMIN: DELETE LEAD
# ──────────────────────────────────────────
@app.route("/admin/delete/<int:lead_id>", methods=["POST"])
@login_required
def delete_lead(lead_id):
    with get_db() as conn:
        conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        conn.commit()
    return redirect(url_for("admin_dashboard"))


# ──────────────────────────────────────────
# ADMIN: EXPORT CSV
# ──────────────────────────────────────────
@app.route("/admin/export")
@login_required
def export_leads():
    import csv
    import io
    from flask import Response

    with get_db() as conn:
        leads = conn.execute("SELECT * FROM leads ORDER BY id DESC").fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Name", "Email", "Phone", "Message", "Source", "Created At"])
    for lead in leads:
        writer.writerow([lead["id"], lead["name"], lead["email"],
                         lead["phone"], lead["message"], lead["source"], lead["created_at"]])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"}
    )


# ──────────────────────────────────────────
# RUN
# ──────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5050)
