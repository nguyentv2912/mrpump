"""MR PUMP — nhạc nền EDM sôi động tự tổng hợp (128 BPM, F thứ) + hiệu ứng âm thanh khớp sự kiện.

  python3 audio.py [--date D]  -> output/mrpump_<date>.wav
"""
import os, sys, json, wave, datetime as dt
import numpy as np
from scipy.signal import butter, sosfilt
from fetch import default_date
from render import make_story, TEND, T1, T0, HOOK, HERE

SR = 44100
BPM = 128
BEAT = 60 / BPM
rng = np.random.default_rng(7)


def t_(d):
    return np.arange(int(d * SR)) / SR


def lp(x, f, o=2):
    return sosfilt(butter(o, f, "low", fs=SR, output="sos"), x)


def hp(x, f, o=2):
    return sosfilt(butter(o, f, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi, o=2):
    return sosfilt(butter(o, [lo, hi], "band", fs=SR, output="sos"), x)


def saw(f, t):
    return 2 * ((f * t) % 1) - 1


def add(buf, x, at, g=1.0):
    i = int(at * SR)
    if i >= len(buf) or i + len(x) <= 0:
        return
    x = x[: len(buf) - i]
    buf[i:i + len(x)] += g * x


def note(n):                       # số MIDI -> Hz
    return 440 * 2 ** ((n - 69) / 12)


# ------------------------------------------------------------- nhạc cụ
def kick():
    t = t_(0.45)
    f = 45 + 120 * np.exp(-t * 32)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.tanh(2.2 * np.sin(ph) * np.exp(-t * 7)) + 0.3 * hp(rng.standard_normal(len(t)), 3000) * np.exp(-t * 300)


def clap():
    t = t_(0.3)
    n = bp(rng.standard_normal(len(t)), 900, 3500)
    env = np.exp(-t * 18) + 0.6 * np.exp(-np.maximum(0, t - 0.012) * 40) * (t > 0.012)
    return 0.8 * n * env


def hat(open_=False):
    t = t_(0.25 if open_ else 0.06)
    return 0.35 * hp(rng.standard_normal(len(t)), 7000) * np.exp(-t * (12 if open_ else 70))


def supersaw(freqs, dur, cut=3500):
    t = t_(dur)
    x = sum(saw(f * (1 + d), t) for f in freqs for d in (-0.012, -0.005, 0, 0.006, 0.011))
    x = lp(x / (len(freqs) * 5), cut)
    return x * np.minimum(1, t / 0.01) * np.exp(-t * 3.2)


def bass(f, dur):
    t = t_(dur)
    x = 0.6 * saw(f, t) + 0.4 * np.sin(2 * np.pi * f / 2 * t)
    return lp(x, 900) * np.minimum(1, t / 0.005) * np.exp(-t * 4)


def pluck(f, dur=0.18):
    t = t_(dur)
    x = saw(f, t) * 0.5 + np.sign(np.sin(2 * np.pi * f * t)) * 0.3
    e = np.exp(-t * 20)
    return (lp(x, 2200) * (1 - e) + lp(x, 6500) * e) * np.exp(-t * 14)


def riser(dur):
    t = t_(dur)
    n = rng.standard_normal(len(t))
    out = np.zeros_like(n)
    steps = 24
    L = len(t) // steps
    for i in range(steps):
        seg = n[i * L:(i + 1) * L]
        out[i * L:(i + 1) * L] = bp(seg, 400 + i * 300, 1200 + i * 450)
    sw = np.sin(2 * np.pi * np.cumsum(200 + 1600 * (t / dur) ** 2) / SR) * 0.25
    return (out * 0.6 + sw) * (t / dur) ** 2


def impact():
    t = t_(1.6)
    sub = np.sin(2 * np.pi * np.cumsum(30 + 80 * np.exp(-t * 6)) / SR) * np.exp(-t * 2.2)
    noise = lp(rng.standard_normal(len(t)), 1500) * np.exp(-t * 5)
    return np.tanh(1.8 * sub + 0.5 * noise)


# ------------------------------------------------------------- hiệu ứng (SFX)
def sfx_tick():
    t = t_(0.03)
    return 0.5 * np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 200)


def sfx_block():                  # tem FILTERED: "stamp" trầm + rè
    t = t_(0.18)
    return 0.8 * np.tanh(3 * np.sin(2 * np.pi * (110 - 40 * t) * t)) * np.exp(-t * 22) + 0.25 * bp(rng.standard_normal(len(t)), 200, 900) * np.exp(-t * 30)


def sfx_pass():
    t = t_(0.16)
    return 0.45 * (np.sin(2 * np.pi * 1318 * t) + 0.5 * np.sin(2 * np.pi * 1976 * t)) * np.exp(-t * 25)


def sfx_enter():                  # zip đi lên
    t = t_(0.28)
    f = 300 + 2200 * (t / 0.28) ** 1.5
    return 0.4 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * t / 0.28) + 0.2 * hp(rng.standard_normal(len(t)), 4000) * np.sin(np.pi * t / 0.28)


def sfx_win():                    # cha-ching: 2 nốt chuông + coin
    out = np.zeros(int(0.6 * SR))
    for k, (f, d) in enumerate(((1568, 0), (2093, 0.07))):
        t = t_(0.5)
        x = (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * f * 2.76 * t)) * np.exp(-t * 9)
        add(out, 0.45 * x, d)
    t = t_(0.08)
    add(out, 0.3 * hp(rng.standard_normal(len(t)), 6000) * np.exp(-t * 60), 0)
    return out


