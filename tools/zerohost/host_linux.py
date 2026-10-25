#!/usr/bin/env python3
"""ZeroHost for Linux - chia sẻ thư mục qua Cloudflare Tunnel (headless CLI).

Đây là bản Linux của ``host.py`` (Windows + Tkinter):
  * Không cần GUI/X11, chạy tốt trên VPS, container và dưới systemd.
  * Đọc cấu hình từ file ``.env`` (hoặc biến môi trường).
  * Sau khi có URL công khai, POST URL đó lên gateway kèm Bearer token.

Thứ tự ưu tiên cấu hình: tham số dòng lệnh > biến môi trường > file .env > mặc định.

Biến môi trường:
  DEFAULT_GATEWAY_UPDATE_URL  URL endpoint gateway (fallback: GATEWAY_UPDATE_URL)
  UPDATE_TOKEN                token Bearer (fallback: GATEWAY_UPDATE_TOKEN)
  PUBLIC_URL                  URL cố định; nếu có thì BỎ QUA quick tunnel
  HOST_DIR                    thư mục cần chia sẻ (mặc định: thư mục hiện tại)
  PORT                        cổng HTTP server cục bộ (mặc định: 8000)
"""

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

DEFAULT_GATEWAY_UPDATE_URL = "https://pgt-energy.onrender.com/_gateway/update"
DEFAULT_PORT = 8000
HTTP_TIMEOUT = 30
STOP_TIMEOUT = 10

TUNNEL_URL_PATTERN = re.compile(
    r"https://[-a-zA-Z0-9@:%._\+~#=]{1,256}\.trycloudflare\.com"
)

_log_lock = threading.Lock()


def log(level, message):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with _log_lock:
        print("%s [%s] %s" % (stamp, level, message), flush=True)


