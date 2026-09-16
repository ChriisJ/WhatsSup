# Portainer Deployment Guide

This guide walks you through deploying **WhatsSup** to your home server using
Portainer and the GitHub-published container image. Two paths are shown:

- **Path A (recommended)**: pull the prebuilt image from GitHub Container
  Registry (GHCR). Smallest setup, auto-updates via Watchtower.
- **Path B**: build the image inside Portainer from the Git repo. Use this if
  you want to fork/customize before deploying.

---

## Prerequisites

- Portainer >= 2.18 installed on your server
- A reachable URL/hostname for your Portainer instance (e.g. `https://nas.local:9443`)
- A DNS name or reverse-proxy entry for WhatsSup (e.g. `https://meds.example.com`)
- For Discord/Telegram bots: see [`SETUP.md`](./SETUP.md)

## Path A: deploy from GHCR image (recommended)

### 1. Merge the PR / push to `main`

The bundled GitHub Actions workflow (`.github/workflows/docker-publish.yml`)
automatically builds and pushes the image to
`ghcr.io/<your-gh-user>/whatssup:latest` on every push to `main`.

1. Open the PR on GitHub and review/merge it.
2. Watch the **Actions** tab: the `Build and Push Docker Image` workflow
   should complete in ~2-4 minutes.
3. Confirm the image exists: `https://github.com/<user>?tab=packages` or
   `docker pull ghcr.io/<your-gh-user>/whatssup:latest` from your server.

> **Note**: GHCR images are private by default. If you want the image to be
> pullable without auth, go to the package page on GitHub → Package settings
> → Change visibility → Public. For a self-hosted single-user setup, leaving
> it private and authenticating from Portainer is fine.

### 2. Create a GitHub PAT for the image pull (private images)

If your GHCR image stays private:

1. GitHub → Settings → Developer settings → Personal access tokens →
   **Fine-grained token**
2. Resource owner: yourself
3. Repository access: **Public repositories (read-only)** is enough if your
   WhatsSup repo is public. Otherwise select the WhatsSup repo.
4. Permissions: `packages: read`
5. Generate token, copy it.

### 3. In Portainer: Stacks → Add stack

- **Name**: `whatssup`
- **Build method**: leave as "Web editor" (we paste a compose file)
- **Environment variables**: fill in at minimum `SECRET_KEY` and
  `DEFAULT_ADMIN_PASSWORD`. See `../.env.example` for the full list.

Paste the following compose content (adjust paths/hostnames as needed):

```yaml
services:
  whatssup:
    image: ghcr.io/<your-gh-user>/whatssup:latest
    container_name: whatssup
    restart: unless-stopped
    ports:
      - "8000:8000"          # adjust host port if 8000 is taken
    env_file:
      - .env                  # path INSIDE the stack - we use the web editor's env block instead
    environment:
      TZ: ${TZ}
      SECRET_KEY: ${SECRET_KEY}
      DEFAULT_ADMIN_USERNAME: ${DEFAULT_ADMIN_USERNAME}
      DEFAULT_ADMIN_PASSWORD: ${DEFAULT_ADMIN_PASSWORD}
      DATABASE_URL: ${DATABASE_URL:-sqlite:///./data/whatssup.db}
      REMINDER_INTERVAL_MINUTES: ${REMINDER_INTERVAL_MINUTES:-30}
      REMINDER_QUIET_HOURS_START: ${REMINDER_QUIET_HOURS_START:-22}
      REMINDER_QUIET_HOURS_END: ${REMINDER_QUIET_HOURS_END:-7}
      # Discord (optional)
      DISCORD_ENABLED: ${DISCORD_ENABLED:-false}
      DISCORD_BOT_TOKEN: ${DISCORD_BOT_TOKEN:-}
      DISCORD_CHANNEL_ID: ${DISCORD_CHANNEL_ID:-}
      DISCORD_ALLOWED_USERS: ${DISCORD_ALLOWED_USERS:-}
      # Telegram (optional)
      TELEGRAM_ENABLED: ${TELEGRAM_ENABLED:-false}
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN:-}
      TELEGRAM_ALLOWED_CHATS: ${TELEGRAM_ALLOWED_CHATS:-}
      # WhatsApp via CallMeBot (optional)
      WHATSAPP_ENABLED: ${WHATSAPP_ENABLED:-false}
      WHATSAPP_PHONE: ${WHATSAPP_PHONE:-}
      WHATSAPP_APIKEY: ${WHATSAPP_APIKEY:-}
    volumes:
      # CRITICAL: persist the SQLite DB outside the container
      - whatssup-data:/app/data
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s

volumes:
  whatssup-data:
```

