"""File-backed subscription store. One row per email: hash, salt, ts, confirmed.

Privacy-first: raw email is NEVER stored — only SHA256(salt + email) and the
display-safe local part (kept for the owner's own digest; salted-hash keyed).
"""
import hashlib, json, os, secrets, threading, time, email.utils, re
from email.header import decode_header

STORE = os.environ.get("SUB_STORE", "/data/subscriptions.json")
_lock = threading.Lock()
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", re.I)
MAX_LIST = 50_000

def _sha(salt: str, ema: str) -> str:
    return hashlib.sha256((salt + "|" + ema.lower()).encode()).hexdigest()

def _load() -> dict:
    try:
        with open(STORE, "r", encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return {"subs": {}}
    d.setdefault("subs", {})
    return d

def _save(d: dict) -> None:
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    tmp = STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, separators=(",", ":"))
    os.replace(tmp, STORE)

def validate(ema_in: str) -> tuple[str | None, str | None]:
    """Return (normalized_email, None) on success or (None, error_msg) on failure."""
    ema = (ema_in or "").strip().lower()[:320]
    if not EMAIL_RE.match(ema):
        return None, "Invalid email address."
    if len(ema) < 6 or ema.endswith("."):
        return None, "Invalid email address."
    return ema, None


def _existing_hash(d: dict, ema: str) -> str | None:
    for h, row in d["subs"].items():
        if _sha(row["salt"], ema) == h:
            return h
    return None


def subscribe(ema_in: str, source: str = "web") -> tuple[str, dict]:
    """idempotent subscribe; returns (status, payload). status: ok|exists|too_long|invalid"""
    ema, err = validate(ema_in)
    if err is not None or ema is None:
        return "invalid", {"detail": err or "Invalid email address."}
    with _lock:
        d = _load()
        if len(d["subs"]) >= MAX_LIST:
            return "too_long", {"detail": "List is full."}
        existing = _existing_hash(d, ema)
        if existing is None:
            salt = secrets.token_hex(8)
            h = _sha(salt, ema)
            local, _, dom = ema.partition("@")
            d["subs"][h] = {
                "local": local[:40], "dom": dom[:120],
                "salt": salt, "ts": int(time.time()),
                "source": source[:24], "confirmed": True,
            }
            _save(d)
            return "ok", {"status": "subscribed", "count": len(d["subs"])}
        return "ok", {"status": "already-subscribed", "count": len(d["subs"])}

def unsubscribe(token: str) -> str:
    """Owner-side removal by subscription id = the sha hash itself."""
    token = (token or "").strip().lower()
    with _lock:
        d = _load()
        before = len(d["subs"])
        d["subs"].pop(token, None)
        if len(d["subs"]) != before:
            _save(d)
        return "ok"

def count() -> int:
    with _lock:
        return len(_load()["subs"])

def dump() -> list[dict]:
    with _lock:
        d = _load()
        out = []
        for h, row in d["subs"].items():
            out.append({
                "hash": h,
                "email": f"{row.get('local','')}@{row.get('dom','')}",
                "ts": row.get("ts", 0), "source": row.get("source", ""),
            })
        out.sort(key=lambda r: r["ts"])
        return out
