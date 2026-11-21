# Yêu cầu cho phiên CEO: thêm lệnh `/claude` vào bot Telegram

Mục tiêu: chủ kênh gõ `/claude` trong Telegram → bot dựng video MR PUMP của đêm gần nhất và gửi lại vào chat.

## Cú pháp
```
/claude                      # đêm gần nhất (23:00 → 07:00 giờ VN), vốn giấy $150
/claude day                  # phiên ngày gần nhất (11:00 → 19:00)
/claude date=2026-11-20      # một đêm cụ thể
/claude start=200            # đổi vốn giấy
```

## Cách bot chạy (trên máy chủ kênh)
1. Chỉ nhận lệnh từ chat ID của chủ kênh (bỏ qua người khác). Mỗi lúc chỉ chạy 1 lần dựng; đang chạy thì trả lời "đang dựng, chờ chút".
2. Trả lời ngay: "MR PUMP đang dựng video đêm <ngày>…".
3. Chạy:
   ```bash
   cd ~/mrpump && git pull -q origin main
   python3 run.py [--session night|day] [--date YYYY-MM-DD] [--start N]   # 2–10 phút
   ```
   (Lần đầu: `git clone https://github.com/nguyentv2912/mrpump ~/mrpump`.)
4. Gửi `output/MR_PUMP_<ngày>[_day].mp4` bằng `sendVideo` (≈8 MB, dưới giới hạn 50 MB của bot), `supports_streaming=true`, caption lấy nguyên từ `output/MR_PUMP_<ngày>[_day].txt` (run.py ghi sẵn).
5. Nếu log có dòng `CẢNH BÁO: chưa có bản quét` thì thêm vào caption: "⚠️ danh sách trending chụp sau đêm (có thiên lệch)".
6. Lỗi (mạng GeckoTerminal, ffmpeg…): gửi 10 dòng cuối của log vào chat, không gửi video.

## Yêu cầu máy
- Python 3.10+, `pip install numpy scipy pillow`, `ffmpeg`.
- Font: JetBrains Mono và Inter. `render.py` đang trỏ cứng tới
  `/usr/share/fonts/truetype/jetbrains-mono/` và `/usr/share/fonts/opentype/inter/` (Linux).
  Máy khác (macOS/Windows) cần cài 2 font này và sửa hai hằng `JB`, `INTER` ở đầu `render.py`.
- Mạng tới `api.geckoterminal.com` (API công khai, không cần key, ~30 lệnh gọi/phút).

## Không làm
- Không tự đăng mạng xã hội từ lệnh `/claude` (đăng qua Buffer cấu hình riêng).
- Không bỏ các nhãn "paper · real prices" / "not financial advice" trong video.

---

# Phần 2: bot tự chạy `/claude` hằng ngày và hẹn đăng Buffer

Phân công: **phiên CEO (bot trên máy chủ kênh) dựng + upload + hẹn đăng**. Các tác vụ trên claude.ai chỉ quét dữ liệu và gửi bản sao cho chủ kênh, **không đăng**.

| Giờ VN | Ai | Việc |
|---|---|---|
| 10:51 | claude.ai | `fetch.py scan --session day` → commit `data/<ngày>_day/` lên main |
| 19:21 | claude.ai | dựng bản sao phiên ngày, gửi chủ kênh (không đăng) |
| **~19:30** | **bot CEO** | **dựng phiên ngày → upload → hẹn đăng** |
| 22:51 | claude.ai | `fetch.py scan` → commit `data/<ngày>/` (bản quét 23:00) lên main |
| 07:21 | claude.ai | dựng bản sao phiên đêm, gửi chủ kênh (không đăng) |
| **~07:30** | **bot CEO** | **dựng phiên đêm → upload → hẹn đăng** |

## 1. Lịch tự chạy (không chỉ khi gõ lệnh)
Thêm 2 job vào bộ lập lịch của bot (giờ Asia/Ho_Chi_Minh):
- **07:30** → tương đương `/claude` (phiên đêm 23:00→07:00 vừa kết thúc)
- **19:30** → tương đương `/claude day` (phiên ngày 11:00→19:00 vừa kết thúc)

