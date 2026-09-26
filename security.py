import hashlib
import os
from pathlib import Path
import re
import secrets
from datetime import datetime, timedelta

from flask import abort, current_app, request, session
from database.db import get_db


def configure_security(app):
    secret = os.environ.get('ASSUREX_SECRET_KEY')
    if not secret:
        path = Path(app.root_path) / 'instance' / 'secret.key'
        path.parent.mkdir(exist_ok=True)
        try:
            with path.open('x', encoding='utf-8') as handle:
                handle.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        secret = path.read_text(encoding='utf-8').strip()
    app.secret_key = secret
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=os.environ.get('ASSUREX_HTTPS') == '1',
                      MAX_CONTENT_LENGTH=12 * 1024 * 1024,
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=8))

    def csrf_token():
        if '_csrf' not in session:
            session['_csrf'] = secrets.token_urlsafe(32)
        return session['_csrf']
    app.jinja_env.globals['csrf_token'] = csrf_token

    @app.before_request
    def protect_request():
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            supplied = request.form.get('_csrf', '')
            if not supplied or not secrets.compare_digest(supplied, session.get('_csrf', '')):
                abort(400, 'Your form expired. Reload the page and try again.')
        if session.get('user_id'):
            db = get_db()
            user = db.execute('SELECT role FROM users WHERE id=?', (session['user_id'],)).fetchone()
            db.close()
            if not user:
                session.clear()
            else:
                session['role'] = user['role']
        if request.method == 'POST' and request.endpoint in ('register', 'profile'):
            email = request.form.get('email', '').strip()
            if len(email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
                abort(400, 'Enter a valid email address.')
        if request.endpoint == 'login' and request.method == 'POST':
            subject = login_subject()
            since = (datetime.now() - timedelta(minutes=15)).isoformat(timespec='seconds')
            db = get_db()
            count = db.execute("SELECT COUNT(*) FROM security_events WHERE event='login failure' AND subject=? AND created_at>?", (subject, since)).fetchone()[0]
            db.close()
            if count >= 8:
                abort(429, 'Too many failed sign-in attempts. Try again in 15 minutes.')

    @app.after_request
    def headers(response):
        if request.endpoint == 'login' and request.method == 'POST' and response.status_code == 200 and not session.get('user_id'):
            security_event('login failure', login_subject())
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Referrer-Policy'] = 'same-origin'
        if session.get('user_id'):
            response.headers['Cache-Control'] = 'no-store'
        return response


def login_subject():
    return hashlib.sha256(request.form.get('email', '').strip().lower().encode()).hexdigest()


def security_event(event, subject):
    db = get_db()
    try:
        db.execute('INSERT INTO security_events(event,subject,created_at) VALUES(?,?,?)',
                   (event, str(subject), datetime.now().isoformat(timespec='seconds')))
        db.commit()
    finally:
        db.close()
