"""Utilitaires partagés : configuration, fichiers de données, heure locale, HTTP."""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "docs" / "data"
BRIEF_DIR = DATA_DIR / "briefings"
STATE_FILE = ROOT / "state" / "state.json"
PROMPTS_DIR = ROOT / "prompts"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("crypto-intel")

USER_AGENT = "crypto-intel/1.0 (personal research dashboard; contact: " + os.getenv("CONTACT_EMAIL", "unset") + ")"


def load_config() -> dict[str, Any]:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def tz(cfg: dict) -> ZoneInfo:
    return ZoneInfo(cfg.get("timezone", "Europe/Paris"))


def now_local(cfg: dict) -> datetime:
    return datetime.now(tz(cfg))


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        log.warning("Fichier JSON illisible, ignoré : %s", path)
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def load_state() -> dict[str, Any]:
    state = read_json(STATE_FILE, {}) or {}
    state.setdefault("seen", {})            # id -> timestamp (dédoublonnage)
    state.setdefault("x_since", {})         # user_id -> dernier tweet vu
    state.setdefault("recent", [])          # derniers éléments (pour recouper les sources)
    state.setdefault("digest_queue", [])    # alertes IMPORTANT en attente
    state.setdefault("sent", {})            # date -> {"critical": n, "digests": [...]}
    return state


def save_state(state: dict[str, Any]) -> None:
    cutoff = time.time() - 3 * 86400
    state["seen"] = {k: v for k, v in state["seen"].items() if v >= cutoff}
    state["recent"] = [r for r in state["recent"] if r.get("ts", 0) >= time.time() - 86400][-400:]
    for d in list(state["sent"].keys())[:-7]:
        state["sent"].pop(d, None)
    write_json(STATE_FILE, state)


def http_get(url: str, *, params: dict | None = None, headers: dict | None = None, timeout: int = 20, retries: int = 2) -> requests.Response | None:
    h = {"User-Agent": USER_AGENT, "Accept": "application/json, */*"}
    if headers:
        h.update(headers)
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, headers=h, timeout=timeout)
            if r.status_code == 429 and attempt < retries:
                time.sleep(5 * (attempt + 1))
                continue
            if r.ok:
                return r
            log.warning("HTTP %s sur %s", r.status_code, url)
            return None
        except requests.RequestException as e:
            if attempt >= retries:
                log.warning("Échec réseau sur %s : %s", url, e)
                return None
            time.sleep(2 * (attempt + 1))
    return None


def read_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def extract_json(text: str) -> Any:
    """Récupère le premier objet/tableau JSON d'une réponse de modèle (tolère ```json ...```)."""
    t = text.strip().replace("```json", "").replace("```", "")
    starts = [i for i in (t.find("{"), t.find("[")) if i != -1]
    if not starts:
        raise ValueError("Aucun JSON trouvé dans la réponse")
    start = min(starts)
    end = max(t.rfind("}"), t.rfind("]"))
    return json.loads(t[start : end + 1])
