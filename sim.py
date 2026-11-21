"""MR PUMP — bộ lọc + paper trade trên nến 5 phút THẬT (không bịa giá).

  python3 sim.py [--date YYYY-MM-DD] [--start 150]   -> data/<date>/night.json

SCANNER  : token trending, quote SOL/USDC, thanh khoản ≥ $30k, vol 24h ≥ $200k, FDV ≤ $30M, ≥ 500 trader/24h
RUG CHECK: mint & freeze authority đã khoá, top 10 ví ≤ 35%, dev ≤ 10%, GT score ≥ 45, ≥ 500 holder
SIGNAL   : nến đóng > đỉnh 30 phút trước, volume ≥ 2× trung bình 1h, nến xanh -> vào ở giá mở nến sau
SIZER    : 24–40% vốn theo độ mạnh volume, tối đa 2 lệnh cùng lúc
EXECUTOR : trượt giá + phí 1,5% mỗi chiều; stop −8%, chốt +30%, trailing 10% khi đã lãi ≥ 10%, time stop 30 phút
"""
import json, os, sys, datetime as dt
import fetch
from fetch import ddir, default_date, night_window, ICT, S

R = dict(liq=30_000, vol24=200_000, fdv=30e6, traders=500, top10=35, dev=10, gt=45, holders=500,
         look=6, volx=2.0, slip=0.015, stop=0.08, tp=0.30, trail_on=0.10, trail=0.10, tstop=6, tmin=0.02, maxpos=2)


def scanner(p):
    if p["quote"] not in ("SOL", "WSOL", "USDC", "USDT"): return "quote not SOL/USDC"
    if p["liq"] < R["liq"]: return f"liq ${p['liq']/1e3:.0f}k < 30k"
    if p["vol24"] < R["vol24"]: return f"vol ${p['vol24']/1e3:.0f}k < 200k"
    if p["fdv"] > R["fdv"]: return f"fdv ${p['fdv']/1e6:.0f}M · not meme size"
    if p["traders24"] < R["traders"]: return f"{p['traders24']} traders < 500"


def rugcheck(t):
    if t["mint"] != "no": return "mint authority open"
    if t["freeze"] != "no": return "freeze authority open"
    if t["honeypot"] == "yes": return "honeypot"
    if t["top10"] > R["top10"]: return f"top 10 hold {t['top10']:.0f}%"
    if t["dev_pct"] > R["dev"]: return f"dev holds {t['dev_pct']:.0f}%"
    if t["gt_score"] < R["gt"]: return f"score {t['gt_score']:.0f} < 45"
    if t["holders"] < R["holders"]: return f"{t['holders']} holders"


