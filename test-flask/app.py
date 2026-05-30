from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'crm-secret-key-2024'

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')

ADMIN_ID = 'admin'
ADMIN_PASSWORD = 'durga123@'


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            company TEXT,
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            source TEXT,
            status TEXT DEFAULT 'New',
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            contact_name TEXT,
            value REAL DEFAULT 0,
            stage TEXT DEFAULT 'Prospecting',
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    conn.commit()
    conn.close()


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


# --- Public routes ---

@app.route('/')
def index():
    conn = get_db()
    stats = {
        'contacts': conn.execute('SELECT COUNT(*) FROM contacts').fetchone()[0],
        'leads': conn.execute('SELECT COUNT(*) FROM leads').fetchone()[0],
        'deals': conn.execute('SELECT COUNT(*) FROM deals').fetchone()[0],
        'revenue': conn.execute("SELECT COALESCE(SUM(value),0) FROM deals WHERE stage='Won'").fetchone()[0],
        'new_leads': conn.execute("SELECT COUNT(*) FROM leads WHERE status='New'").fetchone()[0],
        'open_deals': conn.execute("SELECT COUNT(*) FROM deals WHERE stage NOT IN ('Won','Lost')").fetchone()[0],
    }
    recent_leads = conn.execute('SELECT * FROM leads ORDER BY created_at DESC LIMIT 5').fetchall()
    recent_deals = conn.execute('SELECT * FROM deals ORDER BY created_at DESC LIMIT 5').fetchall()
    conn.close()
    return render_template('index.html', stats=stats, recent_leads=recent_leads, recent_deals=recent_deals)


@app.route('/contacts', methods=['GET', 'POST'])
def contacts():
    conn = get_db()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        company = request.form.get('company', '').strip()
        notes = request.form.get('notes', '').strip()
        if name:
            conn.execute(
                'INSERT INTO contacts (name, email, phone, company, notes) VALUES (?,?,?,?,?)',
                (name, email, phone, company, notes)
            )
            conn.commit()
        conn.close()
        return redirect(url_for('contacts'))
    rows = conn.execute('SELECT * FROM contacts ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('contacts.html', contacts=rows)


@app.route('/contacts/<int:cid>/delete', methods=['POST'])
def delete_contact(cid):
    conn = get_db()
    conn.execute('DELETE FROM contacts WHERE id=?', (cid,))
    conn.commit()
    conn.close()
    return redirect(url_for('contacts'))


@app.route('/leads', methods=['GET', 'POST'])
def leads():
    conn = get_db()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        source = request.form.get('source', '').strip()
        notes = request.form.get('notes', '').strip()
        if name:
            conn.execute(
                'INSERT INTO leads (name, email, phone, source, notes) VALUES (?,?,?,?,?)',
                (name, email, phone, source, notes)
            )
            conn.commit()
        conn.close()
        return redirect(url_for('leads'))
    status_filter = request.args.get('status', '')
    if status_filter:
        rows = conn.execute('SELECT * FROM leads WHERE status=? ORDER BY created_at DESC', (status_filter,)).fetchall()
    else:
        rows = conn.execute('SELECT * FROM leads ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('leads.html', leads=rows, status_filter=status_filter)


@app.route('/leads/<int:lid>/status', methods=['POST'])
def update_lead_status(lid):
    new_status = request.form.get('status')
    if new_status in ('New', 'Contacted', 'Qualified', 'Lost'):
        conn = get_db()
        conn.execute('UPDATE leads SET status=? WHERE id=?', (new_status, lid))
        conn.commit()
        conn.close()
    return redirect(url_for('leads'))


@app.route('/leads/<int:lid>/delete', methods=['POST'])
def delete_lead(lid):
    conn = get_db()
    conn.execute('DELETE FROM leads WHERE id=?', (lid,))
    conn.commit()
    conn.close()
    return redirect(url_for('leads'))


@app.route('/deals', methods=['GET', 'POST'])
def deals():
    conn = get_db()
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        contact_name = request.form.get('contact_name', '').strip()
        value = request.form.get('value', '0').strip() or '0'
        stage = request.form.get('stage', 'Prospecting')
        notes = request.form.get('notes', '').strip()
        if title:
            conn.execute(
                'INSERT INTO deals (title, contact_name, value, stage, notes) VALUES (?,?,?,?,?)',
                (title, contact_name, float(value), stage, notes)
            )
            conn.commit()
        conn.close()
        return redirect(url_for('deals'))
    stage_filter = request.args.get('stage', '')
    if stage_filter:
        rows = conn.execute('SELECT * FROM deals WHERE stage=? ORDER BY created_at DESC', (stage_filter,)).fetchall()
    else:
        rows = conn.execute('SELECT * FROM deals ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('deals.html', deals=rows, stage_filter=stage_filter)


@app.route('/deals/<int:did>/stage', methods=['POST'])
def update_deal_stage(did):
    new_stage = request.form.get('stage')
    if new_stage in ('Prospecting', 'Proposal', 'Negotiation', 'Won', 'Lost'):
        conn = get_db()
        conn.execute('UPDATE deals SET stage=? WHERE id=?', (new_stage, did))
        conn.commit()
        conn.close()
    return redirect(url_for('deals'))


@app.route('/deals/<int:did>/delete', methods=['POST'])
def delete_deal(did):
    conn = get_db()
    conn.execute('DELETE FROM deals WHERE id=?', (did,))
    conn.commit()
    conn.close()
    return redirect(url_for('deals'))


# --- Admin routes ---

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        uid = request.form.get('username', '').strip()
        pwd = request.form.get('password', '').strip()
        if uid == ADMIN_ID and pwd == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        error = 'Invalid credentials'
    return render_template('admin_login.html', error=error)


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))


@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    conn = get_db()
    all_contacts = conn.execute('SELECT * FROM contacts ORDER BY created_at DESC').fetchall()
    all_leads = conn.execute('SELECT * FROM leads ORDER BY created_at DESC').fetchall()
    all_deals = conn.execute('SELECT * FROM deals ORDER BY created_at DESC').fetchall()
    stats = {
        'contacts': len(all_contacts),
        'leads': len(all_leads),
        'deals': len(all_deals),
        'total_revenue': conn.execute("SELECT COALESCE(SUM(value),0) FROM deals WHERE stage='Won'").fetchone()[0],
        'pipeline_value': conn.execute("SELECT COALESCE(SUM(value),0) FROM deals WHERE stage NOT IN ('Won','Lost')").fetchone()[0],
        'lost_deals': conn.execute("SELECT COUNT(*) FROM deals WHERE stage='Lost'").fetchone()[0],
    }
    conn.close()
    return render_template('admin_dashboard.html', contacts=all_contacts, leads=all_leads, deals=all_deals, stats=stats)


@app.route('/health')
def health():
    return {'status': 'ok', 'app': 'CRM — StudentCloud Flask'}


init_db()
