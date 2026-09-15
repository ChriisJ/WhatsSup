# GitHub PAT erstellen (für den Push)

Falls du Option A (lokal pushen) wählst, brauchst du einen **Personal Access Token (PAT)** — nicht dein Passwort. GitHub hat Passwort-Auth für `git push` im August 2021 abgeschafft.

## Fine-grained PAT (empfohlen, abgeschlossener Scope)

1. Gehe zu <https://github.com/settings/tokens?type=beta>
2. **Generate new token** → **Fine-grained**
3. **Token name**: `whatssup-push` (oder was dir gefällt)
4. **Expiration**: 30 Tage (kannst danach verlängern)
5. **Repository access**: **Only select repositories** → `ChriisJ/WhatsSup`
6. **Permissions** → **Repository permissions**:
   - Contents: **Read and write**
   - (Actions, Metadata etc. nicht nötig für den Push)
7. Klick **Generate token**
8. **Token kopieren** — der wird nur EINMAL angezeigt! (`github_pat_xxx...`)

Beim Push fragt git nach:
- **Username**: `ChriisJ` (oder dein Username)
- **Password**: das kopierte Token einfügen, **nicht** dein GitHub-Passwort

## Classic PAT (Fallback)

Falls dir die fine-grained Variante zu fummelig ist:

1. <https://github.com/settings/tokens/new>
2. **Note**: `whatssup-push`
3. **Expiration**: 30 Tage
4. **Scopes**: nur `repo` anhaken
5. **Generate token**
6. Token kopieren (`ghp_xxx...`)

---

## ⚠️ Sicherheit

- Token gilt wie ein Passwort — niemals committen, in Slack posten, in Chat pasten
- Nach erfolgreichem Push: Token in GitHub Revoke / Regenerate
- Wenn du den Verdacht hast, dass der Token geleakt wurde: sofort Revoke + neuen generieren
- Lokal kannst du den Token in `~/.git-credentials` speichern, dann fragt git nicht mehr:
  ```bash
  git config --global credential.helper store
  # Beim nächsten Push nach Token gefragt -> eingeben -> bleibt gespeichert
  ```

## Nach dem Push

Token kannst du entweder löschen oder behalten für künftige Pushes. Wenn er nur 30 Tage gültig ist, einfach vor Ablauf verlängern oder neu generieren.