def _configure_stdout():
    """Đảm bảo log tiếng Việt không làm crash khi stdout dùng locale lạ."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# .env loader
# ---------------------------------------------------------------------------

_ENV_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def parse_env_file(path):
    """Đọc file .env kiểu KEY=VALUE, trả về dict. Không làm gì nếu file thiếu."""
    values = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError as exc:
        log("ERROR", "Không đọc được %s: %s" % (path, exc))
        return values

    for lineno, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            log("WARN", "%s:%d: bỏ qua dòng không phải KEY=VALUE" % (path, lineno))
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not _ENV_KEY_RE.fullmatch(key):
            log("WARN", "%s:%d: tên biến không hợp lệ: %r" % (path, lineno, key))
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        else:
            # Bỏ comment cuối dòng, chỉ khi có khoảng trắng phía trước.
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()

        values[key] = value

    return values


def load_env_file(explicit_path):
    """Nạp .env vào os.environ. Biến đã có trong môi trường luôn thắng."""
    candidates = []
    if explicit_path:
        candidates.append(Path(explicit_path).expanduser())
    else:
        candidates.append(Path(__file__).resolve().parent / ".env")
        candidates.append(Path.cwd() / ".env")

    for path in candidates:
        if not path.is_file():
            if explicit_path:
                log("ERROR", "Không tìm thấy file .env: %s" % path)
                return None
            continue

        values = parse_env_file(path)
        applied = 0
        for key, value in values.items():
            if key in os.environ:
                log("DEBUG", "%s: giữ giá trị từ môi trường cho %s" % (path.name, key))
                continue
            os.environ[key] = value
            applied += 1

        log("INFO", "Đã nạp %d biến từ %s" % (applied, path))
        return path

    if explicit_path:
        return None
    log("INFO", "Không tìm thấy file .env, dùng biến môi trường / mặc định")
    return None


def _env_value(name, default=None, fallback_name=None):
    value = os.environ.get(name)
    if (value is None or not value.strip()) and fallback_name:
        value = os.environ.get(fallback_name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


# ---------------------------------------------------------------------------
# Cấu hình
# ---------------------------------------------------------------------------


@dataclass
class Config:
    directory: Path
    port: int
    gateway_url: Optional[str]
    token: Optional[str]
    public_url: Optional[str]
    serve: bool
    tunnel: bool
    update_enabled: bool
    retries: int
    retry_delay: float
    cloudflared: Optional[str] = None


def find_cloudflared():
    found = shutil.which("cloudflared")
    if found:
        return found

    for candidate in (
        Path(__file__).resolve().parent / "cloudflared",
        Path.cwd() / "cloudflared",
    ):
        if candidate.is_file() and os.access(str(candidate), os.X_OK):
            return str(candidate)
    return None


def build_config(args):
    """Trả về (Config | None, danh sách lỗi)."""
    errors = []

    directory = Path(
        args.dir or _env_value("HOST_DIR") or os.getcwd()
    ).expanduser()
    if not directory.is_dir():
        errors.append("Thư mục không tồn tại hoặc không phải thư mục: %s" % directory)

    port_raw = args.port if args.port is not None else _env_value("PORT", str(DEFAULT_PORT))
    try:
        port = int(str(port_raw))
    except (TypeError, ValueError):
        errors.append("PORT không hợp lệ: %r" % (port_raw,))
        port = DEFAULT_PORT
    else:
        if not 1 <= port <= 65535:
            errors.append("PORT phải trong khoảng 1..65535: %d" % port)

    public_url = args.public_url or _env_value("PUBLIC_URL")
    if public_url and not re.match(r"^https?://[^\s/]+", public_url):
        errors.append("PUBLIC_URL phải bắt đầu bằng http:// hoặc https://: %s" % public_url)

    gateway_url = args.gateway_url or _env_value(
        "DEFAULT_GATEWAY_UPDATE_URL",
        DEFAULT_GATEWAY_UPDATE_URL,
        fallback_name="GATEWAY_UPDATE_URL",
    )
    if gateway_url and not gateway_url.startswith(("http://", "https://")):
        errors.append(
            "DEFAULT_GATEWAY_UPDATE_URL phải bắt đầu bằng http:// hoặc https://: %s"
            % gateway_url
        )

    token = args.token or _env_value("UPDATE_TOKEN", fallback_name="GATEWAY_UPDATE_TOKEN")

    serve = not args.no_server
    tunnel = not args.no_tunnel and not public_url
    update_enabled = not args.no_update

    if update_enabled and not token:
        log(
            "WARN",
            "Chưa có UPDATE_TOKEN; bỏ qua cập nhật gateway "
            "(server/tunnel vẫn chạy bình thường)",
        )
        update_enabled = False
    if update_enabled and errors:
        # Tránh gọi API với cấu hình sai; lỗi đã được báo ở trên.
        update_enabled = False

    cloudflared = None
    if tunnel:
        cloudflared = find_cloudflared()
        if not cloudflared:
            errors.append(
                "Không tìm thấy 'cloudflared'. Cài bằng "
                "'sudo apt install cloudflared' hoặc tải từ "
                "https://github.com/cloudflare/cloudflared/releases rồi đặt "
                "cạnh host_linux.py (nhớ chmod +x)."
            )

    if not serve and not public_url:
        errors.append(
            "Chế độ --no-server chỉ dùng được khi có PUBLIC_URL "
            "(chỉ đẩy URL lên gateway, không chạy server/tunnel)."
        )

    if errors:
        return None, errors

    return (
        Config(
            directory=directory.resolve(),
            port=port,
            gateway_url=gateway_url,
            token=token,
            public_url=public_url,
            serve=serve,
            tunnel=tunnel,
            update_enabled=update_enabled,
            retries=max(1, args.retries),
            retry_delay=max(0.0, args.retry_delay),
            cloudflared=cloudflared,
        ),
        [],
    )


# ---------------------------------------------------------------------------
# Gateway API
# ---------------------------------------------------------------------------


def _mask(secret):
    if not secret:
        return "(trống)"
    if len(secret) <= 6:
        return "*" * len(secret)
    return secret[:4] + "*" * (len(secret) - 6) + secret[-2:]


def push_gateway(public_url, gateway_url, token, retries=3, retry_delay=5.0):
    """POST {"url": public_url} lên gateway. Trả về True nếu thành công."""
    payload = json.dumps({"url": public_url}).encode("utf-8")
    request = urllib.request.Request(gateway_url, data=payload, method="POST")
    request.add_header("Authorization", "Bearer %s" % token)
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", "zerohost-linux/1.0")

    for attempt in range(1, retries + 1):
        log(
            "INFO",
            "Cập nhật gateway %s (lần %d/%d) cho %s"
            % (gateway_url, attempt, retries, public_url),
        )
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
                body = response.read().decode("utf-8", "replace")
                log("INFO", "Gateway đã cập nhật (HTTP %d): %s" % (response.status, body))
                return True
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", "replace")
            except Exception:
                body = ""
            log("ERROR", "Gateway trả HTTP %d: %s" % (exc.code, body))
            retryable = exc.code >= 500 or exc.code in (408, 429)
            if not retryable:
                return False
        except urllib.error.URLError as exc:
            log("ERROR", "Không kết nối được gateway: %s" % (exc.reason,))
        except Exception as exc:  # noqa: BLE001 - CLI cần log mọi lỗi mạng
            log("ERROR", "Lỗi cập nhật gateway: %s" % (exc,))

        if attempt < retries:
            log("INFO", "Thử lại sau %.1fs" % retry_delay)
            time.sleep(retry_delay)

    log("ERROR", "Cập nhật gateway thất bại sau %d lần" % retries)
    return False


# ---------------------------------------------------------------------------
# HTTP server & tunnel
# ---------------------------------------------------------------------------


class LoggingRequestHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler ghi log qua logger chung thay vì stderr."""

    def log_message(self, fmt, *args):
        log("HTTP", "%s %s" % (self.address_string(), fmt % args))

    def log_error(self, fmt, *args):
        log("HTTP", "%s %s" % (self.address_string(), fmt % args))


