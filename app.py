from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
import sqlite3
import os
from datetime import datetime, timedelta
from collections import defaultdict
import time
import threading

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'mobileservice@secretkey2024')

# Use current directory for database (persistent on PythonAnywhere)
DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')

# ─── Admin Credentials ─────────────────────────────────────
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'Hashim2605')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'Hashim@123')

# ─── Firewall Configuration ─────────────────────────────────
RATE_LIMIT_WINDOW   = 60        # seconds
MAX_REQUESTS        = 60        # max requests per IP per window
MAX_LOGIN_ATTEMPTS  = 5         # max failed logins before lockout
LOGIN_LOCKOUT_TIME  = 300       # lockout duration in seconds (5 min)

# In-memory stores (thread-safe via lock)
_lock               = threading.Lock()
_request_counts     = defaultdict(list)   # ip -> [timestamps]
_login_failures     = defaultdict(list)   # ip -> [timestamps]
_blocked_ips        = {}                  # ip -> unblock_time

WHITELISTED_IPS     = {'127.0.0.1', '::1'}  # localhost always allowed

def get_client_ip():
    """Get real IP, respecting X-Forwarded-For if behind proxy."""
    xff = request.headers.get('X-Forwarded-For')
    if xff:
        return xff.split(',')[0].strip()
    return request.remote_addr or '0.0.0.0'

def is_ip_blocked(ip):
    """Return True if IP is currently blocked."""
    with _lock:
        unblock_time = _blocked_ips.get(ip)
        if unblock_time:
            if time.time() < unblock_time:
                return True
            else:
                del _blocked_ips[ip]  # expired, remove block
    return False

def block_ip(ip, duration=LOGIN_LOCKOUT_TIME):
    """Block an IP for given duration (seconds)."""
    with _lock:
        _blocked_ips[ip] = time.time() + duration

def check_rate_limit(ip):
    """Return True if request is allowed, False if rate-limited."""
    now = time.time()
    with _lock:
        # Keep only timestamps within the current window
        _request_counts[ip] = [t for t in _request_counts[ip] if now - t < RATE_LIMIT_WINDOW]
        if len(_request_counts[ip]) >= MAX_REQUESTS:
            return False
        _request_counts[ip].append(now)
    return True

def record_login_failure(ip):
    """Record a failed login attempt; block IP if threshold exceeded."""
    now = time.time()
    with _lock:
        _login_failures[ip] = [t for t in _login_failures[ip] if now - t < LOGIN_LOCKOUT_TIME]
        _login_failures[ip].append(now)
        if len(_login_failures[ip]) >= MAX_LOGIN_ATTEMPTS:
            _blocked_ips[ip] = now + LOGIN_LOCKOUT_TIME
            return True   # just got blocked
    return False

def clear_login_failures(ip):
    with _lock:
        _login_failures.pop(ip, None)

# ─── Firewall Middleware ────────────────────────────────────
@app.before_request
def firewall():
    ip = get_client_ip()

    # Always allow whitelisted IPs
    if ip in WHITELISTED_IPS:
        return

    # 1. IP block check
    if is_ip_blocked(ip):
        abort(403)

    # 2. Rate limit check
    if not check_rate_limit(ip):
        abort(429)

# ─── Database Setup ─────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id    TEXT UNIQUE NOT NULL,
            customer_name TEXT NOT NULL,
            phone_model TEXT NOT NULL,
            problem     TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'Received',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def generate_order_id():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT MAX(CAST(SUBSTR(order_id, 3) AS INTEGER)) as max_num FROM orders WHERE order_id LIKE 'MS%'")
    row = c.fetchone()
    conn.close()
    if row['max_num'] is None:
        number = 1
    else:
        number = row['max_num'] + 1
    return f"MS{1000 + number}"

# ─── Routes ─────────────────────────────────────────────────

@app.route('/', methods=['GET', 'POST'])
def login():
    if 'admin' in session:
        return redirect(url_for('admin'))
    error = None
    if request.method == 'POST':
        ip = get_client_ip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            clear_login_failures(ip)
            session['admin'] = True
            return redirect(url_for('admin'))
        else:
            just_blocked = record_login_failure(ip)
            if just_blocked:
                error = f'அதிக தவறான முயற்சிகள். உங்கள் IP {LOGIN_LOCKOUT_TIME // 60} நிமிடங்களுக்கு தடுக்கப்பட்டது.'
            else:
                error = 'Invalid username or password.'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('login'))


@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if 'admin' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    message = None

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'create':
            cname  = request.form.get('customer_name', '').strip()
            model  = request.form.get('phone_model', '').strip()
            problem = request.form.get('problem', '').strip()
            status = request.form.get('status', 'Received')

            if cname and model and problem:
                oid = generate_order_id()
                try:
                    conn.execute(
                        "INSERT INTO orders (order_id, customer_name, phone_model, problem, status) VALUES (?,?,?,?,?)",
                        (oid, cname, model, problem, status)
                    )
                    conn.commit()
                    message = {'type': 'success', 'text': f'Order {oid} created successfully!'}
                except Exception as e:
                    message = {'type': 'error', 'text': f'Error: {str(e)}'}
            else:
                message = {'type': 'error', 'text': 'Please fill all required fields.'}

    orders = conn.execute(
        "SELECT * FROM orders ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    return render_template('admin.html', orders=orders, message=message)


@app.route('/update/<int:row_id>', methods=['POST'])
def update_order(row_id):
    if 'admin' not in session:
        return redirect(url_for('login'))

    new_status = request.form.get('status')
    conn = get_db()
    conn.execute("UPDATE orders SET status=? WHERE id=?", (new_status, row_id))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))


@app.route('/delete/<int:row_id>', methods=['POST'])
def delete_order(row_id):
    if 'admin' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    conn.execute("DELETE FROM orders WHERE id=?", (row_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))


@app.route('/track', methods=['GET', 'POST'])
def track():
    # Customers only — admin session does NOT affect this page
    order = None
    not_found = False

    if request.method == 'POST':
        oid = request.form.get('order_id', '').strip().upper()
        conn = get_db()
        order = conn.execute(
            "SELECT * FROM orders WHERE UPPER(order_id)=?", (oid,)
        ).fetchone()
        conn.close()
        if not order:
            not_found = True

    return render_template('track.html', order=order, not_found=not_found)


# ─── Custom Error Pages ─────────────────────────────────────
@app.errorhandler(403)
def forbidden(e):
    return render_template('error.html',
        code=403,
        title="Access Denied",
        message="உங்கள் IP முகவரி தடுக்கப்பட்டுள்ளது. சிறிது நேரம் கழித்து முயற்சிக்கவும்."
    ), 403

@app.errorhandler(429)
def too_many_requests(e):
    return render_template('error.html',
        code=429,
        title="Too Many Requests",
        message="அதிகமான கோரிக்கைகள். சிறிது நேரம் கழித்து முயற்சிக்கவும்."
    ), 429

# ─── Initialise DB on startup (works with gunicorn too) ─────
init_db()

# ─── Run ────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True, port=5000)
