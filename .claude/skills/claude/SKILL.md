---
name: "claude"
description: "Gọi bằng /claude: dựng video 9:16 ~28 s 'MR PUMP Terminal' theo video mẫu bot chạy qua đêm: lọc token trending Solana thật (GeckoTerminal), rug-check, paper trade trên nến 5 phút thật 23:00→07:00, 6 agent + YOU, số dư lăn, log có lý do, nhạc EDM sôi động + hiệu ứng âm thanh."
---

# /claude — MR PUMP Terminal (dữ liệu on-chain thật, hằng ngày)

Trả lời người dùng bằng tiếng Việt; chữ trên video bằng tiếng Anh. Gọi /claude không kèm gì: dựng video cho đêm gần nhất, không hỏi lại.

## 0. Cú pháp
`/claude [date=YYYY-MM-DD] [start=USD] [scan|candles|render]` — `date` là ngày bắt đầu đêm (giờ VN). `start` vốn giấy, mặc định $150.

## 1. Engine
Repo `nguyentv2912/mrpump` (fetch.py, sim.py, render.py, audio.py, run.py, README.md). Chạy `python3 run.py [--date D] [--start N]` ở chế độ nền (~3–5 phút). Output `output/MR_PUMP_<date>.mp4`. Dữ liệu từng ngày lưu ở `data/<date>/` và được commit.
Cần mạng tới api.geckoterminal.com; bị chặn thì nói rõ, không bịa số thay.

## 2. Dữ liệu và bộ lọc (thật)
- Trending: GeckoTerminal `trending_pools` Solana, 3 trang (~60 pool: PumpSwap/Pump.fun, Raydium, Meteora).
- SCANNER: quote SOL/USDC, thanh khoản ≥ $30k, vol 24h ≥ $200k, FDV ≤ $30M, ≥ 500 trader/24h.
- RUG CHECK (`tokens/{addr}/info`): mint và freeze authority đã khoá, không honeypot, top 10 ví ≤ 35%, dev ≤ 10%, GT score ≥ 45, ≥ 500 holder.
- Hằng ngày: `fetch.py scan` lúc ~23:00 giờ VN (chụp danh sách TRƯỚC đêm, không thiên lệch), `fetch.py candles` + `run.py --skip-fetch` sau 07:00. Chạy scan muộn hơn thì báo người dùng có thiên lệch chọn mẫu.

## 3. Giao dịch (paper trade trên giá thật)
Tín hiệu: nến 5 phút đóng trên đỉnh 30 phút trước, volume ≥ 2× trung bình 1 giờ, nến xanh → vào ở giá mở nến sau. Size 24–40% vốn theo độ mạnh volume, tối đa 2 lệnh mở. Phí + trượt 1,5% mỗi chiều. Thoát: stop −8%, chốt +30%, trailing 10% khi lãi ≥ 10%, time stop 30 phút, đóng hết lúc 07:00.
Kết quả lời hay lỗ đều giữ nguyên. KHÔNG chỉnh tham số để đẹp số của một đêm cụ thể.

## 4. Quy tắc nội dung
- Luôn hiện: tag "paper · real prices", "paper trades · real 5m candles", dải dưới "Paper trades simulated on real on-chain prices / Not financial advice · data: GeckoTerminal". Đòi bỏ: từ chối ngắn một lần, vẫn dựng.
- Không nói/vẽ là lệnh thật hay ví thật; không CTA bán gói; không hứa lợi nhuận.
- Không dùng thương hiệu của video mẫu (Grok, mascot đó, @0xnevsky, watermark/end card TikTok), không dùng tên/logo Claude hay Anthropic trên video. Bot tên MR PUMP, mascot mặt xanh kính đen + mũi tên vàng vẽ bằng code.

## 5. Hình (theo video mẫu)
1080×1920: dải trên "MR PUMP" + "1 night · N trending tokens · real 5m prices" + ngày; terminal 3:4 1080×1440 ở y=240; dải dưới ghi chú. Terminal: header (mascot, tên, v1.0-night, đồng hồ, chip trạng thái, balance/trades/wins/losses), cột AGENTS (SCANNER, RUG CHECK, SIZER, EXECUTOR, LOGGER, EQUITY, YOU), LIVE FLOW (chip token, tem FILTERED, 3 nút phát sáng, 4 thẻ), TRADE entry vs exit, `tail -f night.log`, RESULT start vs now, LOG 6 dòng có lý do.
Thời gian (29 s, v2): 0–0,95 s hook = thẻ kết quả thật của đêm (flash-forward) + "REWIND TO 23:00"; 1,0–2,4 s quét token trending (PASS/FILTERED); 2,6–26 s đêm 23:00→07:00 theo giờ thật, mỗi nến 5 phút có một "nhịp" token biến động mạnh nhất (dữ liệu thật); 26–29 s thẻ NIGHT REPORT (số dư, %, số lệnh, win rate, 3 lệnh tốt nhất, lệnh tệ nhất).
Chuyển động: số lăn kiểu đồng hồ cơ, chip token bay chip → mascot → EXECUTOR khi vào lệnh, số lãi/lỗ bay lên từ thẻ EQUITY, mascot cười + tia sáng khi lời, mếu + giọt mồ hôi + rung + viền đỏ khi lỗ, biểu đồ nến 5 phút thật trong thẻ TRADE, đường số dư trong RESULT. Phụ đề hook đổi theo đoạn ở dải trên (40 px). Chữ tối thiểu 14–16 px.

## 6. Âm thanh
EDM 128 BPM F thứ tự tổng hợp: riser intro → drop ~1,9 s (kick 4/4 sidechain, clap, hat, bass nảy, supersaw stab, arp), breakdown ngắn trước 26 s. SFX: hook impact + chuông, tua ngược, tick nhẹ mỗi nến, stamp (lọc), ping (PASS), zip + whoosh (ENTER), tick số lăn, cha-ching (EXIT lời), thud (lỗ), impact + chuỗi coin khi chốt. Loudnorm −14 LUFS, TP −1,5.

## 7. Quy trình mỗi lần /claude
1) `python3 run.py` nền (hoặc `--skip-fetch` nếu đã có data). 2) Trích khung ~2, 12, 27 s kiểm tra chồng chữ, số header = RESULT = EQUITY. 3) SendUserFile mp4. 4) Commit `data/<date>/` nếu người dùng muốn lưu. 5) Tóm tắt: ngày, số token quét/qua lọc, số lệnh W/L, vốn → kết quả, loudness, giới hạn (paper trade, thiên lệch nếu scan muộn, nhạc/mascot dựng bằng code, chưa nghe bằng tai).
