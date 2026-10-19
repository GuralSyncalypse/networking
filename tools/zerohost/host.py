import os
import re
import json
import subprocess
import threading
import tkinter as tk
import urllib.request
import urllib.error

from http.server import HTTPServer, SimpleHTTPRequestHandler
from tkinter import filedialog, messagebox, ttk
import webbrowser


DEFAULT_GATEWAY_UPDATE_URL = (
    "https://pgt-energy.onrender.com/_gateway/update"
)


class CloudflaredHostApp:

    def __init__(self, root):
        self.root = root
        self.root.title("Cloudflare Tunnel Host")
        self.root.geometry("520x525")
        self.root.resizable(False, False)

        self.httpd = None
        self.cloudflared_process = None
        self.server_thread = None
        self.tunnel_thread = None
        self.public_url = None

        self._setup_ui()

    def _setup_ui(self):
        # Frame chọn thư mục
        folder_frame = ttk.LabelFrame(
            self.root,
            text=" 1. Thư mục host ",
            padding=10
        )
        folder_frame.pack(fill="x", padx=15, pady=10)

        self.dir_var = tk.StringVar(value=os.getcwd())

        ttk.Entry(
            folder_frame,
            textvariable=self.dir_var,
            width=45
        ).pack(
            side="left",
            padx=(0, 5)
        )

        ttk.Button(
            folder_frame,
            text="Chọn...",
            command=self._browse_folder
        ).pack(side="left")

        # Frame control
        control_frame = ttk.Frame(
            self.root,
            padding=5
        )
        control_frame.pack(
            fill="x",
            padx=15
        )

        ttk.Label(
            control_frame,
            text="Port Local:"
        ).pack(
            side="left",
            padx=(0, 5)
        )

        self.port_var = tk.StringVar(value="8000")

        ttk.Entry(
            control_frame,
            textvariable=self.port_var,
            width=8
        ).pack(
            side="left",
            padx=(0, 20)
        )

        self.btn_start = ttk.Button(
            control_frame,
            text="▶ Khởi Chạy Server",
            command=self._start_hosting
        )
        self.btn_start.pack(
            side="left",
            padx=5
        )

        self.btn_stop = ttk.Button(
            control_frame,
            text="⏹ Dừng Server",
            command=self._stop_hosting,
            state="disabled"
        )
        self.btn_stop.pack(
            side="left",
            padx=5
        )

        # Gateway settings.  The values can be changed for each run without
        # modifying this file.  Environment variables keep unattended runs
        # convenient and avoid putting a token in source code.
        gateway_frame = ttk.LabelFrame(
            self.root,
            text=" Gateway cập nhật tự động ",
            padding=10
        )
        gateway_frame.pack(
            fill="x",
            padx=15,
            pady=(5, 0)
        )

        self.gateway_url_var = tk.StringVar(
            value=os.environ.get(
                "GATEWAY_UPDATE_URL",
                DEFAULT_GATEWAY_UPDATE_URL
            )
        )
        self.gateway_token_var = tk.StringVar(
            value=os.environ.get("GATEWAY_UPDATE_TOKEN", "")
        )

        ttk.Label(gateway_frame, text="URL Gateway:").grid(
            row=0, column=0, sticky="w", padx=(0, 5), pady=(0, 5)
        )
        ttk.Entry(
            gateway_frame,
            textvariable=self.gateway_url_var,
            width=51
        ).grid(row=0, column=1, sticky="ew", pady=(0, 5))

        ttk.Label(gateway_frame, text="Token:").grid(
            row=1, column=0, sticky="w", padx=(0, 5)
        )
        ttk.Entry(
            gateway_frame,
            textvariable=self.gateway_token_var,
            show="*",
            width=51
        ).grid(row=1, column=1, sticky="ew")
        gateway_frame.columnconfigure(1, weight=1)

        # Frame kết quả URL
        result_frame = ttk.LabelFrame(
            self.root,
            text=" 2. Kết nối Cloudflare Tunnel ",
            padding=10
        )
        result_frame.pack(
            fill="x",
            padx=15,
            pady=10
        )

        self.lbl_status = ttk.Label(
            result_frame,
            text="Trạng thái: Chưa hoạt động",
            font=("Arial", 9, "bold")
        )
        self.lbl_status.pack(
            anchor="w",
            pady=(0, 5)
        )

        url_inner_frame = ttk.Frame(
            result_frame
        )
        url_inner_frame.pack(
            fill="x"
        )

        self.url_var = tk.StringVar(
            value="Chờ khởi chạy..."
        )

        self.entry_url = ttk.Entry(
            url_inner_frame,
            textvariable=self.url_var,
            state="readonly"
        )
        self.entry_url.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 5)
        )

        self.btn_copy = ttk.Button(
            url_inner_frame,
            text="Sao chép",
            command=self._copy_url,
            state="disabled"
        )
        self.btn_copy.pack(
            side="left",
            padx=(0, 5)
        )

        self.btn_open = ttk.Button(
            url_inner_frame,
            text="Mở URL",
            command=self._open_url,
            state="disabled"
        )
        self.btn_open.pack(
            side="left"
        )

        self.btn_update_gateway = ttk.Button(
            result_frame,
            text="Cập nhật Gateway ngay",
            command=self._update_current_gateway,
            state="disabled"
        )
        self.btn_update_gateway.pack(
            anchor="w",
            pady=(7, 0)
        )

        # Gateway status
        self.lbl_gateway = ttk.Label(
            result_frame,
            text="Gateway: Chưa cập nhật"
        )
        self.lbl_gateway.pack(
            anchor="w",
            pady=(8, 0)
        )

        # Log
        log_frame = ttk.LabelFrame(
            self.root,
            text=" Log Hệ Thống ",
            padding=5
        )
        log_frame.pack(
            fill="both",
            expand=True,
            padx=15,
            pady=(0, 10)
        )

        self.txt_log = tk.Text(
            log_frame,
            height=7,
            state="disabled",
            font=("Consolas", 8)
        )
        self.txt_log.pack(
            fill="both",
            expand=True
        )

    def _log(self, text):
        # Luôn update Tkinter từ main thread
        self.root.after(
            0,
            self._append_log,
            text
        )

    def _append_log(self, text):
        self.txt_log.config(
            state="normal"
        )
        self.txt_log.insert(
            "end",
            f"{text}\n"
        )
        self.txt_log.see("end")
        self.txt_log.config(
            state="disabled"
        )

    def _browse_folder(self):
        selected = filedialog.askdirectory(
            initialdir=self.dir_var.get()
        )

        if selected:
            self.dir_var.set(selected)

    def _copy_url(self):
        url = self.url_var.get()

        if url.startswith("http"):
            self.root.clipboard_clear()
            self.root.clipboard_append(url)

            messagebox.showinfo(
                "Thành công",
                "Đã chép URL vào khay nhớ tạm!"
            )

    def _open_url(self):
        url = self.url_var.get()

        if url.startswith("http"):
            webbrowser.open(url)

    # =========================================================
    # UPDATE RENDER GATEWAY
    # =========================================================

    def _gateway_settings(self, show_error=True):
        """Read and validate the current UI settings on the Tk thread."""
        gateway_url = self.gateway_url_var.get().strip()
        token = self.gateway_token_var.get().strip()

        if not gateway_url.startswith(("http://", "https://")):
            if show_error:
                messagebox.showerror(
                    "Lỗi Gateway",
                    "URL Gateway phải bắt đầu bằng http:// hoặc https://"
                )
            else:
                self._log("[!] URL Gateway không hợp lệ; bỏ qua cập nhật tự động")
            return None

        if not token:
            if show_error:
                messagebox.showerror(
                    "Lỗi Gateway",
                    "Vui lòng nhập token Gateway. Token có thể tự điền bằng "
                    "biến môi trường GATEWAY_UPDATE_TOKEN."
                )
            else:
                self._log("[!] Chưa có token; bỏ qua cập nhật Gateway tự động")
            return None

        return gateway_url, token

    def _update_current_gateway(self):
        if not self.public_url:
            return

        settings = self._gateway_settings()
        if not settings:
            return

        gateway_url, token = settings
        threading.Thread(
            target=self._update_gateway,
            args=(self.public_url, gateway_url, token),
            daemon=True
        ).start()

    def _update_gateway(self, public_url, gateway_url, token):

        if not token:
            self._log(
                "[!] Không tìm thấy biến môi trường "
                "GATEWAY_UPDATE_TOKEN"
            )

            self.root.after(
                0,
                lambda: self.lbl_gateway.config(
                    text="Gateway: Thiếu token",
                    foreground="red"
                )
            )

            return

        payload = json.dumps({
            "url": public_url
        }).encode("utf-8")

        request = urllib.request.Request(
            gateway_url,
            data=payload,
            method="POST"
        )

        request.add_header(
            "Authorization",
            f"Bearer {token}"
        )

        request.add_header(
            "Content-Type",
            "application/json"
        )

        self._log(
            "[*] Đang cập nhật URL lên Render Gateway..."
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=30
            ) as response:

                body = response.read().decode(
                    "utf-8"
                )

                if response.status == 200:
                    self._log(
                        "[SUCCESS] Gateway đã cập nhật thành công"
                    )

                    self._log(
                        f"[Gateway Response] {body}"
                    )

                    self.root.after(
                        0,
                        lambda: self.lbl_gateway.config(
                            text="Gateway: Đã cập nhật",
                            foreground="green"
                        )
                    )

                else:
                    self._log(
                        f"[!] Gateway trả HTTP "
                        f"{response.status}"
                    )

        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode(
                    "utf-8"
                )
            except Exception:
                body = ""

            self._log(
                f"[!] Gateway HTTP Error: "
                f"{e.code} {body}"
            )

            self.root.after(
                0,
                lambda: self.lbl_gateway.config(
                    text=f"Gateway: Lỗi HTTP {e.code}",
                    foreground="red"
                )
            )

        except urllib.error.URLError as e:
            self._log(
                f"[!] Không kết nối được Render: "
                f"{e.reason}"
            )

            self.root.after(
                0,
                lambda: self.lbl_gateway.config(
                    text="Gateway: Không kết nối được",
                    foreground="red"
                )
            )

        except Exception as e:
            self._log(
                f"[!] Lỗi update gateway: {e}"
            )

            self.root.after(
                0,
                lambda: self.lbl_gateway.config(
                    text="Gateway: Update thất bại",
                    foreground="red"
                )
            )

    def _start_hosting(self):
        directory = self.dir_var.get()
        port_str = self.port_var.get()

        if not os.path.isdir(directory):
            messagebox.showerror(
                "Lỗi",
                "Thư mục chọn không hợp lệ!"
            )
            return

        if not port_str.isdigit():
            messagebox.showerror(
                "Lỗi",
                "Port phải là một số!"
            )
            return

        port = int(port_str)
        self.public_url = None

        executable = (
            "cloudflared.exe"
            if os.name == "nt"
            else "./cloudflared"
        )

        if not os.path.exists(executable):
            messagebox.showerror(
                "Lỗi",
                (
                    f"Không tìm thấy file "
                    f"'{executable}' trong thư mục hiện tại!\n"
                    "Vui lòng đặt file thực thi cùng cấp "
                    "với file Python này."
                )
            )
            return

        self.btn_start.config(
            state="disabled"
        )

        self.btn_stop.config(
            state="normal"
        )

        self.btn_update_gateway.config(
            state="disabled"
        )

        self.lbl_status.config(
            text="Trạng thái: Đang khởi tạo server...",
            foreground="orange"
        )

        self.lbl_gateway.config(
            text="Gateway: Chờ Tunnel...",
            foreground="orange"
        )

        self.url_var.set(
            "Đang tạo đường dẫn..."
        )

        self._log(
            f"--- Bắt đầu host thư mục: "
            f"{directory} ---"
        )

        # ================================================
        # HTTP SERVER
        # ================================================

        def run_http():
            try:
                handler = lambda *args, **kwargs: (
                    SimpleHTTPRequestHandler(
                        *args,
                        directory=directory,
                        **kwargs
                    )
                )

                self.httpd = HTTPServer(
                    ("", port),
                    handler
                )

                self._log(
                    f"[+] Local HTTP Server "
                    f"đã chạy tại port {port}"
                )

                self.httpd.serve_forever()

            except Exception as e:
                self._log(
                    f"[!] Lỗi HTTP Server: {e}"
                )

        self.server_thread = threading.Thread(
            target=run_http,
            daemon=True
        )

        self.server_thread.start()

        # ================================================
        # CLOUDFLARED
        # ================================================

        def run_tunnel():

            cmd = [
                executable,
                "tunnel",
                "--url",
                f"http://localhost:{port}"
            ]

            try:
                self.cloudflared_process = (
                    subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        creationflags=(
                            subprocess.CREATE_NO_WINDOW
                            if os.name == "nt"
                            else 0
                        )
                    )
                )

                url_pattern = re.compile(
                    r"https://"
                    r"[-a-zA-Z0-9@:%._\+~#=]{1,256}"
                    r"\.trycloudflare\.com"
                )

                for line in (
                    self.cloudflared_process.stdout
                ):
                    line = line.strip()

                    if line:
                        self._log(
                            f"[cloudflared] {line}"
                        )

                    match = url_pattern.search(
                        line
                    )

                    if match:
                        public_url = match.group(0)

                        self.root.after(
                            0,
                            self._on_tunnel_success,
                            public_url
                        )

                        # Không break ở đây.
                        # Tiếp tục đọc stdout để tránh pipe đầy.
                        # Tunnel vẫn chạy bình thường.

            except Exception as e:
                self._log(
                    f"[!] Lỗi Cloudflared: {e}"
                )

        self.tunnel_thread = threading.Thread(
            target=run_tunnel,
            daemon=True
        )

        self.tunnel_thread.start()

    def _on_tunnel_success(
        self,
        public_url
    ):
        self.url_var.set(
            public_url
        )
        self.public_url = public_url

        self.lbl_status.config(
            text="Trạng thái: Đang kết nối Online",
            foreground="green"
        )

        self.btn_copy.config(
            state="normal"
        )

        self.btn_open.config(
            state="normal"
        )

        self.btn_update_gateway.config(
            state="normal"
        )

        self._log(
            f"[SUCCESS] URL Cloudflare: "
            f"{public_url}"
        )

        # The form may be edited between runs, so take its latest values just
        # before the automatic request is made.
        settings = self._gateway_settings(show_error=False)
        if settings:
            gateway_url, token = settings
            threading.Thread(
                target=self._update_gateway,
                args=(public_url, gateway_url, token),
                daemon=True
            ).start()

    def _stop_hosting(self):

        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass

            self.httpd = None

        if self.cloudflared_process:
            try:
                self.cloudflared_process.terminate()
            except Exception:
                pass

            self.cloudflared_process = None

        self.btn_start.config(
            state="normal"
        )

        self.btn_stop.config(
            state="disabled"
        )

        self.btn_copy.config(
            state="disabled"
        )

        self.btn_open.config(
            state="disabled"
        )

        self.btn_update_gateway.config(
            state="disabled"
        )

        self.lbl_status.config(
            text="Trạng thái: Đã dừng",
            foreground="red"
        )

        self.lbl_gateway.config(
            text="Gateway: Đã dừng",
            foreground="red"
        )

        self.url_var.set(
            "Chờ khởi chạy..."
        )
        self.public_url = None

        self._log(
            "--- Đã dừng Server thành công ---"
        )


if __name__ == "__main__":

    root = tk.Tk()

    app = CloudflaredHostApp(
        root
    )

    def on_closing():
        app._stop_hosting()
        root.destroy()

    root.protocol(
        "WM_DELETE_WINDOW",
        on_closing
    )

    root.mainloop()
