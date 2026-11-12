"""Monopoly Wallet backend (Flask) - state lives in Upstash Redis so it works on Vercel serverless."""
import json, os, random, secrets, time, urllib.request
from flask import Flask, request, jsonify

app = Flask(__name__)
COLORS = ["#e53935", "#1e88e5", "#43a047", "#fb8c00", "#8e24aa", "#00897b", "#d81b60", "#6d4c41"]
URL = os.environ.get("UPSTASH_REDIS_REST_URL") or os.environ.get("KV_REST_API_URL")
TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN") or os.environ.get("KV_REST_API_TOKEN")
TTL = 3 * 24 * 3600  # games auto-delete 3 days after last activity
_MEM = {}  # local-dev fallback when no Redis env vars are set


def redis(*cmds):
    """Run Redis commands in one round trip; returns list of results."""
    if not URL:
        if os.environ.get("VERCEL"):
            raise RuntimeError("Database not connected: add Upstash Redis in Vercel Storage, then redeploy")
        return _mem(cmds)
    req = urllib.request.Request(URL.rstrip("/") + "/pipeline", data=json.dumps(cmds).encode(),
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        out = json.load(r)
    for o in out:
        if o.get("error"):
            raise RuntimeError("Redis error: " + str(o["error"]))
    return [o.get("result") for o in out]


def _mem(cmds):
    out = []
    for c, *a in cmds:
        c, k = c.upper(), (a[0] if a else None)
        if c == "SET":
            if "NX" in a and k in _MEM: out.append(None)
            else: _MEM[k] = a[1]; out.append("OK")
        elif c == "GET": out.append(_MEM.get(k))
        elif c in ("RPUSH", "LPUSH"):
            l = _MEM.setdefault(k, []); l.append(a[1]) if c == "RPUSH" else l.insert(0, a[1]); out.append(len(l))
        elif c == "LRANGE": out.append(list(_MEM.get(k, [])))
        elif c == "LTRIM": _MEM[k] = _MEM.get(k, [])[: int(a[2]) + 1]; out.append("OK")
        elif c == "HSET": _MEM.setdefault(k, {})[str(a[1])] = str(a[2]); out.append(1)
        elif c == "HINCRBY":
            h = _MEM.setdefault(k, {}); h[str(a[1])] = str(int(h.get(str(a[1]), 0)) + int(a[2])); out.append(int(h[str(a[1])]))
        elif c == "HGETALL": out.append([x for kv in _MEM.get(k, {}).items() for x in kv])
        else: out.append(None)  # EXPIRE etc.
    return out


@app.errorhandler(Exception)
def crash(e):
    return jsonify(error=str(e)[:200]), 500


@app.route("/api/health")
def health():
    redis(("SET", "health", "ok"))
    return jsonify(ok=True, redis="connected" if URL else "memory (local only)")


def err(msg, code=400):
    return jsonify(error=msg), code


def clean(s, n):
    return str(s or "").strip()[:n]


def keys(code):
    return f"g:{code}:meta", f"g:{code}:players", f"g:{code}:bal", f"g:{code}:log"


def touch(code, *extra):
    return [("EXPIRE", k, TTL) for k in keys(code)] + list(extra)


def log(code, text):
    k = keys(code)[3]
    return [("LPUSH", k, json.dumps({"t": int(time.time()), "m": text})), ("LTRIM", k, 0, 39)]


def load(code):
    meta, players = keys(code)[:2]
    m, p = redis(("GET", meta), ("LRANGE", players, 0, -1))
    return (json.loads(m), [json.loads(x) for x in p]) if m else (None, [])


@app.route("/api/<path>", methods=["GET", "POST"])
def route(path):
    b, q = request.get_json(silent=True) or {}, request.args
    if path == "create":
        name, color = clean(b.get("name"), 14), b.get("color")
        try: start = int(b.get("start"))
        except (TypeError, ValueError): return err("Enter a valid starting amount")
        if not name or color not in COLORS or not 0 <= start <= 1000000:
            return err("Fill in name, colour and amount")
        for _ in range(20):
            code = "".join(random.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(4))
            if redis(("SET", keys(code)[0], json.dumps({"start": start}), "NX"))[0]: break
        else: return err("Try again", 503)
        tok = secrets.token_hex(8)
        _, pk, bk, _ = keys(code)
        redis(("RPUSH", pk, json.dumps({"id": 0, "token": tok, "name": name, "color": color})),
              ("HSET", bk, 0, start), *log(code, f"Game created. Everyone starts with ${start:,}"), *touch(code))
        return jsonify(code=code, token=tok)

    code = (q.get("code") or b.get("code") or "").upper()
    meta, players = load(code) if len(code) == 4 else (None, [])
    if not meta: return err("Game not found", 404)
    _, pk, bk, lk = keys(code)

    if path == "taken":
        return jsonify(taken=[p["color"] for p in players], start=meta["start"])

    if path == "join":
        name, color = clean(b.get("name"), 14), b.get("color")
        if not name or color not in COLORS: return err("Choose a name and colour")
        if any(p["color"] == color for p in players): return err("Colour already taken")
        if len(players) >= 8: return err("Game is full (8 players)")
        tok = secrets.token_hex(8)
        n = redis(("RPUSH", pk, json.dumps({"id": len(players), "token": tok, "name": name, "color": color})))[0]
        pid = n - 1
        redis(("HSET", bk, pid, meta["start"]), *log(code, f"{name} joined"), *touch(code))
        return jsonify(code=code, token=tok)

    me = next((p for p in players if p["token"] == (q.get("token") or b.get("token"))), None)
    if not me: return err("Not in this game", 403)

    if path == "state":
        flat, logs = redis(("HGETALL", bk), ("LRANGE", lk, 0, 39))
        bal = {flat[i]: int(flat[i + 1]) for i in range(0, len(flat), 2)}
        return jsonify(me=me["id"], host=me["id"] == 0, start=meta["start"], log=[json.loads(x) for x in logs],
                       players=[{"id": p["id"], "name": p["name"], "color": p["color"], "balance": bal.get(str(p["id"]), 0)} for p in players])

    if path == "adjust":
        if me["id"] != 0: return err("Only the banker can change money", 403)
        try: amt = int(b.get("amount"))
        except (TypeError, ValueError): return err("Enter an amount")
        if not 0 < amt <= 10000000 or b.get("op") not in ("add", "deduct"): return err("Invalid amount")
        sign, tid = (1 if b["op"] == "add" else -1), b.get("target")
        targets = players if tid == "all" else [p for p in players if p["id"] == tid]
        if not targets: return err("Player not found")
        if sign < 0:
            flat = redis(("HGETALL", bk))[0]
            bal = {flat[i]: int(flat[i + 1]) for i in range(0, len(flat), 2)}
            if any(bal.get(str(p["id"]), 0) < amt for p in targets): return err("Not enough money")
        who = "everyone" if tid == "all" else targets[0]["name"]
        note = clean(b.get("note"), 30)
        text = f"{'+' if sign > 0 else '-'}${amt:,} {'to' if sign > 0 else 'from'} {who}" + (f" ({note})" if note else "")
        redis(*[("HINCRBY", bk, p["id"], sign * amt) for p in targets], *log(code, text), *touch(code))
        return jsonify(ok=True)
    return err("Unknown request", 404)
