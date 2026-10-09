# KeyPortal — online account and license-key starter

Dark admin dashboard, web registration/login, a Windows desktop client, and a Flask API.

## Features
- Admin dashboard with user search, status, account creation date, and associated key prefix.
- Generate single-use or multi-use registration keys, optional expiry date, and revoke keys.
- Web and desktop registration require a valid key.
- Passwords are hashed with Werkzeug's password hashing helpers. They are never displayed.
- Full license keys are stored as HMAC digests; the raw key is shown only once at creation.
- CSRF protection for web forms, login/register rate limits, secure cookie settings, and basic security headers.

## 1. Configure and run locally
Use Python 3.11+.

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` to `.env`, then set a random `SECRET_KEY` (at least 32 characters), a strong `ADMIN_PASSWORD`, and `COOKIE_SECURE=false` for localhost HTTP testing only. Do not commit `.env`.
Generate a secret with:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Start the server:
```bash
python app.py
```
Visit `http://127.0.0.1:5000`. Sign in with the admin credentials from `.env`. Generate a key, copy it, then register a test account.

## 2. Deploy online
1. Provision a Python web service on a trusted host that supports persistent storage.
2. Upload this project from a private repository.
3. Configure environment variables in the host dashboard: `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `DATABASE_PATH` pointing to persistent storage, `COOKIE_SECURE=true`, and `APP_BASE_URL` set to your HTTPS domain.
4. Use the production start command `gunicorn --workers 2 --bind 0.0.0.0:$PORT app:app` (adapt `$PORT` syntax to your host).
5. Enable HTTPS, set up backups, restrict dashboard access, and test signup/login/key revocation before sharing it.
6. Update `API_BASE_URL` in `desktop_client.py` to the deployed HTTPS URL.

**Important:** SQLite requires a persistent disk and is best for a small single-instance deployment. For multi-instance or larger production deployments, use PostgreSQL and a managed rate-limit store. The included rate limiter uses in-memory storage and is not shared between workers; configure Redis-backed storage before scaling. Set strong secrets and rotate them carefully.

## 3. Build the Windows executable
On Windows, after editing `API_BASE_URL` and installing requirements:
```powershell
pip install pyinstaller
pyinstaller --onefile --windowed --name KeyPortal desktop_client.py
```
The executable appears at `dist\KeyPortal.exe`.

## Security notes
- The website intentionally cannot show plaintext passwords. Password hashes are not reversible.
- Treat generated registration keys like passwords; distribute them privately.
- The admin password is used only to bootstrap the first admin. Keep it secret.
- Use HTTPS in production; never expose Flask's development server directly to the public internet.
- This starter has not had a professional security audit. Before handling real users, add automated tests, backups, monitoring, email-based recovery, and production database/rate-limit configuration.
