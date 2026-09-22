"""howtosayword API — small, zero-deps-fastapi service.

Served under /api/ on the same origin (nginx proxies /api/ -> :8000).

Endpoints:
  GET  /healthz
  GET  /wotd                  word-of-the-day (deterministic per UTC date)
  POST /subscribe             {email, source?}
  GET  /count                 public list size
  POST /unsubscribe           {token}  (owner key)
  GET  /dump                  owner-keyed subscriber dump

Auth for owner endpoints:  X-Owner-Key header == $SUB_OWNER_KEY.
"""
import hashlib, json, os, time
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
import sub_store

app = FastAPI(title="howtosayword API", version="1.0")
OWNER_KEY = os.environ.get("SUB_OWNER_KEY", "")
WEB = os.environ.get("HTSW_BASE", "https://howtosayword.neurocircuit.xyz")

# ---------------- word corpus ----------------
_WORDS: list[str] | None = None
def words() -> list[str]:
    global _WORDS
    if _WORDS is None:
        try:
            with open("/data/site/words-index.json") as f:
                import json as _j
                _WORDS = sorted(_j.load(f).keys())
        except Exception:
            _WORDS = []
    return _WORDS

class SubIn(BaseModel):
    email: str = Field(min_length=5, max_length=300)
    source: str = Field(default="web", max_length=24)

class UnsubIn(BaseModel):
    token: str = Field(min_length=16, max_length=128)

def _owner(key: str | None) -> None:
    if not OWNER_KEY or key != OWNER_KEY:
        raise HTTPException(status_code=403, detail="forbidden")

# ---------------- routes ----------------
@app.get("/healthz")
def healthz():
    return {"ok": True, "ts": int(time.time()), "subs": sub_store.count(), "words": len(words())}

@app.get("/wotd")
def wotd():
    ws = words()
    day = time.strftime("%Y-%m-%d", time.gmtime())
    if not ws:
        raise HTTPException(status_code=503, detail="corpus index not ready")
    n = len(ws)
    i = int(hashlib.sha256(day.encode()).hexdigest(), 16) % n
    w = ws[i]
    return {"date": day, "word": w, "url": f"{WEB}/word/{w}/"}

@app.post("/subscribe", status_code=201)
def sub(payload: SubIn):
    status, payload_out = sub_store.subscribe(payload.email, payload.source)
    if status == "invalid":
        raise HTTPException(status_code=422, detail=payload_out.get("detail"))
    if status == "too_long":
        raise HTTPException(status_code=503, detail=payload_out.get("detail"))
    return payload_out

@app.get("/count")
def cnt():
    return {"subs": sub_store.count()}

@app.post("/unsubscribe")
def unsub(payload: UnsubIn, x_owner_key: str | None = Header(default=None)):
    _owner(x_owner_key)
    return sub_store.unsubscribe(payload.token)

@app.get("/dump")
def dump(x_owner_key: str | None = Header(default=None)):
    _owner(x_owner_key)
    return {"subs": sub_store.dump()}
