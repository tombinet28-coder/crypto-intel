"""Petits outils de mise en place.

python -m src.tools chat-id        → affiche l'identifiant de ta conversation Telegram
python -m src.tools test-telegram  → envoie un message de test
python -m src.tools resolve-x      → récupère les identifiants numériques des comptes X (coûte quelques centimes)
"""
from __future__ import annotations

import os
import sys

import requests

from . import notify
from .common import load_config


def chat_id() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20).json()
    seen = set()
    for u in r.get("result", []):
        chat = (u.get("message") or {}).get("chat") or {}
        if chat.get("id") and chat["id"] not in seen:
            seen.add(chat["id"])
            print(f"chat_id = {chat['id']}  ({chat.get('first_name', '')} {chat.get('username', '')})")
    if not seen:
        print("Aucun message trouvé : envoie d'abord « bonjour » à ton bot dans Telegram, puis relance.")


def test_telegram() -> None:
    ok = notify.send("✅ <b>Crypto Intel</b> est bien connecté. Tu recevras ici le briefing de 06:30 et les alertes.")
    print("Message envoyé." if ok else "Échec : vérifie TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID.")


def resolve_x() -> None:
    token = os.environ["X_BEARER_TOKEN"]
    cfg = load_config()
    handles = [a["handle"] for a in cfg["x_accounts"] if not a.get("id")]
    for i in range(0, len(handles), 100):
        batch = handles[i : i + 100]
        r = requests.get(
            "https://api.x.com/2/users/by",
            params={"usernames": ",".join(batch), "user.fields": "verified,verified_type,public_metrics"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        ).json()
        for u in r.get("data", []):
            followers = (u.get("public_metrics") or {}).get("followers_count")
            print(f"{u['username']:<18} id: {u['id']:<22} abonnés: {followers}  type: {u.get('verified_type', '-')}")
        for e in r.get("errors", []):
            print("Introuvable :", e.get("value"), "-", e.get("detail"))
    print("\nColle chaque id dans config.yaml, puis vérifie les comptes un par un sur x.com.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"chat-id": chat_id, "test-telegram": test_telegram, "resolve-x": resolve_x}.get(cmd, lambda: print(__doc__))()
