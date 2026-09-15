# Setup Guide

Detailed setup walkthrough.

## 1. Clone and configure

```bash
git clone https://github.com/your-name/medtracker.git
cd medtracker
cp .env.example .env
```

## 2. Generate a strong SECRET_KEY

```bash
openssl rand -hex 32
```

Paste the output into `SECRET_KEY=` in your `.env`.

## 3. Set your admin password

In `.env`:
```
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=<a strong password you'll use to log in>
```

The first time the container starts, this user is created automatically.

## 4. Choose your notification channels

### Discord (recommended — supports interactive buttons)

1. <https://discord.com/developers/applications> → New Application → Bot.
2. **Reset Token** → copy it.
3. Under Bot → enable **MESSAGE CONTENT INTENT**.
4. OAuth2 → URL Generator → scopes: `bot` → permissions: `Send Messages`, `Embed Links`, `Use Slash Commands` (if you want them later).
5. Open the generated URL to invite the bot to your server.
6. (Optional) Right-click a channel → Copy Channel ID (enable Developer Mode first).
7. Fill in `.env`:
   ```
   DISCORD_ENABLED=true
   DISCORD_BOT_TOKEN=<token from step 2>
   DISCORD_CHANNEL_ID=<optional channel id>
   DISCORD_ALLOWED_USERS=<comma-separated Discord user IDs allowed to confirm>
   ```

### Telegram

1. Talk to [@BotFather](https://t.me/BotFather) on Telegram.
2. Send `/newbot`, follow the wizard, copy the token.
3. Find your chat ID by messaging [@userinfobot](https://t.me/userinfobot).
4. Send `/start` to your bot (so it can message you).
5. Fill in `.env`:
   ```
   TELEGRAM_ENABLED=true
   TELEGRAM_BOT_TOKEN=<token>
   TELEGRAM_ALLOWED_CHATS=<your chat id>
   ```

### WhatsApp via CallMeBot (text only)

See `.env.example` for the steps. Long story short: save the number, send a message, get a key.

## 5. Deploy

### Via Docker Compose (Linux/Mac/Windows with Docker)

```bash
docker compose up -d
docker compose logs -f medtracker
```

### Via Portainer

1. Portainer → **Stacks** → **Add stack**.
2. Pick **Git repository**, paste this repo's URL, set `docker-compose.yml` as the path.
3. Under **Environment variables**, paste the contents of your `.env` (or use the **Advanced → Env file** upload).
4. Click **Deploy the stack**.

### Auto-updates

The included GitHub Actions workflow (`/.github/workflows/docker-publish.yml`) builds and pushes the image
to GitHub Container Registry on every push to `main` with the `latest` tag, plus semantic tags for releases.

To use with **Portainer + Watchtower**:
1. Deploy as above.
2. Add a separate **Watchtower** stack pointing at the `medtracker` container.

## 6. First login

1. Open `http://your-host:8000` in a browser.
2. Log in with `DEFAULT_ADMIN_USERNAME` / `DEFAULT_ADMIN_PASSWORD`.
3. **Change your password** (Profile tab) or update `.env` + restart.
4. Profile tab → set your **body weight** in kg.
5. "Meine Supplements" tab → **add your first supplement** from the catalog.
6. Set your schedule (e.g. `08:00, 20:00`) and save.

You're done. The reminder scheduler kicks in within seconds.
