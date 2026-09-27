"""Tests hors ligne (aucun appel réseau) : python -m tests.test_offline"""
import sys, types, json, time
from datetime import datetime
from zoneinfo import ZoneInfo

# Faux modules si non installés (le test ne fait aucun appel réseau)
for name in ("anthropic", "feedparser"):
    if name not in sys.modules:
        try:
            __import__(name)
        except ImportError:
            sys.modules[name] = types.ModuleType(name)

from src import reliability, briefing, monitor, notify
from src.common import load_config

cfg = load_config()

# 1) Niveaux de sources
assert reliability.tier_for_url(cfg, "https://www.sec.gov/news/press-release/2026-1") == 1
assert reliability.tier_for_url(cfg, "https://governance.aave.com/t/xyz") == 1
assert reliability.tier_for_url(cfg, "https://www.coindesk.com/markets/x") == 2
assert reliability.tier_for_url(cfg, "https://www.openpr.com/news/123") == 9
assert reliability.tier_for_url(cfg, "https://randomblog.io/post") == 3
assert reliability.tier_for_url(cfg, "https://www.coinbase.com/blog/post") == 1
assert reliability.tier_for_url(cfg, "https://www.coinbase.com/price/solana") == 3

# 2) Confiance
c = reliability.confidence
assert c([{"tier": 2, "url": "https://coindesk.com/a"}]) == "likely"
assert c([{"tier": 2, "url": "https://coindesk.com/a"}, {"tier": 2, "url": "https://theblock.co/b"}]) == "confirmed"
assert c([{"tier": 2, "url": "https://coindesk.com/a"}, {"tier": 2, "url": "https://coindesk.com/b"}]) == "likely"
assert c([{"tier": 3, "kind": "x", "url": "https://x.com/a"}]) == "rumor"
assert c([{"tier": 9, "url": "https://openpr.com/a"}]) == "unconfirmed"
assert c([{"tier": 1, "url": "https://sec.gov/a"}]) == "confirmed"

# 3) Nettoyage de la sortie du modèle + injection des prix
raw = {"tldr": [{"impact": "wow", "text": "x"}] * 12, "news": [{"title": "t", "impact": "pos", "confidence": "sure",
       "sources": [{"name": "a", "url": "javascript:alert(1)"}]}], "watchlist": [{"impact": "neu", "text": "w"}] * 8,
       "market": [{"symbol": "BTC", "sentiment": "pos", "driver": "Fed", "price": 1}], "evil": "drop me"}
b = briefing.sanitize(raw, "2026-09-28")
assert len(b["tldr"]) == 10 and b["tldr"][0]["impact"] == "neu"
assert b["news"][0]["confidence"] == "unconfirmed"
assert b["news"][0]["sources"][0]["url"] is None
assert len(b["watchlist"]) == 5 and "evil" not in b
prio = [{"symbol": "BTC", "name": "Bitcoin", "price": 84000.0, "change24h": 1.2, "change7d": 3.0, "volume": 3e10, "lastUpdated": "2026-09-28T04:25:00.000Z"},
        {"symbol": "ETH", "name": "Ethereum", "price": None, "change24h": None, "change7d": None, "volume": None, "lastUpdated": None}]
briefing.inject_market(b, prio, cfg)
assert b["market"][0]["price"] == 84000.0 and b["market"][0]["driver"] == "Fed" and b["market"][0]["asOf"] == "28/09 06:25"
assert b["market"][1]["asOf"] == "Donnée indisponible"

# 4) Surveillance : un CRITICAL avec une seule source est rétrogradé
now = datetime(2026, 9, 28, 14, 7, tzinfo=ZoneInfo("Europe/Paris"))
state = {"recent": [], "alerted": {}}
items = [{"id": "rss:1", "kind": "news", "title": "Exchange X hacked", "url": "https://coindesk.com/x", "source": "CoinDesk", "tier": 2, "ts": time.time()}]
cls = [{"id": "rss:1", "cluster": "x-hack", "level": "critical", "assets": ["ETH"], "title": "Exchange X piraté", "summary": "…"}]
al = monitor.build_alerts(cfg, items, cls, state, now)
assert al[0]["level"] == "important" and al[0]["confidence"] == "likely"
# … puis confirmé par une deuxième source indépendante : passe en CRITICAL
items2 = [{"id": "rss:2", "kind": "news", "title": "X exchange exploit", "url": "https://theblock.co/y", "source": "The Block", "tier": 2, "ts": time.time()}]
cls2 = [{"id": "rss:2", "cluster": "x-hack", "level": "critical", "assets": ["ETH"], "title": "Exchange X piraté", "summary": "…"}]
al2 = monitor.build_alerts(cfg, items2, cls2, state, now)
assert al2[0]["level"] == "critical" and al2[0]["confidence"] == "confirmed"
# … et n'est pas renvoyé une troisième fois
assert monitor.build_alerts(cfg, items2, cls2, state, now) == []

# 5) Heures calmes et récaps
assert monitor.in_quiet_hours(cfg, now.replace(hour=23, minute=30))
assert monitor.in_quiet_hours(cfg, now.replace(hour=6, minute=0))
assert not monitor.in_quiet_hours(cfg, now.replace(hour=6, minute=45))
assert monitor.digest_slot(cfg, now.replace(hour=12, minute=37)) == "12:30"
assert monitor.digest_slot(cfg, now.replace(hour=13, minute=7)) is None

# 6) Messages Telegram : le HTML injecté est neutralisé
msg = notify.format_alert({"level": "critical", "title": "<script>x</script>", "time": "14:07", "confidence": "confirmed",
                           "sources": [{"name": "a", "url": "javascript:x"}]})
assert "<script>" not in msg and "javascript:" not in msg
brief = json.load(open("docs/data/briefings/2026-09-27.json", encoding="utf-8"))
assert "TL;DR" in notify.format_briefing(brief, "https://exemple.github.io/crypto-intel/")

print("Tous les tests hors ligne passent ✅")
