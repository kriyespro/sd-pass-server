import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify, abort

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'data.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS visits (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                count INTEGER DEFAULT 0
            )
        ''')
        conn.execute('INSERT OR IGNORE INTO visits (id, count) VALUES (1, 0)')
        conn.commit()


init_db()


def increment_visits():
    with get_db() as conn:
        conn.execute('UPDATE visits SET count = count + 1 WHERE id = 1')
        conn.commit()
        row = conn.execute('SELECT count FROM visits WHERE id = 1').fetchone()
        return row['count']


@app.route('/')
def index():
    visits = increment_visits()
    with get_db() as conn:
        messages = conn.execute(
            'SELECT * FROM messages ORDER BY id DESC LIMIT 10'
        ).fetchall()
    return render_template('index.html', messages=messages, visits=visits)


@app.route('/post', methods=['POST'])
def post_message():
    name = request.form.get('name', '').strip()
    message = request.form.get('message', '').strip()
    if not name or not message:
        return redirect(url_for('index'))
    if len(name) > 50 or len(message) > 500:
        abort(400)
    with get_db() as conn:
        conn.execute(
            'INSERT INTO messages (name, message, created_at) VALUES (?, ?, ?)',
            (name, message, datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
        )
        conn.commit()
    return redirect(url_for('index'))


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/api/messages')
def api_messages():
    with get_db() as conn:
        rows = conn.execute(
            'SELECT id, name, message, created_at FROM messages ORDER BY id DESC LIMIT 20'
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/stats')
def api_stats():
    with get_db() as conn:
        count = conn.execute('SELECT COUNT(*) as c FROM messages').fetchone()['c']
        visits = conn.execute('SELECT count FROM visits WHERE id = 1').fetchone()['count']
    return jsonify({'total_messages': count, 'total_visits': visits})


@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(400)
def bad_request(e):
    return render_template('400.html'), 400


if __name__ == '__main__':
    app.run(debug=False)
