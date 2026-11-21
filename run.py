"""MR PUMP — chạy trọn gói: dữ liệu thật -> lọc + paper trade -> hình -> nhạc + SFX -> mp4.

  python3 run.py [--session night|day] [--date YYYY-MM-DD] [--start 150] [--skip-fetch]

night = 23:00→07:00, day = 11:00→19:00 (giờ VN). Dùng bản quét đầu phiên đã lưu trong
data/<date>[_day]/ nếu có, rồi tải nến 5 phút của phiên.
Ra: output/MR_PUMP_<date>[_day].mp4 và .txt (caption gợi ý để đăng).
"""
import os, sys, json, subprocess, datetime as dt
import fetch

a = sys.argv[1:]
if "--session" in a:
    fetch.SESSION = a[a.index("--session") + 1]
import sim, render, audio  # noqa: E402  (sau khi chọn phiên)

date = dt.date.fromisoformat(a[a.index("--date") + 1]) if "--date" in a else fetch.default_date()
start = float(a[a.index("--start") + 1]) if "--start" in a else 150.0
S = fetch.S()
if "--skip-fetch" not in a:
    if not os.path.exists(os.path.join(fetch.ddir(date), "trending.json")):
        print(f"CẢNH BÁO: chưa có bản quét lúc {S['a']} cho phiên này -> quét bây giờ (có thiên lệch chọn mẫu)")
        fetch.scan(date)
    fetch.candles(date)
res = sim.run(date, start)
v = render.video(date)
w = audio.build(date)
name = f"MR_PUMP_{date}{S['suffix']}"
out = os.path.join(render.HERE, "output", name + ".mp4")
subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", v, "-i", w, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                "-af", "loudnorm=I=-14:TP=-1.5:LRA=7", "-ar", "44100", "-c:a", "aac", "-b:a", "192k", "-shortest",
                "-movflags", "+faststart", out], check=True)
os.remove(v); os.remove(w)
pct = (res["end"] / res["start"] - 1) * 100
cap = (f"MR PUMP · {S['noun']} {date:%d/%m} · {S['a']}→{S['b']} (UTC+7)\n"
       f"{res['scanned']} trending Solana tokens → {res['passed']} passed the rug check → {res['trades']} trades "
       f"({res['wins']}W/{res['losses']}L)\n"
       f"${res['start']:.0f} → ${res['end']:,.2f} ({pct:+.1f}%)\n"
       f"paper trades trên giá thật · not financial advice (data: GeckoTerminal)\n"
       f"#solana #memecoin #crypto #tradingbot #pumpfun")
open(os.path.join(render.HERE, "output", name + ".txt"), "w").write(cap)
r = subprocess.run(["ffmpeg", "-nostdin", "-i", out, "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
print("\n".join(l.strip() for l in r.splitlines()[-12:] if "I:" in l or "Peak:" in l))
print(json.dumps(dict(session=fetch.SESSION, date=str(date), file=out, start=res["start"], end=res["end"], pct=round(pct, 1),
                      trades=res["trades"], wins=res["wins"], losses=res["losses"])))
