# Yêu cầu cho phiên CEO: thêm lệnh `/claude` vào bot Telegram

Mục tiêu: chủ kênh gõ `/claude` trong Telegram → bot dựng video MR PUMP của đêm gần nhất và gửi lại vào chat.

## Cú pháp
```
/claude                      # đêm gần nhất (23:00 → 07:00 giờ VN), vốn giấy $150
/claude date=2026-11-20      # một đêm cụ thể
/claude start=200            # đổi vốn giấy
```

## Cách bot chạy (trên máy chủ kênh)
1. Chỉ nhận lệnh từ chat ID của chủ kênh (bỏ qua người khác). Mỗi lúc chỉ chạy 1 lần dựng; đang chạy thì trả lời "đang dựng, chờ chút".
2. Trả lời ngay: "MR PUMP đang dựng video đêm <ngày>…".
3. Chạy:
   ```bash
   cd ~/mrpump && git pull -q origin main
   python3 run.py [--date YYYY-MM-DD] [--start N]      # 1–3 phút
   ```
   (Lần đầu: `git clone https://github.com/nguyentv2912/mrpump ~/mrpump`.)
4. Gửi `output/MR_PUMP_<ngày>.mp4` bằng `sendVideo` (≈8 MB, dưới giới hạn 50 MB của bot), `supports_streaming=true`, caption lấy từ `data/<ngày>/night.json`:
   `MR PUMP · <ngày> · $<start> → $<end> (<+x.x%>) · <trades> lệnh <wins>W/<losses>L · paper trades trên giá thật`
5. Nếu log có dòng `CẢNH BÁO: chưa có bản quét lúc 23:00` thì thêm vào caption: "⚠️ danh sách trending chụp sau đêm (có thiên lệch)".
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
