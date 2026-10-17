#!/usr/bin/env bash
# SportIQ one-command installer / updater for Ubuntu or Debian.
#
#   curl -fsSL https://raw.githubusercontent.com/jerrytope/SportIQ/master/deploy/install.sh | sudo bash
#
# Safe to re-run: later runs pull the latest code, install new requirements, migrate and restart.
# It only touches SportIQ's own folder, database, service, timer and nginx site; other projects are left alone.
#
# Optional overrides (prefix the command, e.g. `sudo SEED_DEMO=no bash install.sh`):
#   DOMAIN, APP_PORT, APP_DIR, BRANCH, DB_NAME, DB_USER, SEED_DEMO (yes|no), WORKERS,
#   PG_ADMIN_URL  (only if PostgreSQL is not reachable with `sudo -u postgres psql`, e.g. it runs in Docker:
#                  postgres://postgres:PASSWORD@127.0.0.1:5432/postgres)
set -euo pipefail

DOMAIN="${DOMAIN:-nislearning.madeinafricasport.com}"
SERVER_IP="${SERVER_IP:-13.62.102.196}"
REPO="${REPO:-https://github.com/jerrytope/SportIQ.git}"
BRANCH="${BRANCH:-master}"
APP_DIR="${APP_DIR:-/opt/SportIQ}"
APP_USER="${APP_USER:-sportiq}"
APP_PORT="${APP_PORT:-8002}"
DB_NAME="${DB_NAME:-sportiq_db}"
DB_USER="${DB_USER:-sportiq_user}"
SEED_DEMO="${SEED_DEMO:-yes}"
WORKERS="${WORKERS:-3}"
SERVICE="sportiq"

