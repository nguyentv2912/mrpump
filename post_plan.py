"""MR PUMP — kiểm tra trước khi hẹn đăng (chạy thử, KHÔNG gọi Buffer).

  python3 post_plan.py --session night|day [--date D] [--due 'YYYY-MM-DD HH:MM'] [--url <link raw>]

Kiểm tra: video + caption tồn tại, caption có nhãn bắt buộc, có bản quét ĐẦU phiên (không thiên lệch),
dữ liệu không cũ quá 24 giờ so với giờ đăng. In payload create_post cho TikTok + Instagram.
Mã thoát 0 = được đăng, 2 = không được đăng (lý do in ra).
"""
import os, sys, json, datetime as dt
import fetch

a = sys.argv[1:]
if "--session" in a:
    fetch.SESSION = a[a.index("--session") + 1]
S = fetch.S()
date = dt.date.fromisoformat(a[a.index("--date") + 1]) if "--date" in a else fetch.default_date()
HERE = os.path.dirname(os.path.abspath(__file__))
name = f"MR_PUMP_{date}{S['suffix']}"
mp4, txt = (os.path.join(HERE, "output", name + e) for e in (".mp4", ".txt"))
D = fetch.ddir(date)
LABEL = "paper trades trên giá thật · not financial advice"
TIKTOK, INSTA = "6ae71290e29c69a17125bdd6", "6ae71222e29c69a17125ba7a"
_, end = fetch.night_window(date)
now = dt.datetime.now(fetch.ICT)
due = (dt.datetime.strptime(a[a.index("--due") + 1], "%Y-%m-%d %H:%M").replace(tzinfo=fetch.ICT) if "--due" in a
       else (end.replace(hour=12, minute=0) if fetch.SESSION == "night" else end.replace(hour=20, minute=30)))
url = a[a.index("--url") + 1] if "--url" in a else "<link raw octo-videos>"

problems = []
if not os.path.exists(mp4):
    problems.append(f"thiếu video {name}.mp4")
cap = open(txt).read() if os.path.exists(txt) else ""
if not cap:
    problems.append(f"thiếu caption {name}.txt")
elif LABEL not in cap:
    problems.append(f'caption thiếu nhãn "{LABEL}"')
try:
    snap = json.load(open(os.path.join(D, "trending.json")))
    cap_at = dt.datetime.fromisoformat(snap["captured_at"])
    start, _ = fetch.night_window(date)
    if cap_at > start:
        problems.append(f"bản quét chụp lúc {cap_at.astimezone(fetch.ICT):%d/%m %H:%M}, SAU giờ bắt đầu phiên "
                        f"{start:%d/%m %H:%M} → thiên lệch chọn mẫu")
except FileNotFoundError:
    problems.append("không có bản quét đầu phiên")
age_h = (due - end).total_seconds() / 3600
if age_h > 24:
    problems.append(f"dữ liệu cũ {age_h:.1f} giờ so với giờ đăng {due:%d/%m %H:%M} (> 24 giờ)")
if due <= now:
    problems.append(f"giờ đăng {due:%d/%m %H:%M} đã qua")

base = dict(schedulingType="automatic", mode="customScheduled", dueAt=due.isoformat(timespec="seconds"), text=cap,
            assets=[{"video": {"url": url}}])
plan = [dict(base, channelId=TIKTOK, metadata={"tiktok": {"isAiGenerated": True}}),
        dict(base, channelId=INSTA, metadata={"instagram": {"type": "reel", "shouldShareToFeed": True, "isAiGenerated": True}})]
print(f"== {name} · phiên {S['a']}→{S['b']} kết thúc {end:%d/%m %H:%M} · giờ đăng dự kiến {due:%d/%m %H:%M} "
      f"(dữ liệu {age_h:.1f} giờ)")
if problems:
    print("KHÔNG ĐĂNG:\n  - " + "\n  - ".join(problems))
else:
    print("ĐƯỢC ĐĂNG. Payload Buffer create_post:")
print(json.dumps(plan, ensure_ascii=False, indent=1))
sys.exit(2 if problems else 0)
