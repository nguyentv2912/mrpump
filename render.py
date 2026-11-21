"""MR PUMP Terminal v2 — vẽ video từ data/<date>/{night.json, candles.json} (PIL -> ffmpeg).

  python3 render.py [--date D] still 0.5 2 9 18 27     # xem trước vài khung
  python3 render.py [--date D] video [--jobs 4]        # output/mrpump_<date>_silent.mp4

Dòng thời gian (29 s):
  0–0,95  hook: thẻ kết quả thật của đêm (flash-forward) rồi tua ngược
  0,95–2,4 quét token trending (PASS / FILTERED)
  2,6–26  đêm 23:00 → 07:00 theo giờ thật của từng nến/lệnh
  26–29   thẻ NIGHT REPORT
"""
import json, math, os, subprocess, sys, datetime as dt
from multiprocessing import Pool
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from fetch import ddir, default_date, ICT

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, TH, OY = 1080, 1920, 1440, 240          # khung vẽ nội bộ (terminal 3:4 ở y=240)
# Bố cục TikTok: tránh tab trên (~0–150), nút phải (~x>960 ở giữa màn) và caption dưới (~y>1580)
TITLE_Y, CAP_Y = 150, 214
FPS, T0, T1, TEND = 30, 2.6, 26.0, 29.0
HOOK, SCAN0, SCAN_END = 0.95, 1.0, 2.4

BG, PANEL, LINE, DIM, TXT = (8, 22, 16), (11, 29, 21), (34, 66, 50), (120, 148, 132), (226, 238, 230)
GREEN, PINK, ORANGE, PURPLE, BLUE, YELLOW, GREY = (61, 220, 132), (255, 77, 122), (255, 159, 67), (167, 139, 250), (79, 163, 255), (245, 197, 66), (150, 160, 155)

JB = "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-{}.ttf"
INTER = "/usr/share/fonts/opentype/inter/Inter-{}.otf"
_fc = {}


def F(kind, size):
    k = (kind, size)
    if k not in _fc:
        path = JB.format(kind) if kind in ("Regular", "Medium", "Bold", "ExtraBold", "SemiBold") else INTER.format(kind[1:])
        _fc[k] = ImageFont.truetype(path, size)
    return _fc[k]


def money(v, sign=False):
    s = f"${abs(v):,.2f}"
    return (("+" if v >= 0 else "-") + s) if sign else ("-" + s if v < 0 else s)


def short(v):
    return f"${v/1e6:.1f}M" if v >= 1e6 else f"${v/1e3:.0f}k"


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def back(x):                                   # nảy quá rồi về
    x = max(0.0, min(1.0, x))
    c = 1.9
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def alpha(c, a):
    return tuple(int(BG[i] + (c[i] - BG[i]) * a) for i in range(3))


def rr(d, box, r, fill=None, outline=None, width=2):
    d.rounded_rectangle(box, r, fill=fill, outline=outline, width=width)


def dashed_rr(d, box, r, color, width=2, dash=9, gap=6):
    x0, y0, x1, y1 = box
    for (ax, ay, bx, by) in ((x0 + r, y0, x1 - r, y0), (x0 + r, y1, x1 - r, y1), (x0, y0 + r, x0, y1 - r), (x1, y0 + r, x1, y1 - r)):
        L = max(abs(bx - ax), abs(by - ay))
        s = 0
        while s < L:
            e = min(L, s + dash)
            if ax == bx:
                d.line((ax, ay + s, ax, ay + e), fill=color, width=width)
            else:
                d.line((ax + s, ay, ax + e, ay), fill=color, width=width)
            s += dash + gap
    for cx, cy, a0 in ((x0 + r, y0 + r, 180), (x1 - r, y0 + r, 270), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90)):
        d.arc((cx - r, cy - r, cx + r, cy + r), a0, a0 + 90, fill=color, width=width)


def glow_sprite(size, color, radius=18, r=16, strength=1.0, width=6):
    w, h = size
    pad = radius * 2
    im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((pad, pad, pad + w, pad + h), r, outline=color + (int(255 * strength),), width=width)
    return im.filter(ImageFilter.GaussianBlur(radius)), pad


def circle_glow(rad, color, blur=22):
    pad = blur * 2
    s = 2 * (rad + pad)
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((pad, pad, s - pad, s - pad), outline=color + (255,), width=10)
    return im.filter(ImageFilter.GaussianBlur(blur)), rad + pad


def paste_a(im, sprite, xy, a):
    if a <= 0:
        return
    if a < 1:
        sprite = sprite.copy()
        sprite.putalpha(sprite.getchannel("A").point(lambda v: int(v * a)))
    im.paste(sprite, (int(xy[0]), int(xy[1])), sprite)


