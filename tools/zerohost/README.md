# ZeroHost — Cloudflare Tunnel Host

Công cụ chia sẻ thư mục cục bộ ra Internet thông qua **Cloudflare Tunnel**, kèm giao diện desktop (Tkinter) và khả năng tự động cập nhật URL lên một gateway (Render).

Mã nguồn: `host.py` · Bản đóng gói sẵn cho Windows: `host.exe` (Python 3.13 + PyInstaller).
Bản Linux (CLI headless): `host_linux.py` · Mẫu cấu hình: `.env.example`.

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
├─ host.py             # Bản Windows – giao diện Tkinter
├─ host_linux.py       # Bản Linux – CLI headless, đọc .env
├─ .env.example        # Mẫu .env cho host_linux.py
├─ host.exe            # Bản đóng gói sẵn (Windows)
└─ cloudflared.exe     # KHÔNG có sẵn trong repo – cần tự tải về
```

> ⚠️ **`cloudflared.exe` không có sẵn** trong repository (bị `.gitignore` loại trừ). Bạn phải tự tải và đặt file này vào cùng thư mục (xem bên dưới).

## Yêu cầu

- Windows 10/11.
- `cloudflared.exe` — tải tại: https://github.com/cloudflare/cloudflared/releases (chọn bản `cloudflared-windows-amd64.exe`, sau đó đổi tên thành `cloudflared.exe`).
- (Tùy chọn) Token và URL của Gateway nếu muốn dùng tính năng cập nhật tự động.
- (Chỉ khi chạy từ mã nguồn) Python 3.13 — không cần thư viện ngoài, chỉ dùng thư viện chuẩn (`tkinter`, `http.server`, `subprocess`, `urllib`).
- Linux: xem mục [Bản Linux](#bản-linux-host_linuxpy) — Python 3.8+, không cần `tkinter`.

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

## Bản Linux (`host_linux.py`)

Bản CLI headless, không dùng `tkinter`/X11 — phù hợp VPS, container và systemd. Chỉ cần Python 3.8+ và thư viện chuẩn.

So với bản Windows:

| | `host.py` (Windows) | `host_linux.py` (Linux) |
| --- | --- | --- |
| Giao diện | Tkinter desktop | CLI, log ra stdout (bật/tắt bằng systemd) |
| Cấu hình | Ô nhập trên UI + biến môi trường | `.env` + biến môi trường + tham số CLI |
| Biến URL gateway | `GATEWAY_UPDATE_URL` | `DEFAULT_GATEWAY_UPDATE_URL` (vẫn nhận `GATEWAY_UPDATE_URL`) |
| Biến token | `GATEWAY_UPDATE_TOKEN` | `UPDATE_TOKEN` (vẫn nhận `GATEWAY_UPDATE_TOKEN`) |
| URL cố định | không hỗ trợ | `PUBLIC_URL` – có thì bỏ qua quick tunnel |

### Cài đặt

1. Cài `cloudflared`:

   ```bash
   # Debian/Ubuntu – dùng repo chính thức của Cloudflare
   sudo mkdir -p --mode=0755 /usr/share/keyrings
   curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
     | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
   echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" \
     | sudo tee /etc/apt/sources.list.d/cloudflared.list
   sudo apt update && sudo apt install -y cloudflared

   # Hoặc tải binary trực tiếp
   sudo curl -fsSL -o /usr/local/bin/cloudflared \
     https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
   sudo chmod +x /usr/local/bin/cloudflared
   ```

   Nếu `cloudflared` không nằm trong `PATH`, đặt file `cloudflared` **cạnh** `host_linux.py` (nhớ `chmod +x`).

2. Tạo `.env` và chạy:

   ```bash
   cd tools/zerohost
   cp .env.example .env
   chmod 600 .env            # .env chứa token
   chmod +x host_linux.py

   ./host_linux.py                            # chia sẻ thư mục hiện tại + quick tunnel
   ./host_linux.py -d /srv/files -p 8080      # chọn thư mục và port
   ./host_linux.py --env /etc/zerohost.env    # chỉ định file cấu hình
   ```

### Biến cấu hình

| Biến | Ý nghĩa | Mặc định |
| --- | --- | --- |
| `DEFAULT_GATEWAY_UPDATE_URL` | Endpoint nhận URL công khai | `https://pgt-energy.onrender.com/_gateway/update` |
| `UPDATE_TOKEN` | Token Bearer gửi kèm request | (trống → bỏ qua bước gateway) |
| `PUBLIC_URL` | URL cố định đã có sẵn; **đặt là bỏ qua quick tunnel** | (trống → chạy tunnel) |
| `HOST_DIR` | Thư mục cần chia sẻ | thư mục hiện tại |
| `PORT` | Cổng HTTP server cục bộ | `8000` |

Thứ tự ưu tiên: **tham số CLI > biến môi trường > `.env` > mặc định**. File `.env` được tìm ở thư mục chứa script trước, rồi thư mục hiện tại; chỉ định rõ bằng `--env`. Biến đã tồn tại trong môi trường (systemd `EnvironmentFile`, Docker, `export`) không bị `.env` ghi đè.

Request gửi đi giống hệt bản Windows (`POST` JSON `{"url": "..."}` + `Authorization: Bearer <token>`).

### Hành vi

- Có `PUBLIC_URL` → **không** chạy `cloudflared`; chỉ POST URL đó lên gateway. HTTP server cục bộ vẫn chạy để named tunnel (nếu có) trỏ vào.
- Không có `PUBLIC_URL` → chạy `cloudflared tunnel --url http://localhost:<port>`, bắt URL `*.trycloudflare.com` từ stdout rồi POST lên gateway.
- Thiếu `UPDATE_TOKEN` → cảnh báo và bỏ qua gateway; server/tunnel vẫn chạy bình thường.
- Gọi gateway có retry (mặc định 3 lần, cách 5 giây) với lỗi mạng, HTTP 5xx, 408, 429; các lỗi 4xx khác không retry.
- `--no-server --public-url ...` → chế độ một lần: chỉ POST URL rồi thoát (hợp với cron).
- `Ctrl+C` / `SIGTERM` → dừng `cloudflared` và HTTP server sạch sẽ.
- Mã thoát: `0` bình thường, `1` lỗi khi chạy, `2` cấu hình sai.

Các tùy chọn CLI chính (xem đầy đủ bằng `./host_linux.py --help`):

```
-d, --dir DIR            Thư mục chia sẻ (ghi đè HOST_DIR)
-p, --port PORT          Cổng HTTP server (ghi đè PORT)
    --env PATH           Đường dẫn file .env
    --gateway-url URL    Ghi đè DEFAULT_GATEWAY_UPDATE_URL
    --token TOKEN        Ghi đè UPDATE_TOKEN
    --public-url URL     URL cố định, bỏ qua quick tunnel
    --no-server          Không chạy HTTP server
    --no-tunnel          Không chạy cloudflared
    --no-update          Không gọi API gateway
    --retries N          Số lần thử gọi gateway (mặc định 3)
    --retry-delay GIÂY   Chờ giữa các lần thử (mặc định 5)
```

### Chạy dưới systemd

```ini
# /etc/systemd/system/zerohost.service
[Unit]
Description=ZeroHost - Cloudflare Tunnel file host
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=zerohost
WorkingDirectory=/opt/zerohost
EnvironmentFile=/opt/zerohost/.env
ExecStart=/usr/bin/python3 /opt/zerohost/host_linux.py -d /srv/files -p 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now zerohost
journalctl -u zerohost -f      # xem log
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
