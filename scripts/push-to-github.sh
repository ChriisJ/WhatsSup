#!/usr/bin/env bash
# ============================================================
# WhatsSup - Push to GitHub in one shot
# ============================================================
# Usage:
#   chmod +x scripts/push-to-github.sh
#   ./scripts/push-to-github.sh
#
# Optional env vars:
#   GH_USER   - your GitHub username (default: ChriisJ)
#   GH_EMAIL  - git commit email (default: <user>@users.noreply.github.com)
#   GH_REPO   - target repo (default: WhatsSup)
# ============================================================
set -euo pipefail

GH_USER="${GH_USER:-ChriisJ}"
GH_REPO="${GH_REPO:-WhatsSup}"
GH_EMAIL="${GH_EMAIL:-${GH_USER}@users.noreply.github.com}"
BRANCH="${BRANCH:-main}"

# ---- Sanity checks ----
if ! command -v git >/dev/null 2>&1; then
  echo "❌ git nicht gefunden. Installiere git und versuche es nochmal."
  exit 1
fi

if [ -d .git ]; then
  echo "⚠️  .git existiert bereits. Überspringe 'git init'."
  SKIP_INIT=1
fi

# ---- Step 1: git config ----
git config --global user.name  "${GH_USER}"
git config --global user.email "${GH_EMAIL}"
git config --global init.defaultBranch "${BRANCH}"

# ---- Step 2: init (if needed) ----
if [ -z "${SKIP_INIT:-}" ]; then
  git init
fi

# ---- Step 3: ensure .env is ignored, never committed ----
if [ ! -f .gitignore ]; then
  echo "❌ .gitignore fehlt - irgendwas stimmt nicht mit dem Repo-Setup."
  exit 1
fi

if grep -q "^\.env$" .gitignore; then
  echo "✓ .env ist in .gitignore"
else
  echo "⚠️  .env fehlt in .gitignore - füge hinzu"
  echo ".env" >> .gitignore
fi

# Make sure we never accidentally commit the database or pycache
grep -q "__pycache__" .gitignore || echo "__pycache__/" >> .gitignore
grep -q "^data/\*\.db" .gitignore || echo "data/*.db" >> .gitignore

# ---- Step 4: add + commit ----
git add .
git status --short

if git diff --cached --quiet; then
  echo "ℹ️  Nichts zu committen."
else
  git commit -m "feat: initial WhatsSup release

- FastAPI + SQLite backend with smart mg/kg dosage
- Discord + Telegram bots with interactive buttons
- WhatsApp via CallMeBot (text-only)
- PWA frontend, installable
- APScheduler: 30-min reminder loop until confirmed
- Supplement interaction warnings (12 curated rules)
- Blood pressure tracking
- Compliance statistics
- Docker + Portainer-ready
- Auto-publish to GHCR via GitHub Actions"
fi

# ---- Step 5: remote + push ----
REMOTE_URL="https://github.com/${GH_USER}/${GH_REPO}.git"

if git remote get-url origin >/dev/null 2>&1; then
  echo "ℹ️  Remote 'origin' existiert bereits: $(git remote get-url origin)"
else
  git remote add origin "${REMOTE_URL}"
  echo "✓ Remote hinzugefügt: ${REMOTE_URL}"
fi

git branch -M "${BRANCH}"

echo ""
echo "🚀 Pushe nach ${REMOTE_URL} (Branch: ${BRANCH})"
echo "    Du wirst nach Username + PAT gefragt."
echo "    Username: ${GH_USER}"
echo "    Password: <dein GitHub PAT mit 'repo' scope>"
echo ""

git push -u origin "${BRANCH}"

echo ""
echo "✅ Fertig! Repo: https://github.com/${GH_USER}/${GH_REPO}"
echo ""
echo "Nächste Schritte:"
echo "  1. Geh zu https://github.com/${GH_USER}/${GH_REPO}/actions - GHCR Build läuft jetzt"
echo "  2. Nach ~5min: https://github.com/${GH_USER}/${GH_REPO}/packages - Image sollte da sein"
echo "  3. In Portainer: Stack → Git Repo → ${REMOTE_URL}"
