#!/usr/bin/env bash
# One-time setup on an AWS Lightsail Ubuntu 24.04 instance (recommended: 4 GB RAM / 2 vCPU or more).
# Usage (on the server, from the project folder):  sudo bash deploy/setup_ubuntu.sh
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_USER="${SUDO_USER:-ubuntu}"

apt-get update
apt-get install -y python3 python3-venv python3-pip ffmpeg nginx unzip curl fonts-noto-cjk

# yt-dlp needs a JavaScript runtime for YouTube's player challenges
if ! command -v deno >/dev/null; then
  curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh -s -- -y
fi

# Optional: Claude Code CLI, only if you want the "server Claude Code login" mode instead of an API key
if [ "${INSTALL_CLAUDE_CLI:-0}" = "1" ]; then
  curl -fsSL https://claude.ai/install.sh | sudo -u "$APP_USER" bash
fi

cd "$APP_DIR"
sudo -u "$APP_USER" python3 -m venv .venv
sudo -u "$APP_USER" .venv/bin/pip install -q --upgrade pip
sudo -u "$APP_USER" .venv/bin/pip install -q -r requirements.txt
sudo -u "$APP_USER" mkdir -p jobs output state

if [ ! -f .env ]; then
  cp .env.example .env
  echo "ADMIN_PASSWORD=$(openssl rand -base64 18)" >> .env
  echo "ADMIN_HOST=127.0.0.1" >> .env
  chown "$APP_USER" .env; chmod 600 .env
  echo ">> .env created. Admin password:"; grep ADMIN_PASSWORD .env
fi

cat > /etc/systemd/system/autoshorts.service <<EOF
[Unit]
Description=Auto Shorts (admin + scheduler)
After=network-online.target

[Service]
User=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
Environment=PATH=$APP_DIR/.venv/bin:/usr/local/bin:/usr/bin:/bin:/home/$APP_USER/.local/bin
ExecStart=$APP_DIR/.venv/bin/python -m autoshorts.web
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/nginx/sites-available/autoshorts <<'EOF'
server {
    listen 80;
    server_name _;
    client_max_body_size 50m;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300;
    }
}
EOF
ln -sf /etc/nginx/sites-available/autoshorts /etc/nginx/sites-enabled/autoshorts
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

systemctl daemon-reload
systemctl enable --now autoshorts
systemctl status autoshorts --no-pager | head -5
echo ">> Open http://<server-ip>/ and log in. For HTTPS add a domain and run: sudo certbot --nginx"
