# ZeroHost — Cloudflare Tunnel Host

Công cụ chia sẻ thư mục cục bộ ra Internet thông qua **Cloudflare Tunnel**, kèm giao diện desktop (Tkinter) và khả năng tự động cập nhật URL lên một gateway (Render).

Mã nguồn: `host.py` · Bản đóng gói sẵn cho Windows: `host.exe` (Python 3.13 + PyInstaller).

---

## Tính năng

- Chọn thư mục bất kỳ trên máy để chia sẻ.
- Dựng **HTTP Server** cục bộ phục vụ nội dung thư mục đó (mặc định port `8000`).
- Mở **Cloudflare Tunnel** (`cloudflared tunnel --url http://localhost:<port>`) để lấy URL công khai dạng `https://xxxx.trycloudflare.com`.
- Hiển thị URL công khai, cho phép **Sao chép** và **Mở URL** trên trình duyệt.
- **Tự động cập nhật Gateway**: gửi URL vừa tạo lên một gateway HTTP (mặc định là Render) kèm token xác thực.
- Khu vực **Log Hệ Thống** hiển thị trạng thái server, tunnel và gateway theo thời gian thực.

## Cấu trúc

```
tools/zerohost/
├─ README.md           # Tài liệu này
├─ host.py             # Mã nguồn chính (giao diện Tkinter)
├─ host.exe            # Bản đóng gói sẵn (Windows)
└─ cloudflared.exe     # KHÔNG có sẵn trong repo – cần tự tải về
```

> ⚠️ **`cloudflared.exe` không có sẵn** trong repository (bị `.gitignore` loại trừ). Bạn phải tự tải và đặt file này vào cùng thư mục (xem bên dưới).

## Yêu cầu

- Windows 10/11.
- `cloudflared.exe` — tải tại: https://github.com/cloudflare/cloudflared/releases (chọn bản `cloudflared-windows-amd64.exe`, sau đó đổi tên thành `cloudflared.exe`).
- (Tùy chọn) Token và URL của Gateway nếu muốn dùng tính năng cập nhật tự động.
- (Chỉ khi chạy từ mã nguồn) Python 3.13 — không cần thư viện ngoài, chỉ dùng thư viện chuẩn (`tkinter`, `http.server`, `subprocess`, `urllib`).

## Cài đặt & chạy

1. Tải `cloudflared.exe` và đặt **cùng cấp** với `host.exe`/`host.py`:

   ```
   tools/zerohost/
   ├─ host.py (hoặc host.exe)
   └─ cloudflared.exe
   ```

2. Chạy ứng dụng — chọn một trong hai cách:

   **Cách A — dùng bản đóng gói sẵn (không cần Python):**

   ```
   tools\zerohost\host.exe
   ```

   **Cách B — chạy trực tiếp từ mã nguồn (cần Python 3.13):**

   ```powershell
   cd tools\zerohost
   python host.py
   ```

   > Ứng dụng tìm `cloudflared.exe` trong thư mục hiện tại (trên Windows) hoặc `./cloudflared` (trên các hệ điều hành khác). Nếu đặt sai vị trí, app sẽ báo:
   > `Không tìm thấy file 'cloudflared.exe' trong thư mục hiện tại!`

3. Trên giao diện:
   - **Thư mục host**: bấm `Chọn...` để trỏ tới thư mục muốn chia sẻ.
   - **Port Local**: nhập port (mặc định `8000`).
   - Bấm **▶ Khởi Chạy Server** để bật HTTP Server và Cloudflare Tunnel.
   - Khi tunnel kết nối xong, URL công khai sẽ hiện ở mục *2. Kết nối Cloudflare Tunnel*. Dùng `Sao chép` / `Mở URL` để chia sẻ.
   - Bấm **⏹ Dừng Server** (hoặc đóng cửa sổ) để tắt server và tunnel.

## Cập nhật Gateway tự động

Ứng dụng có thể POST URL công khai lên một endpoint gateway sau khi tunnel sẵn sàng.

- **URL Gateway**: mặc định `https://pgt-energy.onrender.com/_gateway/update`, có thể ghi đè bằng biến môi trường `GATEWAY_UPDATE_URL`.
- **Token**: lấy từ biến môi trường `GATEWAY_UPDATE_TOKEN` (cũng có thể nhập trực tiếp vào ô `Token` trên giao diện).

Request gửi đi:

```http
POST <URL Gateway>
Authorization: Bearer <token>
Content-Type: application/json

{ "url": "<public-url>" }
```

Nếu chưa có URL Gateway hợp lệ hoặc chưa có token, bước cập nhật tự động sẽ bị bỏ qua và ghi log cảnh báo (server/tunnel vẫn chạy bình thường).

Ví dụ thiết lập biến môi trường (PowerShell):

```powershell
$env:GATEWAY_UPDATE_TOKEN = "your-token"
$env:GATEWAY_UPDATE_URL   = "https://example.com/_gateway/update"
.\tools\zerohost\host.exe
```

## Build lại `host.exe` từ mã nguồn

Cần Python 3.13 và PyInstaller:

```powershell
cd tools\zerohost
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name host host.py
```

File kết quả nằm ở `tools\zerohost\dist\host.exe`. Copy đè lên `tools\zerohost\host.exe` và đặt cạnh `cloudflared.exe` để sử dụng.

## Công nghệ sử dụng

- Python 3.13, `tkinter`/`ttk` cho giao diện.
- `http.server` (`HTTPServer` + `SimpleHTTPRequestHandler`) cho HTTP server cục bộ.
- `subprocess` để chạy `cloudflared`, `threading` để chạy server và tunnel song song.
- `urllib.request` để gọi gateway.
- Đóng gói bằng PyInstaller (một file `host.exe`).

## Ghi chú

- Đây là công cụ tiện lợi cho việc chia sẻ nhanh nội dung cục bộ; **không** có xác thực cho HTTP server, nên bất kỳ ai có URL đều xem được nội dung trong thư mục đã chọn. Cân nhắc trước khi chia sẻ thư mục nhạy cảm.
- URL `trycloudflare.com` là quick tunnel tạm thời, sẽ thay đổi mỗi lần khởi chạy.
- Cần kết nối Internet để tải `cloudflared` tạo tunnel và để gọi gateway.
