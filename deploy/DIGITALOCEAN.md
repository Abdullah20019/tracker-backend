# DigitalOcean Backend Deployment

## Recommended target

- Ubuntu 24.04 Droplet
- 2 vCPU / 2 GB RAM
- domain: `api.paktrack.xyz`

## 1. Base packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx git
```

## 2. App directory

```bash
sudo useradd --system --create-home --shell /bin/bash paktrack
sudo mkdir -p /opt/paktrack
sudo chown -R paktrack:paktrack /opt/paktrack
```

Clone or copy the backend into:

```bash
/opt/paktrack/backend
```

## 3. Python environment

```bash
cd /opt/paktrack/backend
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Backend env file

Create:

```bash
sudo mkdir -p /etc/paktrack
sudo nano /etc/paktrack/backend.env
```

Suggested contents:

```env
APP_ENV=production
BACKEND_SHARED_SECRET=change-this-to-a-strong-random-secret
CORS_ALLOWED_ORIGINS=https://www.paktrack.xyz,https://paktrack.xyz
PUBLIC_API_ALLOWED_ORIGINS=https://www.paktrack.xyz,https://paktrack.xyz
TRUSTED_HOSTS=api.paktrack.xyz,www.paktrack.xyz,paktrack.xyz
ENABLE_PUBLIC_DOCS=false
ENFORCE_ORIGIN_CHECK=true
TRACK_RATE_LIMIT_PER_MINUTE=60
BULK_RATE_LIMIT_PER_MINUTE=12
HEALTH_RATE_LIMIT_PER_MINUTE=30
INTERNAL_RATE_LIMIT_PER_MINUTE=30
MAX_REQUEST_SIZE_BYTES=32768
```

## 5. Systemd service

Copy:

```bash
sudo cp /opt/paktrack/backend/deploy/paktrack-backend.service /etc/systemd/system/paktrack-backend.service
sudo systemctl daemon-reload
sudo systemctl enable paktrack-backend
sudo systemctl start paktrack-backend
sudo systemctl status paktrack-backend
```

## 6. Nginx

Copy:

```bash
sudo cp /opt/paktrack/backend/deploy/paktrack-api.nginx.conf /etc/nginx/sites-available/paktrack-api.conf
sudo ln -s /etc/nginx/sites-available/paktrack-api.conf /etc/nginx/sites-enabled/paktrack-api.conf
sudo nginx -t
sudo systemctl reload nginx
```

## 7. SSL

If using Cloudflare in front, point `api.paktrack.xyz` to the Droplet and then install TLS on origin too:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d api.paktrack.xyz
```

## 8. Frontend env on Vercel

Set:

```env
VITE_SITE_URL=https://www.paktrack.xyz
VITE_GOOGLE_SITE_VERIFICATION=<google-search-console-token>
VITE_GA_MEASUREMENT_ID=G-XXXXXXXXXX
BACKEND_BASE_URL=https://api.paktrack.xyz
BACKEND_SHARED_SECRET=<same-secret-as-backend>
```
