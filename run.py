"""MR PUMP — chạy trọn gói: dữ liệu thật -> lọc + paper trade -> hình -> nhạc + SFX -> mp4.

  python3 run.py [--date YYYY-MM-DD] [--start 150] [--skip-fetch]

Buổi sáng: dùng bản quét 23:00 đã lưu trong data/<date>/ nếu có, rồi tải nến của đêm.
"""
import os, sys, subprocess, datetime as dt
import fetch, sim, render, audio

a = sys.argv[1:]
date = dt.date.fromisoformat(a[a.index("--date") + 1]) if "--date" in a else fetch.default_date()
start = float(a[a.index("--start") + 1]) if "--start" in a else 150.0
if "--skip-fetch" not in a:
    if not os.path.exists(os.path.join(fetch.ddir(date), "trending.json")):
        print("CẢNH BÁO: chưa có bản quét lúc 23:00 cho đêm này -> quét bây giờ (có thiên lệch chọn mẫu)")
        fetch.scan(date)
    fetch.candles(date)
res = sim.run(date, start)
v = render.video(date) if "--audio-only" not in a else os.path.join(render.HERE, "output", f"mrpump_{date}_silent.mp4")
w = audio.build(date)
out = os.path.join(render.HERE, "output", f"MR_PUMP_{date}.mp4")
subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", v, "-i", w, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                "-af", "loudnorm=I=-14:TP=-1.5:LRA=7", "-ar", "44100", "-c:a", "aac", "-b:a", "192k", "-shortest",
                "-movflags", "+faststart", out], check=True)
os.remove(v); os.remove(w)
r = subprocess.run(["ffmpeg", "-nostdin", "-i", out, "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
print("\n".join(l.strip() for l in r.splitlines()[-12:] if "I:" in l or "Peak:" in l))
print(out)
