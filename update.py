import json, os, urllib.request
CFG = {"1m": ("1m", "7d"), "5m": ("5m", "60d"), "15m": ("15m", "60d"), "1h": ("60m", "1y"), "1d": ("1d", "5y")}
CAP = {"1m": 20000, "5m": 40000, "15m": 40000, "1h": 9000, "1d": 3000}

def get(sym, iv, rg):
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval={iv}&range={rg}"
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    j = json.load(urllib.request.urlopen(r, timeout=40))["chart"]["result"][0]
    t = j["timestamp"]; q = j["indicators"]["quote"][0]
    out = []
    for i in range(len(t)):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None not in (o, h, l, c):
            out.append([t[i], round(o, 2), round(h, 2), round(l, 2), round(c, 2)])
    return out

os.makedirs("data", exist_ok=True)
for tf, (iv, rg) in CFG.items():
    new = None
    for sym in ["XAUUSD=X", "GC=F"]:
        try:
            new = get(sym, iv, rg)
        except Exception as e:
            print(tf, sym, "failed:", e)
            continue
        if new:
            print(tf, sym, len(new), "candles")
            break
    if not new:
        continue
    p = f"data/{tf}.json"
    old = json.load(open(p)) if os.path.exists(p) else []
    m = {c[0]: c for c in old}
    for c in new:
        m[c[0]] = c
    out = [m[k] for k in sorted(m)][-CAP[tf]:]
    json.dump(out, open(p, "w"), separators=(",", ":"))

# 4h candles built from 1h
p1 = "data/1h.json"
if os.path.exists(p1):
    b = {}
    for t, o, h, l, c in json.load(open(p1)):
        k = t - t % 14400
        if k not in b:
            b[k] = [k, o, h, l, c]
        else:
            x = b[k]; x[2] = max(x[2], h); x[3] = min(x[3], l); x[4] = c
    json.dump([b[k] for k in sorted(b)][-9000:], open("data/4h.json", "w"), separators=(",", ":"))
