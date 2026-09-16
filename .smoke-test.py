"""Smoke test for the admin panel changes."""
from backend.main import app
from backend.bot_config import get_effective_config, parse_csv_set
from backend.routes.admin import router as admin_router
from backend.models import BotConfig, User
from backend.notifiers import NotifierManager, DiscordNotifier, TelegramNotifier, WhatsAppNotifier

print("All imports OK")
print()
print("Registered API routes:")
for r in app.routes:
    if hasattr(r, "path") and "/api/" in r.path:
        methods = ",".join(sorted(getattr(r, "methods", []) - {"HEAD"}))
        print(f"  [{methods:<12}] {r.path}")

print()
print("Schema fields check:")
from backend.schemas import BotConfigOut, BotConfigIn
print(f"  BotConfigOut fields: {list(BotConfigOut.model_fields.keys())}")
print(f"  BotConfigIn fields:  {list(BotConfigIn.model_fields.keys())}")