Mỗi job:
```bash
cd ~/mrpump && git pull -q origin main          # BẮT BUỘC: lấy bản quét đầu phiên do claude.ai commit
python3 run.py --session night                   # job 07:30   (job 19:30: --session day)
```
- Kết quả: `output/MR_PUMP_<ngày>.mp4` (đêm) hoặc `output/MR_PUMP_<ngày>_day.mp4` (ngày), kèm file `.txt` cùng tên là caption. Dòng JSON cuối của log có `session, date, start, end, pct, trades, wins, losses`.
- Nếu log có `CẢNH BÁO: chưa có bản quét` → vẫn dựng, gửi chủ kênh, nhưng **không hẹn đăng** (danh sách token chụp sau phiên = thiên lệch); báo chủ kênh để quyết.
- Bot **không** commit/push vào repo mrpump (claude.ai lo phần dữ liệu), tránh xung đột.
- Lỗi → gửi 10 dòng cuối log vào Telegram, không đăng.

## 2. Upload + hẹn đăng Buffer (giống /octo và /grok)
1. Upload mp4 lên kho công khai **octo-videos** (đặt tên `mrpump/MR_PUMP_<ngày>[_day].mp4`), lấy **link raw** tải trực tiếp. Kiểm tra link trả về `200` và `Content-Type: video/mp4` trước khi gọi Buffer.
2. Hẹn đăng trên **cả hai kênh** (organization "My Organization"):
   - TikTok **mr.pump395** — channelId `6ae71290e29c69a17125bdd6`
   - Instagram **pumpmeme.crypto** — channelId `6ae71222e29c69a17125ba7a`
3. Tham số `create_post`:
   ```jsonc
   // TikTok
   { "channelId": "6ae71290e29c69a17125bdd6", "schedulingType": "automatic", "mode": "customScheduled",
     "dueAt": "<YYYY-MM-DDThh:mm:00+07:00>", "text": "<nội dung file .txt>",
     "assets": [{ "video": { "url": "<link raw octo-videos>" } }],
     "metadata": { "tiktok": { "isAiGenerated": true } } }
   // Instagram
   { "channelId": "6ae71222e29c69a17125ba7a", "schedulingType": "automatic", "mode": "customScheduled",
     "dueAt": "<cùng quy tắc>", "text": "<nội dung file .txt>",
     "assets": [{ "video": { "url": "<link raw octo-videos>" } }],
     "metadata": { "instagram": { "type": "reel", "shouldShareToFeed": true, "isAiGenerated": true } } }
   ```
4. **Caption** = nguyên file `.txt`. Bắt buộc còn dòng `paper trades trên giá thật · not financial advice` (run.py đã ghi sẵn); thiếu thì không đăng.
5. **2 video MR PUMP mỗi ngày** (1 đêm + 1 ngày) trên mỗi kênh. Giờ gợi ý: video đêm ~12:00, video ngày ~20:30; dời theo quy tắc mục 3.

## 3. Dùng quy tắc sẵn có của bot (chung với /octo, /grok)
- **Không xếp trùng giờ**: kiểm tra hàng đợi Buffer của từng kênh, dời sang khung trống gần nhất (cách bài khác ≥ khoảng cách bot đang dùng).
- **Dữ liệu không cũ quá 24 giờ so với giờ đăng**: tính từ giờ kết thúc phiên (07:00 cho đêm, 19:00 cho ngày). Không còn khung hợp lệ trong 24 giờ → bỏ, báo chủ kênh.
- **Giới hạn video mỗi ngày**: MR PUMP tính chung vào giới hạn của bot. Đầy giới hạn → không hẹn, báo chủ kênh.
- Sau khi hẹn: gửi vào Telegram giờ đăng của từng kênh + link Buffer post.

## 4. Không làm
- Không bỏ nhãn "paper · real prices" trong video hay dòng "paper trades trên giá thật · not financial advice" trong caption.
- Không sửa số lãi/lỗ; phiên lỗ vẫn đăng đúng số lỗ (hoặc bỏ đăng cả phiên, không chỉnh).
- Không dùng tên/logo Claude hay Anthropic trong video/caption; bot tên MR PUMP.