For a **private** image, add a `registry` config in the Portainer stack
"Advanced" section, or pull manually on the host once:
```bash
docker login ghcr.io -u <gh-user> -p <PAT>
```

### 4. Deploy + first login

1. Click **Deploy the stack**.
2. Wait ~30s for the container healthcheck to flip to healthy.
3. Open `http://<server>:8000` and log in with
   `DEFAULT_ADMIN_USERNAME` / `DEFAULT_ADMIN_PASSWORD`.
4. **Change the admin password immediately** (Profile tab).
5. Set your **body weight** in the profile - this drives mg/kg dosing.
6. Add supplements from the **Katalog** tab.

---

## Path B: build from Git inside Portainer

Use this if you want to fork/customize without using GHCR.

1. Stacks → Add stack → **Git repository**
2. **Repository URL**: `https://github.com/ChriisJ/WhatsSup.git`
3. **Reference**: `refs/heads/main`
4. **Compose path**: `docker-compose.yml` (or leave empty)
5. **Environment**: same env block as Path A, step 3
6. Click **Deploy**. Portainer will `git clone` + `docker build` the image.

**Auto-rebuild on push**: in the stack settings, enable **Auto-update** with
webhook. Each push to `main` on GitHub triggers a redeploy.

---

## Auto-updates via Watchtower (Path A only)

Path A doesn't auto-rebuild. Add a Watchtower sidecar:

```yaml
services:
  whatssup:
    image: ghcr.io/<your-gh-user>/whatssup:latest
    # ... (same as Path A)

  watchtower:
    image: containrrr/watchtower
    container_name: watchtower
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      WATCHTOWER_CLEANUP: "true"
      WATCHTOWER_POLL_INTERVAL: "86400"   # check once a day
      WATCHTOWER_LABEL_ENABLE: "true"    # only update containers with this label
    command: --label-enable

# Add to whatssup service:
#     labels:
#       - "com.centurylinklabs.watchtower.enable=true"
```

Once deployed, Watchtower checks daily and pulls new `:latest` images.

---

## Reverse proxy (HTTPS)

Don't expose port 8000 directly to the internet. Use Caddy, Traefik, or nginx
in front. Example Caddy block:

```caddyfile
meds.example.com {
    reverse_proxy whatssup:8000
}
```

For Traefik (when using docker labels), see the official Traefik docs.

---

## Backup

The whole app is one volume (`whatssup-data`). Backup any way you like:

```bash
# On the host:
docker run --rm -v whatssup_whatssup-data:/data -v $(pwd):/backup \
    alpine tar czf /backup/whatssup-$(date +%F).tar.gz -C /data .
```

Restore: `docker run --rm -v whatssup_whatssup-data:/data -v $(pwd):/backup \
alpine tar xzf /backup/whatssup-<date>.tar.gz -C /data`

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Container restarts every 30s | missing/invalid `SECRET_KEY` | check container logs: `docker logs whatssup` |
| 500 on login | bcrypt/admin bootstrap crash | confirm `bcrypt<4.0` is pinned in requirements.txt |
| Reminders never fire | notifier disabled or token invalid | check `/api/health` for `discord_enabled`/`telegram_enabled` flags |
| Healthcheck stays unhealthy | DB dir not writable | ensure volume mount `/app/data` is writable |
| Discord bot offline | MESSAGE CONTENT INTENT not enabled | Discord dev portal → Bot → enable intent, may take 24h for new bots |

For more, see [`SETUP.md`](./SETUP.md) (bot setup) and the main
[`README.md`](../README.md).
