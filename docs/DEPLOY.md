# Deployment on 109.199.127.99

Verqac runs in Docker next to Mahami on the same server. It uses its own PostgreSQL
container, its own volume and only two local ports (8300 API, 8301 web), so it does not
touch Mahami's database, files or Nginx sites.

## 1. DNS

At the registrar of verqac.com add an A record: `app` → `109.199.127.99`.
(Later: `verqac.com` and `www` for the marketing site.)

## 2. Docker (once)

```bash
docker --version && docker compose version
# if missing: curl -fsSL https://get.docker.com | sh
```

## 3. Code and secrets

```bash
mkdir -p /opt/verqac && cd /opt/verqac
git clone git@github.com:mustafa-mahami/verqac.git .
cp .env.example .env
# fill .env: three different passwords, and VERQAC_JWT_SECRET from:
openssl rand -hex 32
chmod 600 .env
```

## 4. Start

```bash
docker compose up -d --build
docker compose ps                      # db healthy, migrate exited 0, api and web up
curl -s http://127.0.0.1:8300/api/health
```

## 5. Nginx and certificate

```bash
cp deploy/nginx/verqac.conf /etc/nginx/sites-available/verqac
ln -s /etc/nginx/sites-available/verqac /etc/nginx/sites-enabled/verqac
nginx -t && systemctl reload nginx
certbot --nginx -d app.verqac.com
```

Then open https://app.verqac.com and register the first organization.

## 6. Update after a change

```bash
cd /opt/verqac && git pull && docker compose up -d --build
```

The `migrate` service runs `alembic upgrade head` before the API starts.

## 7. Backup (set up on day one)

```bash
# /root/verqac_pg_backup.sh  (nightly cron, keep 14 days)
docker compose -f /opt/verqac/docker-compose.yml exec -T db \
  pg_dump -U postgres -Fc verqac > /root/backups/verqac/verqac_$(date +%F).dump
find /root/backups/verqac -name '*.dump' -mtime +14 -delete
```