say()  { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[warning] %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m[error] %s\033[0m\n' "$*" >&2; exit 1; }
as_app() { sudo -u "$APP_USER" -H "$@"; }

[ "$(id -u)" -eq 0 ] || die "Run with sudo:  curl -fsSL <url> | sudo bash"
command -v apt-get >/dev/null || die "This installer supports Ubuntu/Debian (apt) only."

# --- 0. Port checks: never take over something that already runs ---------------------------------
port_owner() { ss -ltnpH "sport = :$1" 2>/dev/null | head -1; }
if [ -n "$(port_owner "$APP_PORT")" ] && ! port_owner "$APP_PORT" | grep -q gunicorn; then
  die "Port $APP_PORT is already in use: $(port_owner "$APP_PORT"). Re-run with APP_PORT=<free port>."
fi
if [ -n "$(port_owner 80)" ] && ! port_owner 80 | grep -q nginx; then
  die "Port 80 is used by something other than nginx: $(port_owner 80). This installer configures nginx."
fi

# --- 1. System packages ---------------------------------------------------------------------------
say "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl openssl build-essential libpq-dev ffmpeg nginx certbot postgresql-client >/dev/null

PY=""
for cand in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$cand" >/dev/null && "$cand" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then PY="$cand"; break; fi
done
[ -n "$PY" ] || die "Python 3.10 or newer is required (found: $(python3 --version 2>&1)). Install python3.12 and re-run."
apt-get install -y -qq "${PY}-venv" "${PY}-dev" >/dev/null 2>&1 || apt-get install -y -qq python3-venv python3-dev >/dev/null
say "Using $($PY --version)"

# --- 2. App user and code --------------------------------------------------------------------------
id "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --home-dir "/home/$APP_USER" --shell /usr/sbin/nologin "$APP_USER"
if [ -d "$APP_DIR/.git" ]; then
  say "Updating code in $APP_DIR"
  chown -R "$APP_USER:$APP_USER" "$APP_DIR"
  as_app git -C "$APP_DIR" fetch --quiet origin "$BRANCH"
  as_app git -C "$APP_DIR" reset --quiet --hard "origin/$BRANCH"   # .env, media/ and staticfiles/ are git-ignored and kept
elif [ -e "$APP_DIR" ] && [ -n "$(ls -A "$APP_DIR" 2>/dev/null)" ]; then
  die "$APP_DIR exists and is not a git checkout. Move it away or set APP_DIR=/another/path."
else
  say "Cloning $REPO into $APP_DIR"
  mkdir -p "$APP_DIR" && chown "$APP_USER:$APP_USER" "$APP_DIR"
  as_app git clone --quiet --branch "$BRANCH" "$REPO" "$APP_DIR"
fi
mkdir -p "$APP_DIR/media" "$APP_DIR/keys" && chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod 755 "$APP_DIR"

# --- 3. Python environment -------------------------------------------------------------------------
say "Installing Python requirements (first run takes a few minutes)"
[ -x "$APP_DIR/.venv/bin/python" ] || as_app "$PY" -m venv "$APP_DIR/.venv"
as_app "$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip wheel
as_app "$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

# --- 4. Database (separate user + database in the existing PostgreSQL) -----------------------------
ENV_FILE="$APP_DIR/.env"
DB_PASS=""
if [ -f "$ENV_FILE" ]; then
  DB_PASS="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | sed -E 's#^DATABASE_URL=postgres://[^:]+:([^@]+)@.*#\1#' || true)"
fi
[ -n "$DB_PASS" ] || DB_PASS="$(openssl rand -hex 24)"

if [ -n "${PG_ADMIN_URL:-}" ]; then
  pg() { psql "$PG_ADMIN_URL" -v ON_ERROR_STOP=1 -qtAc "$1"; }
elif id postgres >/dev/null 2>&1 && sudo -u postgres psql -qtAc 'select 1' >/dev/null 2>&1; then
  pg() { sudo -u postgres psql -v ON_ERROR_STOP=1 -qtAc "$1"; }
else
  die "Can't reach PostgreSQL as admin. Re-run with PG_ADMIN_URL=postgres://postgres:PASSWORD@127.0.0.1:5432/postgres"
fi
say "Preparing PostgreSQL database '$DB_NAME' and user '$DB_USER'"
if [ "$(pg "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'")" = "1" ]; then
  pg "ALTER ROLE \"$DB_USER\" WITH LOGIN PASSWORD '$DB_PASS'" >/dev/null
else
  pg "CREATE ROLE \"$DB_USER\" WITH LOGIN PASSWORD '$DB_PASS'" >/dev/null
fi
[ "$(pg "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'")" = "1" ] || pg "CREATE DATABASE \"$DB_NAME\" OWNER \"$DB_USER\"" >/dev/null
pg "GRANT ALL PRIVILEGES ON DATABASE \"$DB_NAME\" TO \"$DB_USER\"" >/dev/null
PGPASSWORD="$DB_PASS" psql -h 127.0.0.1 -U "$DB_USER" -d "$DB_NAME" -qtAc 'select 1' >/dev/null \
  || die "Created the database but can't log in as $DB_USER over 127.0.0.1. Check pg_hba.conf allows password logins."

# --- 5. Settings (.env is created once and kept on re-runs) ---------------------------------------
if [ ! -f "$ENV_FILE" ]; then
  say "Writing $ENV_FILE"
  SECRET="$("$APP_DIR/.venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(50))')"
  FERNET="$("$APP_DIR/.venv/bin/python" -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
  cat > "$ENV_FILE" <<EOF
# SportIQ production settings (generated $(date -u +%F)). Keep this file private.
DEBUG=false
SECRET_KEY=$SECRET
ALLOWED_HOSTS=$DOMAIN,$SERVER_IP,127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=https://$DOMAIN
SITE_URL=https://$DOMAIN
DATABASE_URL=postgres://$DB_USER:$DB_PASS@127.0.0.1:5432/$DB_NAME
# Encrypts confidential integrity reports. Never change or lose it once reports exist.
INTEGRITY_ENCRYPTION_KEY=$FERNET
# Staff must use an authenticator app for the back office (set false only for a short internal pilot).
REQUIRE_STAFF_2FA=true
SESSION_IDLE_MINUTES=240
FFMPEG_BINARY=$(command -v ffmpeg)
# Emails are written to the service log until SMTP is set:  journalctl -u $SERVICE | grep -A20 Subject
# EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
# EMAIL_HOST=  EMAIL_PORT=587  EMAIL_HOST_USER=  EMAIL_HOST_PASSWORD=
# DEFAULT_FROM_EMAIL=SportIQ <no-reply@madeinafricasport.com>
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
PAYSTACK_SECRET_KEY=
PAYSTACK_PUBLIC_KEY=
EOF
else
  sed -i -E "s#^DATABASE_URL=.*#DATABASE_URL=postgres://$DB_USER:$DB_PASS@127.0.0.1:5432/$DB_NAME#" "$ENV_FILE"
fi
chown "$APP_USER:$APP_USER" "$ENV_FILE" && chmod 600 "$ENV_FILE"

# --- 6. Migrate, static files, demo data ----------------------------------------------------------
manage() { (cd "$APP_DIR" && as_app "$APP_DIR/.venv/bin/python" manage.py "$@"); }
say "Running database migrations"
manage migrate --noinput
say "Collecting static files"
manage collectstatic --noinput >/dev/null

if [ "$SEED_DEMO" = "yes" ]; then
  if [ "$(manage shell -c "from apps.accounts.models import User; print(User.objects.filter(email='learner@sportiq.test').exists())" 2>/dev/null | tail -1)" != "True" ]; then
    say "Loading demo data (about 5 minutes, includes generating demo video)"
    manage seed_demo
  else
    say "Demo data already present, skipping"
  fi
fi

# --- 7. Services: gunicorn on 127.0.0.1:$APP_PORT + daily jobs -------------------------------------
say "Installing systemd service '$SERVICE' (gunicorn on 127.0.0.1:$APP_PORT)"
cat > "/etc/systemd/system/$SERVICE.service" <<EOF
[Unit]
Description=SportIQ (NIS Digital Sports Academy)
After=network.target postgresql.service

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/gunicorn sportiq.wsgi:application --bind 127.0.0.1:$APP_PORT --workers $WORKERS --timeout 120 --access-logfile - --error-logfile -
Restart=always
RestartSec=5
UMask=0022

[Install]
WantedBy=multi-user.target
EOF
cat > "/etc/systemd/system/$SERVICE-daily.service" <<EOF
[Unit]
Description=SportIQ daily jobs (reminders, surveys, scheduled publishing, AI re-index, reports)

[Service]
Type=oneshot
User=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/python manage.py run_daily_jobs
EOF
cat > "/etc/systemd/system/$SERVICE-daily.timer" <<EOF
[Unit]
Description=Run SportIQ daily jobs at 02:30

[Timer]
OnCalendar=*-*-* 02:30:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --quiet "$SERVICE" "$SERVICE-daily.timer"
systemctl restart "$SERVICE"
systemctl start "$SERVICE-daily.timer"

# --- 8. nginx site for $DOMAIN only, with HTTPS from Let's Encrypt ---------------------------------
if [ -d /etc/nginx/sites-available ]; then
  NGINX_CONF="/etc/nginx/sites-available/$SERVICE"; NGINX_LINK="/etc/nginx/sites-enabled/$SERVICE"
else
  NGINX_CONF="/etc/nginx/conf.d/$SERVICE.conf"; NGINX_LINK=""
fi
mkdir -p /var/www/certbot
CERT="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
KEY="/etc/letsencrypt/live/$DOMAIN/privkey.pem"

app_locations() { cat <<EOF
    client_max_body_size 512M;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location /static/ { alias $APP_DIR/staticfiles/; expires 30d; access_log off; }
    location /media/  { alias $APP_DIR/media/; expires 7d; }
    location / {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 130s;
    }
EOF
}
write_nginx() {
  if [ -f "$CERT" ]; then
    cat > "$NGINX_CONF" <<EOF
server {
    listen 80;
    server_name $DOMAIN;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 301 https://\$host\$request_uri; }
}
server {
    listen 443 ssl;
    server_name $DOMAIN;
    ssl_certificate $CERT;
    ssl_certificate_key $KEY;
    ssl_protocols TLSv1.2 TLSv1.3;
$(app_locations)
}
EOF
  else
    cat > "$NGINX_CONF" <<EOF
server {
    listen 80;
    server_name $DOMAIN;
$(app_locations)
}
EOF
  fi
  [ -z "$NGINX_LINK" ] || ln -sf "$NGINX_CONF" "$NGINX_LINK"
  nginx -t -q || die "nginx configuration test failed; see 'nginx -t'. Your other sites were not reloaded."
  systemctl reload nginx 2>/dev/null || systemctl restart nginx
}
say "Configuring nginx for $DOMAIN"
systemctl enable --quiet nginx; systemctl start nginx
write_nginx
if [ ! -f "$CERT" ]; then
  say "Requesting an HTTPS certificate for $DOMAIN"
  if certbot certonly --webroot -w /var/www/certbot -d "$DOMAIN" --non-interactive --agree-tos \
       --register-unsafely-without-email --deploy-hook "systemctl reload nginx"; then
    write_nginx
  else
    warn "Could not get a certificate. Check that $DOMAIN points to $SERVER_IP and that ports 80 and 443 are open"
    warn "in the AWS security group, then re-run this command. Logging in needs HTTPS in production mode."
  fi
fi

# --- 9. Health check ----------------------------------------------------------------------------------
say "Checking the site"
sleep 3
CODE="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: $DOMAIN" -H 'X-Forwarded-Proto: https' "http://127.0.0.1:$APP_PORT/")"
if [ "$CODE" = "200" ]; then
  say "SportIQ is running:  https://$DOMAIN"
else
  warn "The app answered HTTP $CODE. See the log:  journalctl -u $SERVICE -n 80 --no-pager"
fi
cat <<EOF

  App folder     : $APP_DIR   (settings: $APP_DIR/.env)
  App server     : gunicorn on 127.0.0.1:$APP_PORT  (systemctl status $SERVICE)
  Logs / emails  : journalctl -u $SERVICE -f
  Daily jobs     : systemctl list-timers $SERVICE-daily.timer
  Database       : $DB_NAME (user $DB_USER) on 127.0.0.1:5432
  Update later   : re-run the same command
EOF
[ "$SEED_DEMO" = "yes" ] && warn "Demo accounts (incl. admin@sportiq.test) use the published password SportIQ-demo-2026. Change them or reinstall with SEED_DEMO=no before real users join."
exit 0
