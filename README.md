# networking — bộ tool cá nhân

Monorepo chứa các công cụ cá nhân, mỗi tool nằm trong một thư mục riêng dưới [`tools/`](tools/).

## Danh sách tool

| Tool | Mô tả | Thư mục |
| --- | --- | --- |
| **ZeroHost** | Chia sẻ thư mục cục bộ ra Internet qua Cloudflare Tunnel, có giao diện Tkinter và tự động cập nhật URL lên gateway (Render). | [`tools/zerohost`](tools/zerohost) |

> Thêm tool mới: tạo thư mục `tools/<tên-tool>/`, đặt mã nguồn + `README.md` riêng, rồi bổ sung một dòng vào bảng trên.

## Cấu trúc repo

```
networking/
├─ README.md            # Mục lục (file này)
├─ .gitignore
└─ tools/
   └─ zerohost/         # Cloudflare Tunnel Host
      ├─ README.md
      ├─ host.py
      ├─ host.exe        (không commit – xem .gitignore)
      └─ cloudflared.exe (không có sẵn – tự tải về)
```

## Quy ước

- **Mỗi tool tự chứa**: mã nguồn, tài liệu và cách build nằm gọn trong `tools/<tên-tool>/`.
- **Không commit binary** (`.exe`, `.dll`, `.pyd`), thư mục `build/`, `dist/`, `__pycache__/`. Phân phối bản build qua **GitHub Releases**.
- `cloudflared.exe` (và các binary phụ thuộc khác) **không có trong repo** — xem README của từng tool để biết cách tải.
