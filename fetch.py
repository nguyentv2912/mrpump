"""MR PUMP — thu dữ liệu on-chain thật (GeckoTerminal public API, Solana).

  python3 fetch.py scan    [--date YYYY-MM-DD]   # chụp token trending + rug-check (chạy lúc ~23:00 ICT)
  python3 fetch.py candles [--date YYYY-MM-DD]   # nến 5 phút của đêm 23:00→07:00 ICT (chạy sau 07:00)

--date là ngày bắt đầu đêm (giờ Việt Nam). Mặc định: đêm gần nhất đã kết thúc.
Lưu vào data/<date>/{trending.json, tokens.json, candles.json}.
"""
import json, os, sys, time, datetime as dt, urllib.request, urllib.error

API = "https://api.geckoterminal.com/api/v2"
ICT = dt.timezone(dt.timedelta(hours=7))
HERE = os.path.dirname(os.path.abspath(__file__))
_last = [0.0]

# Hai phiên mỗi ngày (giờ VN): đêm 23:00→07:00 và ngày 11:00→19:00
SESS = {
    "night": dict(start=23, a="23:00", b="07:00", one="ONE NIGHT", noun="night", till="the bot trades till 7am",
                  report="NIGHT REPORT", inone="in one night", log="night.log", wake="7am", ver="v2.0-night", suffix=""),
    "day": dict(start=11, a="11:00", b="19:00", one="ONE DAY", noun="day", till="the bot trades till 7pm",
                report="DAY REPORT", inone="in one day", log="day.log", wake="7pm", ver="v2.0-day", suffix="_day"),
}
SESSION = "night"


def S():
    return SESS[SESSION]


def get(path, tries=4):
    for i in range(tries):
        wait = 2.2 - (time.time() - _last[0])          # public API ~30 req/phút
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        req = urllib.request.Request(API + path, headers={"Accept": "application/json", "User-Agent": "mrpump-terminal/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(15 * (i + 1)); continue
            if e.code == 404:
                return None
            if i == tries - 1:
                raise
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(5)


def night_window(date):
    start = dt.datetime.combine(date, dt.time(S()["start"], 0), ICT)
    return start, start + dt.timedelta(hours=8)


def default_date():
    """Phiên gần nhất đã kết thúc."""
    now = dt.datetime.now(ICT)
    if SESSION == "day":
        return now.date() if now.hour >= 19 else now.date() - dt.timedelta(days=1)
    d = now.date() - dt.timedelta(days=1)
    if now.hour < 7:
        d -= dt.timedelta(days=1)
    return d


def tonight():
    """Phiên sắp tới (quét trước giờ bắt đầu ~10 phút). Đêm: từ 12:00 trở đi là đêm hôm nay."""
    now = dt.datetime.now(ICT)
    if SESSION == "day":
        return now.date()
    return now.date() if now.hour >= 12 else now.date() - dt.timedelta(days=1)


def ddir(date):
    p = os.path.join(HERE, "data", date.isoformat() + S()["suffix"])
    os.makedirs(p, exist_ok=True)
    return p


def f(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def scan(date, pages=3):
    pools = []
    for page in range(1, pages + 1):
        d = get(f"/networks/solana/trending_pools?include=base_token,quote_token,dex&page={page}&duration=24h")
        inc = {i["id"]: i["attributes"] for i in d.get("included", [])}
        for p in d["data"]:
            a, r = p["attributes"], p["relationships"]
            bt = inc.get(r["base_token"]["data"]["id"], {})
            qt = inc.get(r["quote_token"]["data"]["id"], {})
            pools.append({
                "pool": a["address"], "name": a["name"], "dex": r["dex"]["data"]["id"],
                "symbol": bt.get("symbol", a["name"].split("/")[0].strip()),
                "token": r["base_token"]["data"]["id"].split("_", 1)[1],
                "quote": qt.get("symbol", ""),
                "created": a["pool_created_at"], "liq": f(a["reserve_in_usd"]),
                "fdv": f(a["fdv_usd"]), "vol24": f(a["volume_usd"]["h24"]),
                "vol1h": f(a["volume_usd"]["h1"]),
                "chg": {k: f(v) for k, v in a["price_change_percentage"].items()},
                "buys24": a["transactions"]["h24"]["buys"], "sells24": a["transactions"]["h24"]["sells"],
                "traders24": a["transactions"]["h24"].get("unique_traders", 0),
            })
    seen, uniq = set(), []
    for p in pools:
        if p["token"] not in seen:
            seen.add(p["token"]); uniq.append(p)
    snap = {"captured_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "source": "GeckoTerminal trending_pools (solana, 24h)", "pools": uniq}
    json.dump(snap, open(os.path.join(ddir(date), "trending.json"), "w"), indent=1)

    tokens = {}
    for p in uniq:
        if p["quote"] not in ("SOL", "WSOL", "USDC", "USDT") or p["liq"] < 20_000:
            continue                                   # không cần rug-check thêm
        d = get(f"/networks/solana/tokens/{p['token']}/info")
        if not d:
            continue
        a = d["data"]["attributes"]
        h = a.get("holders") or {}
        dist = h.get("distribution_percentage") or {}
        tokens[p["token"]] = {
            "gt_score": f(a.get("gt_score")), "holders": h.get("count") or 0,
            "top10": f(dist.get("top_10"), 100.0), "mint": a.get("mint_authority"),
            "freeze": a.get("freeze_authority"), "honeypot": a.get("is_honeypot"),
            "dev_pct": f(a.get("developer_holding_percentage")), "categories": a.get("categories", []),
        }
    json.dump(tokens, open(os.path.join(ddir(date), "tokens.json"), "w"), indent=1)
    print(f"scan {date}: {len(uniq)} pool trending, rug-check {len(tokens)} token")


def candles(date):
    start, end = night_window(date)
    snap = json.load(open(os.path.join(ddir(date), "trending.json")))
    tokens = json.load(open(os.path.join(ddir(date), "tokens.json")))
    out = {"from": start.isoformat(), "to": end.isoformat(), "tf": "5m", "pools": {}}
    s0, e0 = int(start.timestamp()), int(end.timestamp())
    for p in snap["pools"]:
        if p["token"] not in tokens:
            continue
        d = get(f"/networks/solana/pools/{p['pool']}/ohlcv/minute?aggregate=5&before_timestamp={e0}&limit=110&currency=usd&token=base")
        if not d:
            continue
        rows = sorted(r for r in d["data"]["attributes"]["ohlcv_list"] if s0 - 3600 <= r[0] < e0)
        if len(rows) >= 30:
            out["pools"][p["pool"]] = rows
    json.dump(out, open(os.path.join(ddir(date), "candles.json"), "w"))
    print(f"candles {date}: {len(out['pools'])} pool có nến đêm {start:%d/%m %H:%M}→{end:%H:%M} ICT")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--session" in args:
        SESSION = args[args.index("--session") + 1]
    date = default_date()
    if "--date" in args:
        date = dt.date.fromisoformat(args[args.index("--date") + 1])
    cmd = args[0] if args else "all"
    if cmd == "scan" and "--date" not in args:
        date = tonight()
    if cmd in ("scan", "all"):
        scan(date)
    if cmd in ("candles", "all"):
        candles(date)