def start_http_server(directory, port):
    handler = partial(LoggingRequestHandler, directory=str(directory))
    httpd = ThreadingHTTPServer(("", port), handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, name="http-server", daemon=True)
    thread.start()
    return httpd


def _push_async(public_url, cfg):
    if not cfg.update_enabled:
        log("INFO", "Bỏ qua cập nhật gateway (không bật cập nhật)")
        return
    threading.Thread(
        target=push_gateway,
        args=(public_url, cfg.gateway_url, cfg.token, cfg.retries, cfg.retry_delay),
        name="gateway-update",
        daemon=True,
    ).start()


def run_tunnel(cfg, stop_event, url_event, state):
    cmd = [
        cfg.cloudflared,
        "tunnel",
        "--no-autoupdate",
        "--url",
        "http://127.0.0.1:%d" % cfg.port,
    ]
    log("INFO", "Khởi chạy: %s" % " ".join(cmd))

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except OSError as exc:
        log("ERROR", "Không chạy được cloudflared: %s" % exc)
        state["failed"] = True
        stop_event.set()
        return

    state["process"] = process
    stdout = process.stdout

    try:
        for raw_line in stdout:
            line = raw_line.rstrip()
            if not line:
                continue
            log("TUNNEL", line)

            match = TUNNEL_URL_PATTERN.search(line)
            if match and not url_event.is_set():
                public_url = match.group(0)
                url_event.set()
                log("INFO", "URL Cloudflare: %s" % public_url)
                _push_async(public_url, cfg)
    except Exception as exc:  # noqa: BLE001
        log("ERROR", "Lỗi đọc log cloudflared: %s" % exc)
        if not stop_event.is_set():
            state["failed"] = True
            # Đóng pipe để vòng lặp không treo ở process.wait() bên dưới.
            try:
                process.terminate()
            except Exception:
                pass
    finally:
        try:
            stdout.close()
        except Exception:
            pass

    code = process.wait()
    state["process"] = None

    if stop_event.is_set():
        return

    if not url_event.is_set():
        log("ERROR", "cloudflared kết thúc (exit %s) trước khi lấy được URL" % code)
        state["failed"] = True
    else:
        log("ERROR", "cloudflared đã dừng ngoài ý muốn (exit %s)" % code)
        state["failed"] = True
    stop_event.set()