def sfx_loss():                   # thud đi xuống
    t = t_(0.35)
    f = 220 * np.exp(-t * 5)
    return 0.7 * np.tanh(2 * np.sin(2 * np.pi * np.cumsum(f) / SR)) * np.exp(-t * 9)


def sfx_whoosh():
    t = t_(0.35)
    n = rng.standard_normal(len(t))
    return 0.5 * bp(n, 500, 4000) * np.sin(np.pi * t / 0.35) ** 2


def sfx_rewind():                 # băng tua ngược: sweep đi xuống + rè
    t = t_(0.3)
    f = 2400 * np.exp(-t * 9) + 150
    return 0.35 * np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR)) * np.exp(-t * 3) + 0.2 * hp(rng.standard_normal(len(t)), 3000) * np.exp(-t * 6)


def sfx_cash():                   # kết: chuỗi coin
    out = np.zeros(int(1.4 * SR))
    for i in range(9):
        add(out, sfx_win() * (0.9 - i * 0.07), i * 0.09)
    return out


# ------------------------------------------------------------- bản nhạc
def music(dur):
    buf = np.zeros(int(dur * SR) + SR)
    bar = 4 * BEAT
    prog = [[53, 56, 60], [49, 53, 56], [56, 60, 63], [51, 55, 58]]          # Fm Db Ab Eb
    roots = [41, 37, 44, 39]
    arp = [0, 2, 1, 2, 0, 2, 1, 3]
    drop = bar                                                                # intro 1 ô, drop ở ~1.9 s
    K, C, Ho, Hc = kick(), clap(), hat(True), hat()
    side = np.ones(len(buf))
    add(buf, riser(drop) * 0.5, 0)
    nb = int(dur / BEAT) + 1
    for b in range(nb):
        tb = b * BEAT
        if tb < drop:
            add(buf, Hc, tb, 0.6)
            if b % 2 == 1:
                add(buf, K * 0.6, tb)
            continue
        brk = T1 - 2 * bar < tb < T1 - 0.05            # breakdown ngắn trước khi chốt kết quả
        if not brk:
            add(buf, K, tb)
            i = int(tb * SR)
            L = int(0.22 * SR)
            side[i:i + L] = np.minimum(side[i:i + L], 0.25 + 0.75 * (np.arange(min(L, len(side) - i)) / L))
        if b % 2 == 1 and not brk:
            add(buf, C, tb, 0.7)
        add(buf, Ho, tb + BEAT / 2, 0.45 if not brk else 0.2)
        add(buf, Hc, tb + BEAT / 4, 0.3)
        add(buf, Hc, tb + 3 * BEAT / 4, 0.3)
    mus = np.zeros(len(buf))
    for k in range(int(dur / bar) + 1):
        ts = k * bar
        ch = prog[k % 4]
        r = roots[k % 4]
        if ts >= drop:
            for s in range(8):                                         # bass nảy 8 nốt
                add(mus, bass(note(r), BEAT / 2), ts + s * BEAT / 2, 0.55)
            for s in (0, 1.5, 3):                                      # stab supersaw
                add(mus, supersaw([note(n) for n in ch], 0.5), ts + s * BEAT, 0.5)
        for s in range(16):                                            # arp 16th
            n = ch[arp[s % 8] % 3] + (12 if arp[s % 8] == 3 else 0) + 12
            add(mus, pluck(note(n)), ts + s * BEAT / 4, 0.22 if ts >= drop else 0.14)
    out = buf + mus * side
    return out, drop


def build(date):
    s = make_story(date)
    dur = TEND
    mix, drop = music(dur)
    sfx = np.zeros_like(mix)
    add(sfx, impact() * 0.9, 0.02)                    # hook: thẻ kết quả bật lên
    add(sfx, sfx_win(), 0.12, 0.9)
    add(sfx, sfx_rewind(), 0.70, 0.8)                  # tua ngược về 23:00
    add(sfx, impact() * 0.6, drop)
    for vt, k, p in s.items:
        if k == "check":
            add(sfx, sfx_pass() if p["ok"] else sfx_block() * 0.7, vt, 0.8)
        elif k == "pulse":
            add(sfx, sfx_tick(), vt, 0.25)
        elif k == "enter":
            add(sfx, sfx_enter(), vt, 0.8)
            add(sfx, sfx_whoosh(), vt, 0.5)
            add(sfx, sfx_tick(), vt + 0.12, 0.8)
        elif k == "exit":
            add(sfx, sfx_win() if p["pnl"] > 0 else sfx_loss(), vt, 0.9 if p["pnl"] > 0 else 0.8)
            for j in range(6):                         # số lăn
                add(sfx, sfx_tick(), vt + 0.04 + j * 0.06, 0.35)
    add(sfx, impact(), T1, 1.0)
    add(sfx, sfx_cash() if s.n["end"] >= s.n["start"] else sfx_loss(), T1 + 0.05, 0.8)
    x = mix * 0.55 + sfx * 0.75
    x = x[: int(dur * SR)]
    fade = int(0.6 * SR)
    x[-fade:] *= np.linspace(1, 0, fade)
    x = np.tanh(x / max(1e-9, np.max(np.abs(x))) * 1.4) * 0.9
    st = np.stack([x, np.roll(hp(x, 2000), 220) * 0.25 + x], 1)      # rộng nhẹ
    st /= np.max(np.abs(st)) * 1.05
    out = os.path.join(HERE, "output", f"mrpump_{date}.wav")
    with wave.open(out, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((st * 32767).astype(np.int16).tobytes())
    print(out)
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    build(dt.date.fromisoformat(a[a.index("--date") + 1]) if "--date" in a else default_date())
