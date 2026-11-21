# MR PUMP Terminal

Video 9:16 (~29 s) "sáu agent, log trước", **2 phiên mỗi ngày**: đêm 23:00→07:00 và ngày 11:00→19:00 (giờ VN), cho meme coin Solana, dựng từ **dữ liệu on-chain thật**.

| Bước | File | Việc làm |
|---|---|---|
| 1 | `fetch.py scan` | Chụp ~60 pool **trending** Solana (GeckoTerminal: Pump.fun/PumpSwap, Raydium, Meteora) + rug-check từng token (mint/freeze authority, top 10 ví, % dev, số holder, GT score). Nên chạy lúc ~23:00 giờ VN. |
| 2 | `fetch.py candles` | Nến 5 phút thật của đêm 23:00 → 07:00 (UTC+7). Chạy sau 07:00. |
| 3 | `sim.py` | SCANNER + RUG CHECK lọc token, rồi paper trade trên nến thật: breakout đỉnh 30 phút + volume ≥ 2×, size 24–40% vốn, stop −8%, chốt +30%, trailing 10%, time stop 30 phút, phí + trượt 1,5%/chiều. Kết quả lời hay lỗ đều giữ nguyên. |
| 4 | `render.py` | Vẽ terminal (PIL) → mp4 30 fps, 4 tiến trình song song. `python3 render.py still 2 12 27` để xem trước. |
| 5 | `audio.py` | Nhạc EDM 128 BPM tự tổng hợp (F thứ, kick 4/4, sidechain, supersaw, arp) + SFX theo sự kiện: stamp khi bị lọc, ping khi PASS, zip khi ENTER, cha-ching khi EXIT lời, thud khi lỗ, impact + coin khi chốt kết quả. |
| 6 | `run.py` | Chạy hết, loudnorm −14 LUFS → `output/MR_PUMP_<date>.mp4`. |

```bash
python3 fetch.py scan [--session day]   # chạy ~10 phút trước giờ bắt đầu phiên
python3 run.py [--session day]          # sau khi phiên kết thúc: nến + giả lập + video + caption .txt
python3 run.py --date 2026-11-20 --skip-fetch --start 200
```

Chỉ cần Python 3 + numpy, scipy, Pillow, ffmpeg. API công khai, không cần key (giới hạn ~30 lệnh gọi/phút).

## Trung thực
- Giá, token, chỉ số lọc là thật. **Lệnh là paper trade (giả lập)** trên giá thật, đã tính phí/trượt giá. Video luôn ghi "paper trades · real 5m candles" và "Not financial advice".
- Chạy `scan` sau khi đêm đã qua (như bản demo 20/11) là có **thiên lệch chọn mẫu**: danh sách trending chụp lúc sáng. Chạy `scan` đúng 23:00 hằng ngày thì không còn thiên lệch này.
- `data/<date>/` lưu dữ liệu từng ngày để kiểm lại được.