def text_sprite(text, font, color, stroke=0, sc=(0, 0, 0)):
    b = font.getbbox(text, stroke_width=stroke)
    im = Image.new("RGBA", (b[2] - b[0] + 8, b[3] - b[1] + 8), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((4 - b[0], 4 - b[1]), text, font=font, fill=color, stroke_width=stroke, stroke_fill=sc)
    return im


def odometer(im, xr, y, old, new, k, font, color):
    """Số lăn kiểu đồng hồ cơ, căn phải tại xr. k: 0→1."""
    n = max(len(old), len(new))
    old, new = old.rjust(n), new.rjust(n)
    cw = font.getlength("0")
    asc, desc = font.getmetrics()
    lh = asc + desc
    x = xr - cw * n
    d = ImageDraw.Draw(im)
    for i, (a, b) in enumerate(zip(old, new)):
        cx = x + i * cw
        if a == b or k >= 1:
            if b != " ":
                d.text((cx, y), b, font=font, fill=color)
            continue
        kk = ease(min(1, k * (1.0 + 0.12 * (n - i))))          # chữ số bên phải lăn nhanh hơn
        tile = Image.new("RGBA", (int(cw) + 2, lh), (0, 0, 0, 0))
        td = ImageDraw.Draw(tile)
        off = int(kk * lh)
        td.text((0, -off), a, font=font, fill=color + (int(255 * (1 - kk * 0.7)),))
        td.text((0, lh - off), b, font=font, fill=color)
        im.paste(tile, (int(cx), int(y)), tile)


# ---------------------------------------------------------------- mascot Mr Pump (vẽ bằng code)
def mascot(size, mood="ok"):
    S = size * 4
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i in range(60):
        t = i / 59
        c = (int(40 + 60 * t), int(170 + 70 * t), int(100 + 50 * t), 255)
        m = int(S * 0.08 + t * S * 0.06)
        d.ellipse((m, m + int(S * 0.04), S - m, S - m + int(S * 0.02)), fill=c)
    d.polygon([(S * .5, S * .02), (S * .62, S * .16), (S * .54, S * .16), (S * .54, S * .24), (S * .46, S * .24), (S * .46, S * .16), (S * .38, S * .16)], fill=(245, 197, 66, 255))
    d.rounded_rectangle((S * .2, S * .38, S * .47, S * .55), int(S * .06), fill=(10, 14, 12, 255))
    d.rounded_rectangle((S * .53, S * .38, S * .8, S * .55), int(S * .06), fill=(10, 14, 12, 255))
    d.rectangle((S * .45, S * .42, S * .55, S * .46), fill=(10, 14, 12, 255))
    d.line((S * .26, S * .42, S * .33, S * .42), fill=(120, 255, 190, 255), width=int(S * .02))
    d.line((S * .59, S * .42, S * .66, S * .42), fill=(120, 255, 190, 255), width=int(S * .02))
    if mood == "win":                                       # cười toác
        d.chord((S * .32, S * .52, S * .72, S * .8), 0, 180, fill=(10, 30, 20, 255))
        d.chord((S * .4, S * .66, S * .64, S * .8), 0, 180, fill=(255, 110, 130, 255))
    elif mood == "loss":                                    # mếu + giọt mồ hôi
        d.arc((S * .36, S * .64, S * .68, S * .86), 200, 340, fill=(10, 30, 20, 255), width=int(S * .035))
        d.ellipse((S * .78, S * .3, S * .9, S * .46), fill=(120, 200, 255, 255))
        d.polygon([(S * .84, S * .2), (S * .79, S * .35), (S * .89, S * .35)], fill=(120, 200, 255, 255))
    else:
        d.arc((S * .33, S * .5, S * .72, S * .78), 15, 160, fill=(10, 30, 20, 255), width=int(S * .035))
    return im.resize((size, size), Image.LANCZOS)


# ---------------------------------------------------------------- dữ liệu -> trạng thái
class Story:
    def __init__(self, night, candles=None):
        self.n = night
        self.s0 = dt.datetime.fromisoformat(night["window"][0]).timestamp()
        self.s1 = dt.datetime.fromisoformat(night["window"][1]).timestamp()
        self.pool_of = {c["symbol"]: c["pool"] for c in night["checks"] if c["ok"]}
        self.rows_of = {}
        if candles:
            for sym, pool in self.pool_of.items():
                if pool in candles["pools"]:
                    self.rows_of[sym] = candles["pools"][pool]
        self.items = []
        checks = night["checks"]
        for i, c in enumerate(checks):
            self.items.append((SCAN0 + (SCAN_END - SCAN0) * (i + 0.5) / len(checks), "check", c))
        for e in night["events"]:
            if e["kind"] == "skip" and not e["why"].startswith("busy"):
                continue
            self.items.append((self.vt(e["t"]), e["kind"], e))
        # nhịp thị trường thật: mỗi nến 5 phút, token qua lọc biến động mạnh nhất
        self.pulses = []
        if self.rows_of:
            ts = int(self.s0)
            while ts < self.s1:
                best = None
                for sym, rows in self.rows_of.items():
                    for i, r in enumerate(rows):
                        if r[0] == ts and i >= 12 and r[1] > 0:
                            av = sum(x[5] for x in rows[i - 12:i]) / 12 or 1e-9
                            pct = r[4] / r[1] - 1
                            if best is None or abs(pct) > abs(best["pct"]):
                                best = dict(sym=sym, pct=pct, volx=r[5] / av, t=ts)
                            break
                if best:
                    self.items.append((self.vt(ts + 300), "pulse", best))
                    self.pulses.append(best)
                ts += 300
        self.items.sort(key=lambda x: x[0])
        # LOG + tail
        self.rows, self.tail = [], []
        self.rows.append((SCAN0, "23:00", "SCAN", None, f"{night['scanned']} trending pools", "GeckoTerminal · Solana", "", DIM))
        self.rows.append((SCAN_END, "23:00", "CHECK", None, f"{night['passed']} pass · {night['filtered']} blocked", "mint/freeze · top10 · liq · vol", "", DIM))
        self.curve = [(T0, night["start"])]
        for vt, k, p in self.items:
            if k == "check":
                if p["ok"]:
                    self.tail.append((vt, f"PASS  ${p['symbol']}", f"liq {short(p['liq'])} · top10 {p['top10']:.0f}%", GREEN))
                else:
                    self.tail.append((vt, f"BLOCK ${p['symbol']}", p["reason"], PINK))
            elif k in ("enter", "exit"):
                hh = dt.datetime.fromtimestamp(p["t"], ICT).strftime("%H:%M")
                if k == "enter":
                    self.rows.append((vt, hh, "ENTER", p["sym"], p["sym"], p["why"], f"size {p['size']*100:.0f}%", TXT))
                    self.tail.append((vt, f"{hh} ENTER ${p['sym']} {p['size']*100:.0f}%", p["why"].replace(" over 30m high", ""), ORANGE))
                else:
                    self.rows.append((vt, hh, "EXIT", p["sym"], p["sym"], p["why"], money(p["pnl"], True), GREEN if p["pnl"] > 0 else PINK))
                    self.tail.append((vt, f"{hh} EXIT  ${p['sym']} {money(p['pnl'], True)}", p["why"], GREEN if p["pnl"] > 0 else PINK))
                    self.curve.append((vt, p["bal"]))
        self.sym_color = {}
        pal = [ORANGE, BLUE, GREEN, PINK, PURPLE, YELLOW, (90, 220, 230)]
        for c in checks:
            self.sym_color.setdefault(c["symbol"], pal[len(self.sym_color) % len(pal)])
        self.entries = {}
        for e in night["events"]:
            if e["kind"] == "enter":
                self.entries.setdefault(e["sym"], []).append(e)

    def vt(self, ts):
        return T0 + (T1 - T0) * (ts - self.s0) / (self.s1 - self.s0)

    def ts_at(self, t):
        x = min(1.0, max(0.0, (t - T0) / (T1 - T0)))
        return self.s0 + x * (self.s1 - self.s0)

    def clock(self, t):
        return dt.datetime.fromtimestamp(self.ts_at(t), ICT)

    def entry_for(self, p):
        best = None
        for e in self.entries.get(p["sym"], []):
            if e["t"] <= p["t"]:
                best = e
        return best

    def state(self, t):
        n = self.n
        st = dict(bal=n["start"], prev_bal=n["start"], bal_t=-9, trades=0, wins=0, losses=0, cnt_t=-9, prev=(0, 0, 0),
                  checked=0, filtered=0, passed=0, line=2, last=None, last_t=-9, lastk=None, chips=[], sizer=None,
                  equity=None, open={}, trade=None, pulse_t=-9, last_exit=None, last_enter=None)
        for vt, k, p in self.items:
            if vt > t:
                break
            if k == "pulse":
                st["pulse_t"] = vt
                st["chips"].append((vt, p["sym"], "pulse", f"{p['pct']*100:+.1f}% 5m · {p['volx']:.1f}×", p))
                continue
            st["last"], st["last_t"], st["lastk"] = p, vt, k
            if k == "check":
                st["checked"] += 1
                st["passed" if p["ok"] else "filtered"] += 1
                st["chips"].append((vt, p["symbol"], p["ok"], p["reason"] or f"liq {short(p['liq'])} · top10 {p['top10']:.0f}%", p))
            elif k == "skip":
                st["chips"].append((vt, p["sym"], None, p["why"], p))
            elif k == "enter":
                st["line"] += 1
                st["open"][p["sym"]] = p
                st["sizer"] = p
                st["trade"] = ("enter", p, vt)
                st["last_enter"] = (vt, p)
                st["chips"].append((vt, p["sym"], True, "ENTER · " + p["why"].split(" · ")[1], p))
            elif k == "exit":
                st["line"] += 1
                st["open"].pop(p["sym"], None)
                st["prev"] = (st["trades"], st["wins"], st["losses"])
                st["trades"] += 1
                st["wins" if p["pnl"] > 0 else "losses"] += 1
                st["cnt_t"] = vt
                st["prev_bal"], st["bal"], st["bal_t"] = st["bal"], p["bal"], vt
                st["equity"] = p
                st["trade"] = ("exit", p, vt)
                st["last_exit"] = (vt, p)
        return st


# ---------------------------------------------------------------- hoạ sĩ
class Painter:
    """Bố cục dọc 9:16 cho TikTok: terminal phủ kín khung, agent thành dải ngang, chữ lớn."""
    AG = [("SCANNER", ORANGE, "SCANNER"), ("RUG CHECK", PINK, "RUG CHECK"), ("SIZER", PURPLE, "SIZER"),
          ("EXECUTOR", GREEN, "EXECUTOR"), ("LOGGER", ORANGE, "LOGGER"), ("EQUITY", BLUE, "EQUITY"), ("YOU", TXT, "YOU")]
    FX0, FX1, FY0, FY1 = 16, 1064, 258, 1892
    PX0, PX1 = 24, 1056
    TILE_W, TILE_Y0, TILE_Y1 = 142, 474, 600

    def __init__(self, story):
        self.s = story
        n = story.n
        self.m = {k: mascot(120, k) for k in ("ok", "win", "loss")}
        self.ms = {k: mascot(120, k) for k in ("ok", "win", "loss")}
        self.mb = {k: mascot(130, k) for k in ("ok", "win", "loss")}
        self.base = self.build_base()
        self.g_agent = {name: glow_sprite((self.TILE_W, self.TILE_Y1 - self.TILE_Y0), col, 12, 14, 0.9) for name, col, _ in self.AG}
        self.g_node = {lab: circle_glow(r + 6, col) for x, y, r, col, lab in self.nodes}
        self.g_gold = circle_glow(84, YELLOW, 26)
        self.g_loss = glow_sprite((self.FX1 - self.FX0, self.FY1 - self.FY0), PINK, 26, 22, 1.0, 14)
        self.pct = (n["end"] / n["start"] - 1) * 100
        self.captions = [(0.0, "ONE NIGHT. REAL CHARTS.", YELLOW),
                         (HOOK, f"{n['scanned']} trending tokens → {n['filtered']} rejected", TXT),
                         (T0, f"{n['passed']} passed the rug check", GREEN),
                         (8.5, "the bot trades till 7am", TXT),
                         (14.5, "every trade gets a reason", TXT),
                         (20.0, f"{n['trades']} trades · {n['wins']} W / {n['losses']} L", TXT),
                         (T1, f"{self.pct:+.1f}% in one night · paper", GREEN if self.pct >= 0 else PINK)]
        self.cap_sprites = [(t0, text_sprite(txt, F("iExtraBold", 46), c)) for t0, txt, c in self.captions]
        self.title = text_sprite("MR PUMP", F("iExtraBold", 72), YELLOW)
        self._end_core = None

    def tile_x(self, i):
        return self.PX0 + i * (self.TILE_W + 6)

    # ------------------------------------------------------------ nền tĩnh
    def build_base(self):
        n = self.s.n
        base = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(base)
        for y in range(self.FY0 + 20, self.FY1 - 10, 24):
            for x in range(self.FX0 + 10, self.FX1 - 6, 24):
                d.point((x, y), fill=(18, 40, 30))
        rr(d, (self.FX0, self.FY0, self.FX1, self.FY1), 24, outline=LINE, width=2)
        for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
            d.ellipse((36 + i * 24, 272, 50 + i * 24, 286), fill=c)
        date_s = dt.datetime.fromisoformat(n["window"][0]).strftime("%d %b %Y")
        d.text((470, 279), f"Solana · {date_s} · 23:00→07:00", font=F("Regular", 19), fill=DIM, anchor="mm")
        dashed_rr(d, (836, 264, 1050, 294), 8, GREEN, 2, 6, 4)
        d.text((943, 279), "paper · real prices", font=F("Medium", 17), fill=GREEN, anchor="mm")
        d.line((self.FX0 + 2, 302, self.FX1 - 2, 302), fill=LINE, width=1)
        # header
        d.ellipse((30, 314, 166, 450), fill=(14, 36, 26), outline=LINE, width=2)
        f = F("ExtraBold", 34)
        d.text((184, 316), "MR PUMP", font=f, fill=YELLOW)
        d.text((184 + f.getlength("MR PUMP "), 316), "Terminal", font=f, fill=TXT)
        bx = 184 + f.getlength("MR PUMP Terminal ")
        dashed_rr(d, (bx, 322, bx + 108, 350), 6, YELLOW, 2, 5, 3)
        d.text((bx + 54, 336), "v2.0-night", font=F("Medium", 15), fill=YELLOW, anchor="mm")
        d.text((1046, 376), "balance", font=F("Regular", 18), fill=DIM, anchor="ra")
        for x, lab in ((770, "trades"), (890, "wins"), (1000, "losses")):
            d.text((x, 446), lab, font=F("Regular", 17), fill=DIM, anchor="ma")
        d.line((self.FX0 + 2, 466, self.FX1 - 2, 466), fill=LINE, width=1)
        for i in range(len(self.AG)):
            self.agent_tile(d, i, False)
        # panels
        P = [(660, 1094), (1400, 1540), (1552, 1884)]
        for y0, y1 in P:
            rr(d, (self.PX0, y0, self.PX1, y1), 18, outline=LINE, width=2)
        rr(d, (self.PX0, 1106, 534, 1388), 18, outline=LINE, width=2)
        rr(d, (546, 1106, self.PX1, 1388), 18, outline=LINE, width=2)
        d.text((40, 672), "LIVE FLOW · SCAN → CHECK → SIZE → EXEC → LOG", font=F("Medium", 18), fill=DIM)
        d.text((40, 1118), "TRADE · 5m CANDLES", font=F("Medium", 18), fill=DIM)
        d.text((562, 1118), "$ tail -f night.log", font=F("Medium", 19), fill=TXT)
        d.text((40, 1412), "RESULT · equity curve", font=F("Medium", 18), fill=DIM)
        d.text((40, 1564), "LOG · every trade gets a reason", font=F("Medium", 18), fill=DIM)
        self.nodes = [(250, 874, 54, PINK, "RUG CHECK"), (540, 874, 74, GREEN, "MR PUMP"), (830, 874, 54, GREEN, "EXECUTOR")]
        for (ax, ay, ar, _, _), (bx_, by, br, _, _) in zip(self.nodes, self.nodes[1:]):
            for x in range(ax + ar + 8, bx_ - br - 6, 14):
                d.ellipse((x - 3, ay - 3, x + 3, ay + 3), fill=LINE)
        for x, y, r, col, lab in self.nodes:
            d.ellipse((x - r, y - r, x + r, y + r), fill=(12, 26, 20), outline=col, width=4)
        self.icon(d, "RUG CHECK", 250, 874, big=True)
        self.icon(d, "EXECUTOR", 830, 874, big=True)
        self.cards = [(PINK, "FILTERED"), (PURPLE, "SIZER"), (ORANGE, "LOGGER"), (BLUE, "EQUITY")]
        for i, (col, lab) in enumerate(self.cards):
            x0 = 36 + i * 254
            dashed_rr(d, (x0, 986, x0 + 244, 1082), 12, alpha(col, .7), 2, 7, 5)
            d.text((x0 + 14, 994), "• " + lab, font=F("Medium", 17), fill=col)
        return base

    def agent_tile(self, d, i, on):
        name, col, _ = self.AG[i]
        x0, y0, y1 = self.tile_x(i), self.TILE_Y0, self.TILE_Y1
        if on:
            rr(d, (x0, y0, x0 + self.TILE_W, y1), 14, fill=alpha(col, .16))
            dashed_rr(d, (x0, y0, x0 + self.TILE_W, y1), 14, col, 2, 7, 4)
        else:
            rr(d, (x0, y0, x0 + self.TILE_W, y1), 14, outline=(24, 48, 36), width=2)
        cx = x0 + self.TILE_W // 2
        rr(d, (cx - 26, y0 + 10, cx + 26, y0 + 62), 13, fill=(alpha(col, 1 if on else .8) if name != "YOU" else (235, 240, 236)))
        self.icon(d, name, cx, y0 + 36)
        d.text((cx, y0 + 70), name, font=F("Bold", 17), fill=col, anchor="ma")

    def icon(self, d, name, cx, cy, big=False):
        k = 1.5 if big else 1.0
        c = (20, 20, 20) if not big else None
        if name == "SCANNER":
            for r in (15, 10, 4):
                d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=c, width=3)
        elif name == "RUG CHECK":
            col = c or PINK
            s = 13 * k
            d.polygon([(cx, cy - s - 2), (cx + s, cy - s * .6), (cx + s * .85, cy + s * .4), (cx, cy + s + 2), (cx - s * .85, cy + s * .4), (cx - s, cy - s * .6)], outline=col, width=3)
            d.line([(cx - s * .4, cy), (cx - s * .05, cy + s * .35), (cx + s * .5, cy - s * .35)], fill=col, width=3)
        elif name == "SIZER":
            d.line((cx, cy - 13, cx, cy + 12), fill=c, width=3)
            d.line((cx - 13, cy - 7, cx + 13, cy - 7), fill=c, width=3)
            d.arc((cx - 17, cy - 9, cx - 5, cy + 5), 0, 180, fill=c, width=3)
            d.arc((cx + 5, cy - 9, cx + 17, cy + 5), 0, 180, fill=c, width=3)
            d.line((cx - 8, cy + 13, cx + 8, cy + 13), fill=c, width=3)
        elif name == "EXECUTOR":
            col = c or GREEN
            s = 1.6 if big else 1.1
            pts = [(2, -12), (-7, 2), (0, 2), (-3, 13), (8, -3), (1, -3), (4, -12)]
            d.polygon([(cx + x * s, cy + y * s) for x, y in pts], fill=col)
        elif name == "LOGGER":
            d.rounded_rectangle((cx - 10, cy - 13, cx + 10, cy + 13), 3, outline=c, width=3)
            for yy in (-5, 1, 7):
                d.line((cx - 5, cy + yy, cx + 5, cy + yy), fill=c, width=2)
        elif name == "EQUITY":
            d.line([(cx - 13, cy + 8), (cx - 5, cy), (cx + 1, cy + 5), (cx + 12, cy - 8)], fill=(255, 255, 255), width=3)
            d.polygon([(cx + 13, cy - 11), (cx + 13, cy - 3), (cx + 6, cy - 9)], fill=(255, 255, 255))
        elif name == "YOU":
            d.ellipse((cx - 13, cy - 13, cx + 13, cy + 13), fill=(30, 40, 34))
            d.ellipse((cx - 6, cy - 17, cx + 17, cy + 6), fill=(235, 240, 236))

    # ------------------------------------------------------------ khung
    def frame(self, t):
        im = self.hook(t) if t < HOOK else self.core(t)
        if t >= T1 + 0.12:
            im = self.report(im, t)
        return self.compose(im, t)

    def compose(self, im, t):
        im.paste(self.title, (int(W / 2 - self.title.size[0] / 2), int(TITLE_Y - self.title.size[1] / 2)), self.title)
        self.caption(im, t)
        return im

    def caption(self, im, t):
        cur = None
        for t0, sp in self.cap_sprites:
            if t >= t0:
                cur = (t0, sp)
        t0, sp = cur
        k = back((t - t0) / 0.22)
        a = min(1, (t - t0) / 0.1)
        w, h = sp.size
        s = 0.8 + 0.2 * k
        spr = sp.resize((max(1, int(w * s)), max(1, int(h * s))), Image.BICUBIC)
        paste_a(im, spr, (W / 2 - spr.size[0] / 2, CAP_Y - spr.size[1] / 2), a)

    def hook(self, t):
        if self._end_core is None:
            self._end_core = self.core(T1 + 0.5, quiet=True)
        im = Image.blend(self._end_core, Image.new("RGB", (W, H), (4, 10, 7)), 0.72)
        n = self.s.n
        k = back(t / 0.3)
        cy = 1000
        card = Image.new("RGBA", (960, 700), (0, 0, 0, 0))
        cd = ImageDraw.Draw(card)
        cd.rounded_rectangle((0, 0, 959, 699), 40, fill=(10, 30, 21, 240), outline=YELLOW + (255,), width=5)
        cd.text((480, 96), "ONE NIGHT · REAL CHARTS", font=F("ExtraBold", 38), fill=YELLOW, anchor="mm")
        cd.text((480, 220), f"{money(n['start'])} → {money(n['end'])}", font=F("ExtraBold", 70), fill=TXT, anchor="mm")
        col = GREEN if self.pct >= 0 else PINK
        cd.text((480, 380), f"{self.pct:+.1f}%", font=F("iBlack", 190), fill=col, anchor="mm")
        cd.text((480, 530), f"{n['trades']} trades · {n['scanned']} trending tokens", font=F("iSemiBold", 38), fill=TXT, anchor="mm")
        cd.text((480, 600), "paper trades on real 5m prices", font=F("Medium", 28), fill=DIM, anchor="mm")
        s = 0.6 + 0.4 * k
        c2 = card.resize((int(960 * s), int(700 * s)), Image.BICUBIC)
        im.paste(c2, (int(W / 2 - c2.size[0] / 2), int(cy - c2.size[1] / 2)), c2)
        mm = self.mb["win" if self.pct >= 0 else "loss"]
        im.paste(mm, (W // 2 - 65, int(cy - 350 * s - 80)), mm)
        if t > 0.72:
            g = (t - 0.72) / (HOOK - 0.72)
            import random
            rnd = random.Random(int(t * 1000))
            src = im.copy()
            for _ in range(16):
                y = rnd.randrange(self.FY0, self.FY1 - 40)
                h = rnd.randrange(8, 44)
                dx = int(rnd.uniform(-70, 70) * g)
                im.paste(src.crop((0, y, W, y + h)), (dx, y))
            ImageDraw.Draw(im).text((W // 2, 1450), "◀◀  REWIND TO 23:00", font=F("ExtraBold", 46), fill=TXT, anchor="mm")
        return im

    def report(self, im, t):
        n = self.s.n
        k = ease((t - T1 - 0.12) / 0.35)
        im = Image.blend(im, Image.new("RGB", (W, H), (4, 10, 7)), 0.72 * k)
        CW, CH = 1000, 1320
        card = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
        cd = ImageDraw.Draw(card)
        col = GREEN if self.pct >= 0 else PINK
        cd.rounded_rectangle((0, 0, CW - 1, CH - 1), 40, fill=(10, 30, 21, 248), outline=col + (255,), width=5)
        date_s = dt.datetime.fromisoformat(n["window"][0]).strftime("%d %b %Y")
        cd.text((CW // 2, 170), f"NIGHT REPORT · {date_s}", font=F("ExtraBold", 34), fill=DIM, anchor="mm")
        cd.text((CW // 2, 285), money(n["end"]), font=F("iBlack", 140), fill=col, anchor="mm")
        cd.text((CW // 2, 400), f"{self.pct:+.1f}% from {money(n['start'])} in one night", font=F("iSemiBold", 38), fill=TXT, anchor="mm")
        wr = n["wins"] / max(1, n["trades"]) * 100
        for i, (v, lab) in enumerate([(str(n["trades"]), "trades"), (f"{wr:.0f}%", "win rate"), (f"{n['filtered']}/{n['scanned']}", "filtered")]):
            x = 175 + i * 325
            cd.text((x, 500), v, font=F("ExtraBold", 60), fill=TXT, anchor="mm")
            cd.text((x, 556), lab, font=F("Medium", 26), fill=DIM, anchor="mm")
        cd.line((60, 610, CW - 60, 610), fill=LINE + (255,), width=2)
        ex = sorted([e for e in n["events"] if e["kind"] == "exit"], key=lambda e: -e["pnl"])
        cd.text((60, 640), "BEST TRADES", font=F("Bold", 28), fill=GREEN)
        for i, e in enumerate(ex[:3]):
            y = 700 + i * 92
            hh = dt.datetime.fromtimestamp(e["t"], ICT).strftime("%H:%M")
            cd.text((60, y), f"{hh}  ${e['sym']}", font=F("Bold", 36), fill=TXT)
            cd.text((60, y + 44), e["why"], font=F("Regular", 22), fill=DIM)
            cd.text((CW - 60, y + 4), money(e["pnl"], True), font=F("ExtraBold", 38), fill=GREEN if e["pnl"] > 0 else PINK, anchor="ra")
        w_ = ex[-1]
        cd.text((60, 990), "WORST", font=F("Bold", 28), fill=PINK)
        hh = dt.datetime.fromtimestamp(w_["t"], ICT).strftime("%H:%M")
        cd.text((60, 1040), f"{hh}  ${w_['sym']}", font=F("Bold", 36), fill=TXT)
        cd.text((60, 1084), w_["why"], font=F("Regular", 22), fill=DIM)
        cd.text((CW - 60, 1044), money(w_["pnl"], True), font=F("ExtraBold", 38), fill=PINK, anchor="ra")
        cd.text((CW // 2, 1240), "paper trades on real 5m candles · not financial advice", font=F("Medium", 22), fill=DIM, anchor="mm")
        y = 330 + int(90 * (1 - k))
        paste_a(im, card, (W / 2 - CW / 2, y), k)
        mm = self.mb["win" if self.pct >= 0 else "loss"]
        b = 1 + 0.08 * math.sin((t - T1) * 9) * max(0, 1 - (t - T1) / 2)
        m2 = mm.resize((int(130 * b), int(130 * b)), Image.LANCZOS)
        if k > 0.3:
            g, pad = self.g_gold
            paste_a(im, g, (W / 2 - pad, y + 80 - pad), k)
            im.paste(m2, (int(W / 2 - m2.size[0] / 2), int(y + 80 - m2.size[1] / 2)), m2)
        return im

    def core(self, t, quiet=False):
        s = self.s
        st = s.state(t)
        im = self.base.copy()
        d = ImageDraw.Draw(im)
        n = s.n
        end = t >= T1
        clk = s.clock(t)
        since = t - st["last_t"]
        lx = st["last_exit"]
        win_pop = lx and lx[1]["pnl"] > 0 and t - lx[0] < 0.9 and not quiet
        loss_hit = lx and lx[1]["pnl"] <= 0 and t - lx[0] < 0.5 and not quiet
        mood = "win" if (win_pop or end) and self.pct >= 0 else ("loss" if loss_hit else "ok")

        # header
        hm = self.m[mood]
        im.paste(hm, (38, 322), hm)
        blink = (int(t * 2) % 2 == 0) or end
        d.ellipse((186, 372, 200, 386), fill=ORANGE if blink else alpha(ORANGE, .4))
        d.text((210, 362), f"{'done' if end else ('running' if t >= T0 else 'scanning')} · {clk:%H:%M:%S}", font=F("Medium", 26), fill=TXT)
        status = self.status(st, end)
        fs = F("Medium", 18)
        w = fs.getlength(status) + 26
        rr(d, (184, 406, 184 + w, 440), 6, outline=GREEN, width=2)
        d.text((197, 423), status, font=fs, fill=GREEN, anchor="lm")
        kb = (t - st["bal_t"]) / 0.45
        bcol = TXT if kb >= 1.3 else (GREEN if st["bal"] >= st["prev_bal"] else PINK)
        odometer(im, 1046, 310, money(st["prev_bal"]), money(st["bal"]), kb, F("ExtraBold", 56), bcol)
        kc = (t - st["cnt_t"]) / 0.35
        pt, pw, pl = st["prev"]
        f40 = F("ExtraBold", 42)
        for x, a_, b_, c in ((770, pt, st["trades"], TXT), (890, pw, st["wins"], GREEN), (1000, pl, st["losses"], PINK)):
            wv = f40.getlength(str(b_))
            odometer(im, x + wv / 2, 392, str(a_), str(b_), kc, f40, c)
        d = ImageDraw.Draw(im)

        # dải agent
        act = self.active(st, t, end)
        for i, (name, col, _) in enumerate(self.AG):
            x0 = self.tile_x(i)
            if name in act:
                g, pad = self.g_agent[name]
                im.paste(g, (x0 - pad, self.TILE_Y0 - pad), g)
                d = ImageDraw.Draw(im)
                self.agent_tile(d, i, True)
            b = self.badge(name, st, end)
            fb = F("Medium", 14)
            bw = fb.getlength(b) + 14
            cx = x0 + self.TILE_W / 2
            rr(d, (cx - bw / 2, self.TILE_Y0 + 96, cx + bw / 2, self.TILE_Y0 + 120), 5, outline=col, width=2)
            d.text((cx, self.TILE_Y0 + 108), b, font=fb, fill=col, anchor="mm")
        who = sorted(act)[0] if act else ("SCANNER" if t < T0 else "LOGGER")
        col = dict((a, c) for a, c, _ in self.AG)[who]
        line = f"▸ {who} · {self.agent_line(who, st, end)}"
        d.text((self.PX0 + 4, 614), line[:62], font=F("Medium", 23), fill=col)

        # chip token
        chips = st["chips"][-4:]
        for j, (vt, sym, ok, why, p) in enumerate(chips[::-1]):
            age = t - vt
            x0 = self.PX1 - 16 - (j + 1) * 250 + 10
            dy = int(24 * (1 - ease(age / 0.22))) if j == 0 else 0
            bcol = (GREEN if p["pct"] >= 0 else PINK) if ok == "pulse" else (ORANGE if ok is not False else PINK)
            box = (x0, 704 + dy, x0 + 240, 784 + dy)
            rr(d, box, 12, fill=(13, 31, 23))
            dashed_rr(d, box, 12, alpha(bcol, .85), 2, 7, 4)
            cc = s.sym_color.get(sym, ORANGE)
            d.ellipse((x0 + 12, 716 + dy, x0 + 40, 744 + dy), fill=cc)
            d.text((x0 + 26, 730 + dy), sym[:1].upper(), font=F("Bold", 17), fill=BG, anchor="mm")
            d.text((x0 + 50, 713 + dy), "$" + sym[:10], font=F("Bold", 24), fill=TXT)
            d.text((x0 + 12, 754 + dy), why[:21], font=F("Regular", 18), fill=bcol if ok == "pulse" else DIM)
            if ok is False and age < 0.45:
                a = min(1, age / 0.08)
                stamp = Image.new("RGBA", (170, 42), (0, 0, 0, 0))
                sd = ImageDraw.Draw(stamp)
                sd.rounded_rectangle((2, 2, 168, 40), 8, outline=PINK + (int(255 * a),), width=3, fill=(60, 10, 25, int(200 * a)))
                sd.text((85, 21), "FILTERED", font=F("ExtraBold", 24), fill=PINK + (int(255 * a),), anchor="mm")
                stamp = stamp.rotate(-8, expand=True, resample=Image.BICUBIC)
                im.paste(stamp, (x0 + 50, 738 + dy), stamp)
                d = ImageDraw.Draw(im)
        d.text((self.PX1 - 16, 672), f"checked {st['checked']}", font=F("Regular", 18), fill=DIM, anchor="ra")

        # nút
        hot = self.hot_nodes(st, since, end)
        for x, y, r, col, lab in self.nodes:
            if lab in hot:
                g, pad = self.g_node[lab]
                im.paste(g, (x - pad, y - pad), g)
        if end:
            g, pad = self.g_gold
            im.paste(g, (540 - pad, 874 - pad), g)
        d = ImageDraw.Draw(im)
        for x, y, r, col, lab in self.nodes:
            d.ellipse((x - r, y - r, x + r, y + r), outline=col if lab != "MR PUMP" or not end else YELLOW, width=4)
        bump = 1 + 0.14 * math.sin(min(1, (t - lx[0]) / 0.5) * math.pi) if win_pop else 1.0
        ms = self.ms[mood]
        if bump != 1.0:
            ms = ms.resize((int(120 * bump), int(120 * bump)), Image.LANCZOS)
        im.paste(ms, (int(540 - ms.size[0] / 2), int(874 - ms.size[1] / 2 - 2)), ms)
        d = ImageDraw.Draw(im)
        for k2 in range(3):
            ph = (t * 1.6 + k2 / 3) % 1
            for (ax, ay, ar, _, _), (bx, by, br, _, _) in zip(self.nodes, self.nodes[1:]):
                xx = ax + ar + (bx - br - ax - ar) * ph
                d.ellipse((xx - 5, ay - 5, xx + 5, ay + 5), fill=GREEN if not end else YELLOW)
        if win_pop:
            a = 1 - (t - lx[0]) / 0.9
            for i in range(8):
                ang = i * math.pi / 4 + t * 2
                r1, r2 = 84 + 10 * (1 - a), 96 + 16 * (1 - a)
                d.line((540 + r1 * math.cos(ang), 874 + r1 * math.sin(ang), 540 + r2 * math.cos(ang), 874 + r2 * math.sin(ang)), fill=alpha(YELLOW, a), width=5)
        last_sym = st["last"]["symbol"] if st["lastk"] == "check" else (st["last"] or {}).get("sym", "")
        ok_last = st["lastk"] != "check" or st["last"]["ok"]
        d.text((250, 940), "RUG CHECK", font=F("Medium", 19), fill=PINK, anchor="mm")
        d.text((250, 964), ("PASS $" if ok_last else "BLOCK $") + str(last_sym)[:9], font=F("Regular", 18), fill=PINK, anchor="mm")
        d.text((540, 964), "MR PUMP · " + ("done" if end else f"{(st['checked'] * 7 + int(t * 13)) % 90 + 20} msg/s"), font=F("Medium", 18), fill=YELLOW, anchor="mm")
        d.text((830, 940), "EXECUTOR", font=F("Medium", 19), fill=GREEN, anchor="mm")
        d.text((830, 964), "FLAT" if not st["open"] else "LIVE $" + list(st["open"])[-1][:8], font=F("Regular", 18), fill=GREEN, anchor="mm")

        # 4 thẻ
        sz, eqp = st["sizer"], st["equity"]
        vals = [(str(st["filtered"]), f"{st['passed']} passed"),
                ((f"{sz['size']*100:.0f}% eq" if sz else "--"), (money(sz["size"] * st["bal"]) if sz else "waiting")),
                (f"line #{st['line']}", "with a reason"),
                ((money(eqp["pnl"], True) if eqp else "+$0.00"), "last close")]
        for i, (v, sub) in enumerate(vals):
            x0 = 36 + i * 254
            col = self.cards[i][0]
            if i == 3 and eqp:
                col = GREEN if eqp["pnl"] > 0 else PINK
            d.text((x0 + 14, 1018), v, font=F("Bold", 32), fill=TXT if i < 3 else col)
            d.text((x0 + 14, 1056), sub[:20], font=F("Regular", 17), fill=DIM)

        self.trade_card(im, st, t)
        d = ImageDraw.Draw(im)

        # tail -f
        alltail = [x for x in s.tail if x[0] <= t]
        d.text((self.PX1 - 16, 1120), f"{len(alltail) + 2} lines", font=F("Regular", 16), fill=DIM, anchor="ra")
        tl = alltail[-3:]
        for j, (vt, a_, b_, c) in enumerate(tl):
            yy = 1154 + j * 74
            d.text((562, yy), a_[:38], font=F("Medium", 20), fill=c)
            d.text((574, yy + 28), b_[:42], font=F("Regular", 17), fill=DIM)
        if int(t * 3) % 2 == 0:
            d.rectangle((562, 1154 + len(tl) * 74, 573, 1176 + len(tl) * 74), fill=GREEN)

        bal = st["prev_bal"] + (st["bal"] - st["prev_bal"]) * ease(kb)
        self.equity_curve(d, t, bal, end)

        # LOG 4 dòng
        rows = [r for r in s.rows if r[0] <= t][-4:]
        for j, (vt, hh, kind, sym, title, why, right, rc) in enumerate(rows):
            yy = 1598 + j * 70
            age = t - vt
            if (j == len(rows) - 1) and age < 1.5:
                fl = 1 - min(1, age / 0.4)
                d.rectangle((self.PX0 + 4, yy - 6, self.PX1 - 4, yy + 62), fill=tuple(int(18 + 30 * fl * (c / 255)) for c in (ORANGE if kind == "ENTER" else rc)))
                d.rectangle((self.PX0 + 4, yy - 6, self.PX0 + 9, yy + 62), fill=ORANGE)
            d.text((40, yy + 6), hh, font=F("Medium", 22), fill=DIM)
            bc = {"ENTER": ORANGE, "EXIT": GREEN if rc != PINK else PINK, "SCAN": BLUE, "CHECK": PINK}[kind]
            rr(d, (124, yy + 4, 230, yy + 34), 5, outline=bc, width=2, fill=alpha(bc, .12))
            d.text((177, yy + 19), kind, font=F("Medium", 17), fill=bc, anchor="mm")
            if sym:
                d.ellipse((248, yy + 2, 274, yy + 28), fill=s.sym_color.get(sym, ORANGE))
                d.text((261, yy + 15), sym[:1].upper(), font=F("Bold", 14), fill=BG, anchor="mm")
                d.text((284, yy - 1), "$" + title[:12], font=F("Bold", 25), fill=TXT)
            else:
                d.text((248, yy - 1), title, font=F("Bold", 25), fill=TXT)
            d.text((248, yy + 33), why[:56], font=F("Regular", 19), fill=alpha(ORANGE, .9))
            d.text((self.PX1 - 18, yy), right, font=F("Bold", 26), fill=rc if kind == "EXIT" else ORANGE, anchor="ra")

        if not quiet:
            self.fliers(im, st, t)
        if loss_hit:
            a = 1 - (t - lx[0]) / 0.5
            g, pad = self.g_loss
            paste_a(im, g, (self.FX0 - pad, self.FY0 - pad), a * 0.8)
            amp = int(6 * a)
            if amp:
                sh = int(amp * math.sin((t - lx[0]) * 90))
                term = im.crop((0, self.FY0 - 4, W, self.FY1 + 4))
                im.paste(BG, (0, self.FY0 - 4, W, self.FY1 + 4))
                im.paste(term, (sh, self.FY0 - 4))
        return im

    def fliers(self, im, st, t):
        d = ImageDraw.Draw(im)
        le = st["last_enter"]
        if le and 0 <= t - le[0] < 0.6:
            k = (t - le[0]) / 0.6
            p0, p1, p2 = (self.PX1 - 16 - 250 + 10 + 120, 744), (540, 874), (830, 874)
            for gk in (0.0, 0.06, 0.12):
                kk = max(0, k - gk)
                if kk < 0.55:
                    u = ease(kk / 0.55)
                    c = (p0[0] * (1 - u) ** 2 + 2 * (1 - u) * u * 700 + u * u * p1[0], p0[1] * (1 - u) ** 2 + 2 * (1 - u) * u * 640 + u * u * p1[1])
                else:
                    u = ease((kk - 0.55) / 0.45)
                    c = (p1[0] + (p2[0] - p1[0]) * u, p1[1])
                a = 1 if gk == 0 else 0.35
                r = 20 if gk == 0 else 13
                col = self.s.sym_color.get(le[1]["sym"], ORANGE)
                d.ellipse((c[0] - r, c[1] - r, c[0] + r, c[1] + r), fill=alpha(col, a), outline=alpha(TXT, a), width=2)
                if gk == 0:
                    d.text((c[0] + 26, c[1] - 16), "$" + le[1]["sym"][:9], font=F("Bold", 26), fill=TXT)
        lx = st["last_exit"]
        if lx and 0 <= t - lx[0] < 1.0:
            k = (t - lx[0]) / 1.0
            p = lx[1]
            col = GREEN if p["pnl"] > 0 else PINK
            big = p["pnl"] > 10
            sp = text_sprite(money(p["pnl"], True), F("ExtraBold", 60 if big else 46), col, 5, (4, 12, 8))
            s = back(min(1, k / 0.25))
            sp2 = sp.resize((max(1, int(sp.size[0] * s)), max(1, int(sp.size[1] * s))), Image.BICUBIC)
            x = min(36 + 3 * 254 + 122 - sp2.size[0] / 2, W - 24 - sp2.size[0])
            y = 990 - 110 * ease(k) - sp2.size[1] / 2
            paste_a(im, sp2, (x, y), 1 if k < 0.7 else (1 - k) / 0.3)

    def trade_card(self, im, st, t):
        d = ImageDraw.Draw(im)
        tr = st["trade"]
        if not tr:
            d.text((40, 1220), "waiting for a signal…", font=F("Regular", 22), fill=DIM)
            return
        kind, p, vt = tr
        sym = p["sym"]
        ent = p if kind == "enter" else self.s.entry_for(p)
        cc = self.s.sym_color.get(sym, ORANGE)
        d.ellipse((40, 1150, 74, 1184), fill=cc)
        d.text((57, 1167), sym[:1].upper(), font=F("Bold", 19), fill=BG, anchor="mm")
        d.text((84, 1144), "$" + sym[:10], font=F("ExtraBold", 32), fill=TXT)
        rows = self.s.rows_of.get(sym)
        now_ts = self.s.ts_at(t)
        pct = None
        if rows and ent:
            e_ts = ent["t"]
            x_ts = p["t"] if kind == "exit" else None
            vis = [r for r in rows if e_ts - 8 * 300 <= r[0] < (x_ts if x_ts else now_ts) and r[0] <= now_ts][-22:]
            if vis:
                last_c = vis[-1][4]
                pct = p["pct"] if kind == "exit" else last_c * (1 - 0.015) / ent["price"] - 1
                X0, X1, Y0, Y1 = 40, 518, 1200, 1300
                lo = min(min(r[3] for r in vis), ent["price"])
                hi = max(max(r[2] for r in vis), ent["price"])
                rng_ = (hi - lo) or hi * 0.01
                Y = lambda v: Y1 - (v - lo) / rng_ * (Y1 - Y0)
                cw = (X1 - X0) / 22
                for i, r in enumerate(vis):
                    cx = X0 + cw * (i + 0.5)
                    col = GREEN if r[4] >= r[1] else PINK
                    d.line((cx, Y(r[2]), cx, Y(r[3])), fill=col, width=2)
                    y_a, y_b = sorted((Y(r[1]), Y(r[4])))
                    d.rectangle((cx - cw * 0.32, y_a, cx + cw * 0.32, max(y_b, y_a + 2)), fill=col)
                ye = Y(ent["price"])
                for x in range(X0, X1, 12):
                    d.line((x, ye, x + 6, ye), fill=ORANGE, width=2)
                d.text((X1, ye - 22), "entry", font=F("Medium", 16), fill=ORANGE, anchor="ra")
                if kind == "exit":
                    xp = ent["price"] * (1 + p["pct"])
                    xc = X0 + cw * (len(vis) - 0.5)
                    d.ellipse((xc - 8, Y(xp) - 8, xc + 8, Y(xp) + 8), outline=TXT, width=3)
        if pct is None and kind == "exit":
            pct = p["pct"]
        if pct is not None:
            d.text((518, 1146), f"{pct*100:+.1f}%" + (" live" if kind == "enter" else ""), font=F("Bold", 28), fill=GREEN if pct >= 0 else PINK, anchor="ra")
        size = (ent or p).get("size", 0) * 100
        d.text((40, 1314), f"size {size:.0f}% · slip 1.5% · {'open' if kind == 'enter' else 'closed'}", font=F("Medium", 19), fill=TXT)
        d.text((40, 1346), p["why"].replace(" over 30m high", "")[:40], font=F("Regular", 18), fill=ORANGE)

    def equity_curve(self, d, t, bal, end):
        n = self.s.n
        pts = [(vt, b) for vt, b in self.s.curve if vt <= t]
        allb = [b for _, b in self.s.curve]
        lo, hi = min(allb), max(allb)
        rng_ = (hi - lo) or 1
        X0, X1, Y0, Y1 = 40, 730, 1444, 1500
        X = lambda v: X0 + (min(v, T1) - T0) / (T1 - T0) * (X1 - X0)
        Y = lambda b: Y1 - (b - lo) / rng_ * (Y1 - Y0)
        ys = Y(n["start"])
        for x in range(X0, X1, 14):
            d.line((x, ys, x + 7, ys), fill=LINE, width=1)
        if t >= T0:
            line, prev = [], pts[0][1]
            for vt, b in pts:
                line += [(X(vt), Y(prev)), (X(vt), Y(b))]
                prev = b
            line.append((X(max(T0, t)), Y(prev)))
            col = GREEN if bal >= n["start"] else PINK
            d.polygon(line + [(line[-1][0], Y1), (line[0][0], Y1)], fill=alpha(col, .18))
            d.line(line, fill=col, width=4)
            d.ellipse((line[-1][0] - 6, line[-1][1] - 6, line[-1][0] + 6, line[-1][1] + 6), fill=col)
        d.text((self.PX1 - 16, 1414), "start " + money(n["start"]), font=F("Medium", 18), fill=DIM, anchor="ra")
        d.text((self.PX1 - 16, 1440), money(bal), font=F("ExtraBold", 40), fill=GREEN if bal >= n["start"] else PINK, anchor="ra")
        w_, l_ = self._wl(t)
        f = F("Bold", 22)
        d.text((40, 1506), f"{w_} W / ", font=f, fill=GREEN)
        d.text((40 + f.getlength(f"{w_} W / "), 1506), f"{l_} L", font=f, fill=PINK)
        d.text((self.PX1 - 16, 1508), "paper · real 5m candles", font=F("Regular", 17), fill=DIM, anchor="ra")

    def _wl(self, t):
        w = l = 0
        for vt, k, p in self.s.items:
            if vt > t:
                break
            if k == "exit":
                if p["pnl"] > 0:
                    w += 1
                else:
                    l += 1
        return w, l

    def status(self, st, end):
        if end:
            return f"NIGHT CLOSED · {st['trades']} TRADES LOGGED"
        k, p = st["lastk"], st["last"]
        if k == "check":
            return f"SCANNER · {'PASSED' if p['ok'] else 'BLOCKED'} ${p['symbol'][:10]}"
        if k == "enter":
            return f"EXECUTOR · ENTERED ${p['sym'][:10]}"
        if k == "exit":
            return f"TRADE CLOSED · LOGGED ${p['sym'][:10]}"
        if k == "skip":
            return f"SIZER · SKIPPED ${p['sym'][:10]}"
        return "BOOTING · LOADING TRENDING"

    def active(self, st, t, end):
        if end:
            return {"YOU"}
        k, since = st["lastk"], t - st["last_t"]
        if k == "check":
            return {"SCANNER"} if st["last"]["stage"] == "SCANNER" else {"RUG CHECK"}
        if since < 0.9:
            if k == "enter":
                return {"SIZER"} if since < 0.3 else {"EXECUTOR"}
            if k == "exit":
                return {"EXECUTOR"} if since < 0.2 else ({"LOGGER"} if since < 0.5 else {"EQUITY"})
            if k == "skip":
                return {"SIZER"}
        if t - st["pulse_t"] < 0.18:
            return {"SCANNER"}
        return set()

    def hot_nodes(self, st, since, end):
        if end:
            return {"MR PUMP"}
        if since > 0.6:
            return set()
        return {"check": {"RUG CHECK"}, "enter": {"MR PUMP", "EXECUTOR"}, "exit": {"EXECUTOR"}, "skip": {"MR PUMP"}}.get(st["lastk"], set())

    def badge(self, name, st, end):
        if name == "YOU":
            return "READING" if end else "ASLEEP"
        if name == "EXECUTOR":
            return "LIVE" if st["open"] else "FLAT"
        return {"SCANNER": "SCAN", "RUG CHECK": "PASS", "SIZER": "SIZE", "LOGGER": "WRITE", "EQUITY": "UPDATE"}[name]

    def agent_line(self, name, st, end):
        chips = st["chips"]
        if name == "SCANNER":
            if chips:
                vt, sym, ok, why, p = chips[-1]
                if ok == "pulse":
                    return f"${sym} {p['pct']*100:+.1f}% in 5m · vol {p['volx']:.1f}×"
                if "liq" in p:
                    return f"${sym} · liq {short(p['liq'])} · {'pass' if ok else p['reason']}"
                return f"signal ${sym}"
            return "loading trending…"
        if name == "RUG CHECK":
            return f"{st['passed']} passed · {st['filtered']} blocked"
        if name == "SIZER":
            sz = st["sizer"]
            return f"{sz['size']*100:.0f}% of {money(st['bal'])} · never a fixed ticket" if sz else "idle"
        if name == "EXECUTOR":
            return ("LONG $" + list(st["open"])[-1] + " · slip + fee 1.5%") if st["open"] else "flat · waiting"
        if name == "LOGGER":
            return f"line #{st['line']} · no trade without a reason"
        if name == "EQUITY":
            return f"{money(st['bal'])} · {st['trades']} closes"
        if name == "YOU":
            return f"{st['line']} lines to read at 7am"


def load(date):
    return json.load(open(os.path.join(ddir(date), "night.json")))


def load_candles(date):
    p = os.path.join(ddir(date), "candles.json")
    return json.load(open(p)) if os.path.exists(p) else None


def make_story(date):
    return Story(load(date), load_candles(date))


_P = None


def _init(date):
    global _P
    _P = Painter(make_story(date))


def _seg(args):
    date, f0, f1, path = args
    p = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", path],
                         stdin=subprocess.PIPE)
    for f in range(f0, f1):
        p.stdin.write(_P.frame(f / FPS).convert("RGB").tobytes())
    p.stdin.close()
    p.wait()
    return path


def video(date, jobs=4):
    out = os.path.join(HERE, "output")
    os.makedirs(out, exist_ok=True)
    N = int(TEND * FPS)
    cuts = [N * i // jobs for i in range(jobs + 1)]
    segs = [(date, cuts[i], cuts[i + 1], f"{out}/_seg{i}.mp4") for i in range(jobs)]
    with Pool(jobs, initializer=_init, initargs=(date,)) as pool:
        paths = pool.map(_seg, segs)
    lst = f"{out}/_segs.txt"
    open(lst, "w").write("".join(f"file '{p}'\n" for p in paths))
    dst = f"{out}/mrpump_{date}_silent.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", dst], check=True)
    for p_ in paths + [lst]:
        os.remove(p_)
    print(dst)
    return dst


if __name__ == "__main__":
    a = sys.argv[1:]
    date = dt.date.fromisoformat(a[a.index("--date") + 1]) if "--date" in a else default_date()
    if "still" in a:
        P = Painter(make_story(date))
        ts = [float(x) for x in a[a.index("still") + 1:] if x.replace(".", "").isdigit()]
        out = os.path.join(HERE, "output")
        os.makedirs(out, exist_ok=True)
        for t in ts:
            P.frame(t).convert("RGB").save(f"{out}/still_{t:05.2f}.png")
        print("ok", ts)
    elif "video" in a:
        video(date, int(a[a.index("--jobs") + 1]) if "--jobs" in a else 4)