def run(date, start_cap=150.0):
    D = ddir(date)
    snap = json.load(open(f"{D}/trending.json"))
    toks = json.load(open(f"{D}/tokens.json"))
    cd = json.load(open(f"{D}/candles.json"))
    n0, n1 = night_window(date)
    s0, e0 = int(n0.timestamp()), int(n1.timestamp())

    checks, passed = [], []
    for p in snap["pools"]:
        why, stage = scanner(p), "SCANNER"
        if not why:
            t = toks.get(p["token"])
            stage = "RUG CHECK"
            why = "no token info" if t is None else rugcheck(t)
        if not why and p["pool"] not in cd["pools"]:
            stage, why = "SCANNER", "no candles overnight"
        c = dict(symbol=p["symbol"].lstrip("$"), dex=p["dex"], liq=p["liq"], vol24=p["vol24"], fdv=p["fdv"],
                 top10=toks.get(p["token"], {}).get("top10"), holders=toks.get(p["token"], {}).get("holders"),
                 stage=stage, reason=why, ok=not why, pool=p["pool"])
        checks.append(c)
        if not why:
            passed.append(c)

    # tín hiệu
    sig = []
    for c in passed:
        rows = cd["pools"][c["pool"]]
        for i in range(12, len(rows) - 1):
            ts, o, h, l, cl, v = rows[i]
            if not (s0 <= ts < e0 - 1800): continue
            hi = max(r[2] for r in rows[i - R["look"]:i])
            av = sum(r[5] for r in rows[i - 12:i]) / 12 or 1e-9
            if cl > hi and v >= R["volx"] * av and cl > o:
                sig.append((rows[i + 1][0], c["symbol"], c["pool"], i + 1, v / av, (cl / hi - 1)))
    sig.sort()

    cash, open_pos, trades, last_entry = start_cap, [], [], {}
    events = []

    def equity_at(ts):
        return cash + sum(p["qty"] * price_at(p["pool"], ts) for p in open_pos)

    def price_at(pool, ts):
        best = None
        for r in cd["pools"][pool]:
            if r[0] <= ts: best = r[4]
        return best

    def close(p, ts, px, why):
        nonlocal cash
        out = px * (1 - R["slip"])
        cash += p["qty"] * out
        pnl = p["qty"] * out - p["cost"]
        p.update(exit_ts=ts, exit=out, pnl=pnl, why=why)
        trades.append(p)
        events.append(dict(t=ts, kind="exit", sym=p["sym"], pnl=pnl, why=why, eq=None, pct=out / p["entry"] - 1))

    def step_positions(upto):
        for p in list(open_pos):
            rows = cd["pools"][p["pool"]]
            while p["k"] < len(rows) and rows[p["k"]][0] < upto:
                ts, o, h, l, cl, v = rows[p["k"]]
                p["k"] += 1
                if ts < p["ts"]: continue
                p["bars"] += 1
                stop = p["entry"] * (1 - R["stop"])
                if p["peak"] >= p["entry"] * (1 + R["trail_on"]):
                    stop = max(stop, p["peak"] * (1 - R["trail"]))
                if l <= stop:
                    trail = stop > p["entry"] * (1 - R["stop"]) + 1e-12
                    close(p, ts + 300, min(o, stop), "trailing stop hit" if trail else "stop 8% hit"); open_pos.remove(p); break
                if h >= p["entry"] * (1 + R["tp"]):
                    close(p, ts + 300, max(o, p["entry"] * (1 + R["tp"])), "take-profit +30%"); open_pos.remove(p); break
                p["peak"] = max(p["peak"], h)
                if p["bars"] >= R["tstop"] and cl < p["entry"] * (1 + R["tmin"]):
                    close(p, ts + 300, cl, "time stop 30m"); open_pos.remove(p); break

    for ts, sym, pool, k, vx, brk in sig:
        step_positions(ts)
        if any(p["pool"] == pool for p in open_pos) or len(open_pos) >= R["maxpos"]:
            events.append(dict(t=ts, kind="skip", sym=sym, why="busy · max 2 open" if len(open_pos) >= R["maxpos"] else "already in"))
            continue
        if ts - last_entry.get(pool, 0) < 1800:
            continue
        eq = equity_at(ts)
        size = min(0.40, max(0.24, 0.24 + 0.04 * (vx - 2)))
        rows = cd["pools"][pool]
        px = rows[k][1] * (1 + R["slip"])
        cost = min(cash, eq * size)
        if cost < 1: continue
        cash -= cost
        p = dict(sym=sym, pool=pool, ts=ts, entry=px, qty=cost / px, cost=cost, size=size, k=k, bars=0, peak=px,
                 reason=f"breakout {brk*100:+.1f}% over 30m high · vol {vx:.1f}×")
        open_pos.append(p)
        last_entry[pool] = ts
        events.append(dict(t=ts, kind="enter", sym=sym, size=size, why=p["reason"], price=px, eq=None))
    step_positions(e0 + 3600)
    for p in list(open_pos):
        close(p, e0, price_at(p["pool"], e0), "closed at " + S()["b"]); open_pos.remove(p)

    events.sort(key=lambda e: (e["t"], e["kind"] != "exit"))
    eq = start_cap
    for e in events:
        if e["kind"] == "exit":
            eq += e["pnl"]
        e["bal"] = round(eq, 2)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    res = dict(session=fetch.SESSION, date=date.isoformat(), window=[n0.isoformat(), n1.isoformat()], start=start_cap,
               end=round(start_cap + sum(t["pnl"] for t in trades), 2), trades=len(trades), wins=wins,
               losses=len(trades) - wins, scanned=len(checks), passed=len(passed),
               filtered=len(checks) - len(passed), rules=R, captured_at=snap["captured_at"],
               source="GeckoTerminal public API · Solana · 5m OHLCV",
               checks=checks, events=events,
               trades_detail=[{k: v for k, v in t.items() if k not in ("k",)} for t in trades])
    json.dump(res, open(f"{D}/night.json", "w"), indent=1, default=float)
    print(f"{date}: quét {len(checks)}, qua lọc {len(passed)}, {len(sig)} tín hiệu, {len(trades)} lệnh "
          f"({wins}W/{len(trades)-wins}L), ${start_cap:.2f} -> ${res['end']:.2f}")
    return res


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--session" in a:
        fetch.SESSION = a[a.index("--session") + 1]
    d = dt.date.fromisoformat(a[a.index("--date") + 1]) if "--date" in a else default_date()
    s = float(a[a.index("--start") + 1]) if "--start" in a else 150.0
    run(d, s)
