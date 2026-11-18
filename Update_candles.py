#!/usr/bin/env python3
"""
تحديث شمعات الذهب (PAXGUSDT من Binance) وحفظها بملفات JSON داخل مجلد data/

- أول مرة (أو إذا ما في data/meta.json): بيجيب سنتين كاملين من شمعات الدقيقة
  وبيبني منها كل الفريمات (1m,5m,15m,1h,4h,1d).
- بعدين: بيجيب بس الشمعات الجديدة (آخر يوم تقريباً) وبيحدّث الملفات.

الملفات:
  data/<tf>.json            آخر فترة (بيحمّلها الشارت أول ما يفتح، سريعة)
  data/<tf>/YYYY-MM.json    أرشيف شهري للأقدم (بيتحمّل لما تسحب الشارت لورا)
  data/index.json           قائمة الأشهر المتوفرة بالأرشيف
  data/meta.json            علامة إنو الجلب الأول خلص
كل شمعة: [وقت_بالثواني, open, high, low, close]
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SYMBOL = "PAXGUSDT"
HOSTS = ["https://data-api.binance.vision", "https://api.binance.com"]
YEARS = 2
OUT = "data"
TFS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
# عدد الأيام بالملف الرئيسي. None = كل السنتين بالملف الرئيسي (بدون أرشيف)
WINDOW = {"1m": 7, "5m": 45, "15m": 120, "1h": None, "4h": None, "1d": None}
DAY = 86400


# ---------------------------------------------------------------- جلب
def fetch_klines(start_ms, end_ms):
    """بيرجع شمعات الدقيقة بين start_ms و end_ms (قائمة من مصفوفات Binance)."""
    qs = urllib.parse.urlencode({
        "symbol": SYMBOL, "interval": "1m",
        "startTime": start_ms, "endTime": end_ms, "limit": 1000})
    last = None
    for attempt in range(4):
        for host in HOSTS:
            try:
                req = urllib.request.Request(
                    f"{host}/api/v3/klines?{qs}",
                    headers={"User-Agent": "candles-bot"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    j = json.load(r)
                if isinstance(j, list):
                    return j
                last = RuntimeError(str(j))
            except Exception as e:  # noqa
                last = e
        time.sleep(2 * (attempt + 1))
    raise last


def fetch_range(since_s, now_s, pause=0.12):
    """بيجيب كل شمعات الدقيقة من since_s لهلأ، صفحة صفحة."""
    out = []
    cur = since_s * 1000
    end = now_s * 1000
    while cur < end:
        rows = fetch_klines(cur, end)
        if not rows:
            # ممكن يكون في فجوة (صيانة): نقفز ساعة ونكمل
            cur += 3600 * 1000
            continue
        for k in rows:
            out.append([int(k[0]) // 1000, float(k[1]), float(k[2]),
                        float(k[3]), float(k[4])])
        nxt = int(rows[-1][0]) + 60_000
        if nxt <= cur:
            break
        cur = nxt
        if len(rows) < 1000 and cur >= end - 60_000:
            break
        time.sleep(pause)
    return out


# ---------------------------------------------------------------- معالجة
def resample(c1m, sec):
    """بيبني شمعات فريم أكبر من شمعات الدقيقة."""
    out, cur = [], None
    for t, o, h, l, c in c1m:
        b = t - t % sec
        if cur is None or cur[0] != b:
            if cur:
                out.append(cur)
            cur = [b, o, h, l, c]
        else:
            if h > cur[2]:
                cur[2] = h
            if l < cur[3]:
                cur[3] = l
            cur[4] = c
    if cur:
        out.append(cur)
    return out


def rnd(rows):
    return [[r[0], round(r[1], 2), round(r[2], 2), round(r[3], 2),
             round(r[4], 2)] for r in rows]


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return None


def write(path, obj):
    """بيكتب بس إذا تغيّر المحتوى (عشان ما نعمل Commit بلا فايدة)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    txt = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == txt:
                return False
    except FileNotFoundError:
        pass
    with open(path, "w", encoding="utf-8") as f:
        f.write(txt)
    return True


def month_key(t):
    d = datetime.fromtimestamp(t, tz=timezone.utc)
    return f"{d.year}-{d.month:02d}"


def merge(old, new_from, rebuilt):
    """بيحتفظ بالقديم قبل new_from، وبيستبدل الباقي بالمعاد بناؤه."""
    keep = [r for r in (old or []) if r[0] < new_from]
    return keep + rebuilt


def archive(tf, rows, now_s):
    """بيحط الشمعات الأقدم من (نص الفترة) بملفات شهرية."""
    w = WINDOW[tf]
    cut = ((now_s - (w * DAY) // 2) // DAY) * DAY  # بيتغيّر مرة باليوم
    by_month = {}
    for r in rows:
        if r[0] < cut:
            by_month.setdefault(month_key(r[0]), []).append(r)
    for mk, part in by_month.items():
        path = f"{OUT}/{tf}/{mk}.json"
        have = {r[0]: r for r in (read(path) or [])}
        for r in part:
            have[r[0]] = r
        write(path, rnd([have[k] for k in sorted(have)]))


def list_chunks():
    idx = {}
    for tf in TFS:
        d = f"{OUT}/{tf}"
        if os.path.isdir(d):
            idx[tf] = sorted(f[:-5] for f in os.listdir(d)
                             if f.endswith(".json"))
    return idx


# ---------------------------------------------------------------- تشغيل
def main(argv):
    now_s = int(time.time())
    meta = read(f"{OUT}/meta.json")
    backfill = "--backfill" in argv or not meta

    if backfill:
        since = ((now_s - YEARS * 365 * DAY) // DAY) * DAY
        print("جلب أولي من", datetime.fromtimestamp(since, tz=timezone.utc))
    else:
        last1m = (read(f"{OUT}/1m.json") or [[now_s - 2 * DAY]])[-1][0]
        # لازم نرجع ليوم UTC كامل عشان نعيد بناء فريم اليوم بشكل صحيح
        since = (min(last1m - 3600, now_s - DAY) // DAY) * DAY

    c1m = fetch_range(since, now_s)
    if not c1m:
        print("ما إجا أي شمعات")
        return 0
    print("شمعات الدقيقة:", len(c1m))

    for tf, sec in TFS.items():
        rebuilt = c1m if tf == "1m" else resample(c1m, sec)
        main_path = f"{OUT}/{tf}.json"
        old = [] if backfill else (read(main_path) or [])
        rows = merge(old, since, rebuilt)
        w = WINDOW[tf]
        if w is None:
            keep_from = ((now_s - YEARS * 365 * DAY) // DAY) * DAY
            rows = [r for r in rows if r[0] >= keep_from]
        else:
            archive(tf, rows, now_s)
            keep_from = ((now_s - w * DAY) // DAY) * DAY
            rows = [r for r in rows if r[0] >= keep_from]
        write(main_path, rnd(rows))

    write(f"{OUT}/index.json", list_chunks())
    write(f"{OUT}/meta.json", {"backfill": now_s if backfill else meta["backfill"],
                               "updated": now_s})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
