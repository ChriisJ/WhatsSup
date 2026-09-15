# 💊 MedTracker

Self-hosted supplement & medication tracker with smart reminders.
**No ads. No subscription. Your data stays on your machine.**

- 📋 List your supplements with **weight-based dosage** calculation (mg/kg body weight)
- ⏰ Automatic **optimal timing** based on half-life, food requirements, and known interactions
- 🔔 **Smart reminders** via Discord, Telegram, WhatsApp (CallMeBot), and Web UI
  - Reminders repeat every **30 minutes until you confirm** — forget to check off your morning meds? You'll know.
- 🤖 **Interactive buttons** in Discord and Telegram — tap "Genommen" right from the reminder
- 🚫 **Interaction warnings** — catches things like Calcium ↔ Eisen, Zink ↔ Kupfer, Koffein ↔ Melatonin
- ❤️ **Blood pressure tracking** built-in
- 📊 **Compliance stats** — see how often you really hit your schedule
- 🔌 Pure **Docker container**, drops into Portainer with one stack file
- 🌐 **PWA**: install on your phone, works offline-ish

---

## 🚀 Quick start (Docker / Portainer)

### Option A: One-click Portainer

In Portainer: **Stacks → Add stack → Git repository**, point at this repo, set env vars in the web UI
(see `.env.example` for the full list), and deploy.

The default port is `8000`. Open `http://your-host:8000` and log in with the credentials from `.env`.

### Option B: Local Docker Compose

```bash
git clone https://github.com/your-name/medtracker.git
cd medtracker
cp .env.example .env
# Edit .env — set SECRET_KEY and DEFAULT_ADMIN_PASSWORD at minimum
docker compose up -d
```

The image is automatically published to GitHub Container Registry on every push to `main`
and tagged `latest`. Pull with:

```bash
docker pull ghcr.io/your-name/medtracker:latest
```

### Option C: Plain Python (for hacking on it)

```bash
git clone https://github.com/your-name/medtracker.git
cd medtracker
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
python -m backend.main
# -> open http://localhost:8000
```

---

## ⚙️ Configuration

All configuration is via the `.env` file. See [`.env.example`](./.env.example) for the full list.

### Required
- `SECRET_KEY` — random long string used for JWT tokens. Generate one with `openssl rand -hex 32`.
- `DEFAULT_ADMIN_PASSWORD` — your initial admin password.

### Optional: Discord bot

1. Go to <https://discord.com/developers/applications> → **New Application** → **Bot**.
2. Copy the bot **token**.
3. Enable **MESSAGE CONTENT INTENT** under Bot settings.
4. Invite the bot to your server using OAuth2 → URL Generator (scopes: `bot`, permissions: `Send Messages`).
5. Set `DISCORD_ENABLED=true`, `DISCORD_BOT_TOKEN=...`, optional `DISCORD_GUILD_ID` and `DISCORD_CHANNEL_ID`.

Reminders will be sent to the channel with a **"Genommen / Snooze 30 / Skip"** button row.
Tapping a button updates the database instantly.

### Optional: Telegram bot

1. Talk to [@BotFather](https://t.me/BotFather) → `/newbot` → copy token.
2. Set `TELEGRAM_ENABLED=true`, `TELEGRAM_BOT_TOKEN=...`.
3. Find your chat ID (e.g. via [@userinfobot](https://t.me/userinfobot)) and set `TELEGRAM_ALLOWED_CHATS=...`.
4. Send `/start` to your bot.

### Optional: WhatsApp (via CallMeBot — free, unofficial, no buttons)

> ⚠️ WhatsApp via CallMeBot only supports plain text. You'll have to confirm via the web UI.
> Meta's official WhatsApp Business API costs money per conversation.

1. Save `+34 644 59 71 47` as **CallMeBot** in your contacts.
2. Send the message: `I allow callmebot to send me messages`.
3. You'll receive an API key via WhatsApp.
4. Set `WHATSAPP_ENABLED=true`, `WHATSAPP_PHONE=<your number, international, no +>`, `WHATSAPP_APIKEY=<key>`.

---

## 🧠 Smart features in detail

### Weight-based dosage
Set your body weight once in the profile. Each supplement catalog entry has a recommended
`mg/kg` value. Override per-supplement or use a fixed dose. The app computes your daily target automatically.

### Optimal timing
The catalog encodes best-time heuristics per category:
- **Melatonin, Magnesium, ZMA** → 30–60 min before bed
- **Vitamin D, Omega-3** → with a fatty meal
- **Iron, Vitamin B/C, Zink** → morning, empty stomach, away from coffee/calcium
- **Koffein** → before 14:00
- … and more

### Reminder loop
The scheduler ticks every minute. For each pending intake past its scheduled time:
- If we've never sent a reminder, send one.
- If the last reminder was sent ≥ `REMINDER_INTERVAL_MINUTES` ago (default 30), send another.
- After 4 hours of silence → mark as `MISSED` and stop.
- Quiet hours (default 22:00–07:00) suppress non-overdue nudges.

### Interaction warnings
Built-in curated list. Add more via the database. Detected automatically on the Today view.

---

## 📁 Project structure

```
medtracker/
├── backend/             # FastAPI app
│   ├── main.py          # Entry point + wiring
│   ├── config.py
│   ├── database.py
│   ├── models.py        # SQLAlchemy models
│   ├── schemas.py       # Pydantic schemas
│   ├── security.py      # JWT + bcrypt
│   ├── dose.py          # mg/kg + timing heuristics
│   ├── interactions.py  # Interaction rules
│   ├── scheduler.py     # APScheduler 1-min tick
│   ├── bot_bridge.py    # Bot → DB bridge
│   ├── seed_catalog.py  # Built-in supplement catalog
│   ├── notifiers/       # Discord, Telegram, WhatsApp
│   └── routes/          # FastAPI routers
├── frontend/            # Vanilla JS SPA (PWA-ready)
├── data/                # SQLite DB lives here (gitignored)
├── docker-compose.yml
├── Dockerfile
└── .github/workflows/   # Auto-publish Docker image to GHCR
```

---

## 🔐 Security notes

- Single-user-friendly but **multi-user from day one** — share with family.
- Passwords hashed with bcrypt.
- JWT bearer tokens, 7-day expiry.
- **Change `SECRET_KEY` and `DEFAULT_ADMIN_PASSWORD` before exposing to the internet**.
- No external services phone home. No analytics. No telemetry.
- Bind the container behind a reverse proxy (Caddy, nginx, Traefik) for HTTPS.

---

## 🚧 Roadmap / ideas

- [ ] Web Push (browser notifications, no Telegram needed)
- [ ] Refill tracking (when will you run out?)
- [ ] Lab value tracking (Vit D blood level, etc.)
- [ ] Apple Health / Google Fit sync
- [ ] i18n (currently de + en strings)
- [ ] Native mobile app (Capacitor wrapper around the PWA)

PRs welcome — see [`docs/CONTRIBUTING.md`](./docs/CONTRIBUTING.md).

---

## ⚠️ Disclaimer

MedTracker is not a medical device. The interaction database and dosage suggestions are
**heuristic and not a substitute for medical advice**. Always consult a doctor or pharmacist
before changing supplements, especially if you take prescription medication.

---

## 📜 License

MIT. See [`LICENSE`](./LICENSE).