def _terminate(process):
    if process is None or process.poll() is not None:
        return
    log("INFO", "Dừng cloudflared (pid %d)..." % process.pid)
    try:
        process.terminate()
    except Exception:
        return
    try:
        process.wait(timeout=STOP_TIMEOUT)
    except subprocess.TimeoutExpired:
        log("WARN", "cloudflared không thoát sau %ds, kill..." % STOP_TIMEOUT)
        try:
            process.kill()
            process.wait(timeout=STOP_TIMEOUT)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="host_linux.py",
        description=(
            "Chia sẻ thư mục qua Cloudflare Tunnel trên Linux (headless) và "
            "cập nhật URL công khai lên gateway."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-d", "--dir", help="Thư mục cần chia sẻ (ghi đè HOST_DIR)")
    parser.add_argument("-p", "--port", type=int, help="Cổng HTTP server cục bộ (ghi đè PORT)")
    parser.add_argument("--env", help="Đường dẫn file .env (mặc định: cạnh script hoặc CWD)")
    parser.add_argument("--gateway-url", help="Ghi đè DEFAULT_GATEWAY_UPDATE_URL")
    parser.add_argument("--token", help="Ghi đè UPDATE_TOKEN")
    parser.add_argument(
        "--public-url",
        help="URL cố định đã có sẵn; nếu đặt thì không chạy quick tunnel",
    )
    parser.add_argument("--no-server", action="store_true", help="Không chạy HTTP server cục bộ")
    parser.add_argument("--no-tunnel", action="store_true", help="Không chạy cloudflared")
    parser.add_argument("--no-update", action="store_true", help="Không gọi API gateway")
    parser.add_argument("--retries", type=int, default=3, help="Số lần thử khi gọi gateway")
    parser.add_argument(
        "--retry-delay", type=float, default=5.0, help="Giây chờ giữa các lần thử"
    )
    parser.add_argument("--version", action="version", version="zerohost-linux 1.0")
    return parser.parse_args(argv)


def _install_signal_handlers(stop_event):
    def handler(signum, _frame):
        try:
            name = signal.Signals(signum).name
        except ValueError:
            name = str(signum)
        log("INFO", "Nhận tín hiệu %s, đang dừng..." % name)
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError):
            # Không phải main thread (ví dụ khi được import) - bỏ qua.
            pass


def main(argv=None):
    _configure_stdout()
    args = parse_args(argv)

    env_path = load_env_file(args.env)
    if args.env and env_path is None:
        return 2

    cfg, errors = build_config(args)
    if errors:
        for message in errors:
            log("ERROR", message)
        return 2

    log("INFO", "Thư mục chia sẻ : %s" % cfg.directory)
    log("INFO", "Port cục bộ    : %d" % cfg.port)
    log("INFO", "Gateway        : %s" % (cfg.gateway_url or "(không dùng)"))
    log("INFO", "Token          : %s" % _mask(cfg.token))
    log("INFO", "Chế độ         : %s" % ("PUBLIC_URL cố định" if cfg.public_url else "quick tunnel"))
    log(
        "INFO",
        "HTTP server    : %s"
        % ("bật" if cfg.serve else "tắt (--no-server)"),
    )

    stop_event = threading.Event()
    url_event = threading.Event()
    state = {"process": None, "failed": False}
    _install_signal_handlers(stop_event)

    httpd = None
    if cfg.serve:
        try:
            httpd = start_http_server(cfg.directory, cfg.port)
        except OSError as exc:
            log("ERROR", "Không mở được HTTP server tại port %d: %s" % (cfg.port, exc))
            return 1
        log("INFO", "HTTP server đang chạy tại http://localhost:%d" % cfg.port)

    start_time = time.time()
    try:
        if cfg.public_url:
            url_event.set()
            log("INFO", "Dùng PUBLIC_URL từ cấu hình: %s" % cfg.public_url)

            if not cfg.serve:
                # Chế độ một lần: chỉ đẩy URL lên gateway rồi thoát.
                if not cfg.update_enabled:
                    log("INFO", "Không có cập nhật gateway để gửi (thiếu token hoặc --no-update).")
                    return 0
                ok = push_gateway(
                    cfg.public_url,
                    cfg.gateway_url,
                    cfg.token,
                    cfg.retries,
                    cfg.retry_delay,
                )
                return 0 if ok else 1

            _push_async(cfg.public_url, cfg)
        else:
            log("INFO", "Đang chờ cloudflared lấy URL công khai...")
            threading.Thread(
                target=run_tunnel,
                args=(cfg, stop_event, url_event, state),
                name="cloudflared",
                daemon=True,
            ).start()

        warned = False
        while not stop_event.is_set():
            stop_event.wait(1.0)
            if (
                cfg.tunnel
                and not warned
                and not url_event.is_set()
                and time.time() - start_time > 60
            ):
                warned = True
                log("WARN", "Sau 60s vẫn chưa lấy được URL, tiếp tục chờ...")
    except KeyboardInterrupt:
        log("INFO", "Ctrl+C - đang dừng...")
        stop_event.set()

    log("INFO", "Đang dọn dẹp...")
    if httpd is not None:
        try:
            httpd.shutdown()
            httpd.server_close()
        except Exception:
            pass
    _terminate(state.get("process"))
    log("INFO", "Đã dừng.")
    return 1 if state.get("failed") else 0


if __name__ == "__main__":
    sys.exit(main())
