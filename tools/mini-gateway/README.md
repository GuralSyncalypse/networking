# Mini Gateway — Netty TCP Reverse Proxy

Reverse proxy TCP (Layer 4) 1-1 hiệu năng cao, viết bằng Java 11 + Netty. Proxy không phân tích giao thức nên dùng được cho HTTP, HTTPS/TLS, SSH, WebSocket, database... bất kỳ luồng TCP nào.

```
Client ──:8080──> Proxy (Netty) ──:9999──> Backend
```

- Mỗi kết nối client được ánh xạ 1-1 sang một kết nối backend riêng.
- Dữ liệu được chuyển tiếp nguyên byte, không buffer toàn bộ message.
- Backpressure hai chiều bằng `AUTO_READ=false` + `read()` theo khả năng ghi của đầu bên kia, tránh tràn bộ nhớ khi client/backend chậm.
- `TCP_NODELAY`, `SO_KEEPALIVE`, `SO_REUSEADDR`, backlog 1024.
- Đóng kết nối còn lại khi một đầu ngắt (half-close được xử lý bằng flush trước khi close).

## Yêu cầu

- JDK 11 trở lên (đã kiểm thử với JDK 27)
- Maven 3.6+ (hoặc dùng Maven wrapper của IDE)

## Build

```bash
cd tools/mini-gateway
mvn clean package
```

Kết quả: `target/mini-gateway.jar` — fat jar chạy độc lập, không cần classpath.

Chỉ build, bỏ qua test:

```bash
mvn clean package -DskipTests
```

## Chạy

Mặc định lắng nghe `8080` và chuyển tiếp tới `127.0.0.1:9999`:

```bash
java -jar target/mini-gateway.jar
```

Tuỳ chỉnh bằng tham số dòng lệnh:

```bash
java -jar target/mini-gateway.jar --local-port 8080 --remote-host 127.0.0.1 --remote-port 9999
```

| Tham số | Viết tắt | Mặc định | Mô tả |
| --- | --- | --- | --- |
| `--local-port` | `-l` | `8080` | Cổng proxy lắng nghe |
| `--remote-host` | `-r` | `127.0.0.1` | Host backend |
| `--remote-port` | `-p` | `9999` | Cổng backend |
| `--help` | `-h` | | In hướng dẫn |

Ví dụ trỏ tới một backend từ xa:

```bash
java -jar target/mini-gateway.jar -l 9000 -r example.com -p 443
```

## Kiểm thử thủ công

1. Khởi chạy backend giả lập:

   ```bash
   python -m http.server 9999 --bind 127.0.0.1
   ```

2. Chạy proxy:

   ```bash
   java -jar target/mini-gateway.jar
   ```

3. Gửi request qua proxy:

   ```bash
   curl -v http://127.0.0.1:8080/
   ```

   Kỳ vọng: HTTP 200 và nội dung directory listing của backend ở cổng 9999.

Kiểm tra thêm với HTTPS/TLS (proxy trong suốt với byte):

```bash
curl -vk https://127.0.0.1:8080/
```

## Kiểm thử tự động

```bash
mvn test
```

Các test end-to-end trong `ProxyServerTest` dựng backend echo thật và kiểm tra:

- request/response đi qua proxy đúng nguyên byte;
- payload lớn 8 MB (backpressure, không mất dữ liệu);
- client bị đóng khi backend không truy cập được;
- 20 client đồng thời không lẫn dữ liệu;
- parse tham số dòng lệnh và validate port.

## Cấu trúc mã nguồn

```
src/main/java/com/proxy/
├─ ProxyServer.java           # Bootstrap server, CLI, vòng đời EventLoopGroup
├─ ProxyFrontendHandler.java  # Client -> Backend, mở kết nối backend
└─ ProxyBackendHandler.java   # Backend -> Client, đóng kết nối an toàn
src/test/java/com/proxy/
└─ ProxyServerTest.java       # Test end-to-end + unit test CLI
```

## Ghi chú thiết kế

- **Không dùng `ChannelInboundHandlerAdapter` mặc định với AUTO_READ**: mỗi handler chủ động gọi `read()` sau khi dữ liệu đã được đẩy đi và đầu nhận còn ghi được. Đây là mô hình backpressure chuẩn của Netty.
- **Reference counting**: message được chuyển nguyên `ByteBuf` sang kênh đối diện qua `write()`, không copy; nếu kênh đích không còn active thì `release()` để tránh rò rỉ bộ nhớ.
- **Kết nối backend dùng chung EventLoop với client** (`inboundChannel.eventLoop()`), giảm context switch và số thread.
- **Không có timeout tự động**: proxy phù hợp cho kết nối dài hạn (SSH, WebSocket). Có thể bổ sung `ReadTimeoutHandler` nếu cần.

## Hạn chế / hướng mở rộng

- Chỉ hỗ trợ NIO transport; có thể thêm native epoll/kqueue để giảm syscall trên Linux/macOS.
- Chưa có TLS termination, access log, metrics, hay load balancing nhiều backend.
- Chưa giới hạn số kết nối đồng thời; có thể thêm `ChannelGroup` + semaphore nếu triển khai công khai.
