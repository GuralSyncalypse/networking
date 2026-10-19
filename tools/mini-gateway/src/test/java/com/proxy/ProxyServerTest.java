package com.proxy;

import io.netty.bootstrap.ServerBootstrap;
import io.netty.buffer.Unpooled;
import io.netty.channel.Channel;
import io.netty.channel.ChannelHandlerContext;
import io.netty.channel.ChannelInboundHandlerAdapter;
import io.netty.channel.ChannelInitializer;
import io.netty.channel.EventLoopGroup;
import io.netty.channel.nio.NioEventLoopGroup;
import io.netty.channel.socket.SocketChannel;
import io.netty.channel.socket.nio.NioServerSocketChannel;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.Random;
import java.util.concurrent.TimeUnit;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

/**
 * End-to-end tests: real TCP sockets against an embedded backend behind the proxy.
 */
public class ProxyServerTest {

    private EventLoopGroup backendBoss;
    private EventLoopGroup backendWorkers;
    private Channel backendChannel;
    private ProxyServer proxy;
    private Channel proxyChannel;

    @Before
    public void setUp() {
        proxy = new ProxyServer();
    }

    @After
    public void tearDown() throws Exception {
        if (proxyChannel != null) {
            proxyChannel.close().sync();
        }
        if (proxy != null) {
            proxy.shutdown();
        }
        if (backendChannel != null) {
            backendChannel.close().sync();
        }
        if (backendBoss != null) {
            backendBoss.shutdownGracefully(0, 2, TimeUnit.SECONDS).sync();
        }
        if (backendWorkers != null) {
            backendWorkers.shutdownGracefully(0, 2, TimeUnit.SECONDS).sync();
        }
    }

    @Test
    public void proxiesRequestToBackendAndBack() throws Exception {
        int backendPort = startEchoBackend();
        proxyChannel = proxy.bind(0, "127.0.0.1", backendPort);
        int proxyPort = ((java.net.InetSocketAddress) proxyChannel.localAddress()).getPort();

        try (Socket socket = connect(proxyPort)) {
            byte[] payload = "GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n".getBytes(StandardCharsets.US_ASCII);
            socket.getOutputStream().write(payload);
            socket.getOutputStream().flush();

            byte[] response = readExactly(socket.getInputStream(), payload.length);
            assertArrayEquals(payload, response);
        }
    }

    @Test
    public void proxiesLargePayloadWithBackpressure() throws Exception {
        int backendPort = startEchoBackend();
        proxyChannel = proxy.bind(0, "127.0.0.1", backendPort);
        int proxyPort = ((java.net.InetSocketAddress) proxyChannel.localAddress()).getPort();

        byte[] payload = new byte[8 * 1024 * 1024];
        new Random(42).nextBytes(payload);

        try (Socket socket = connect(proxyPort)) {
            Thread writer = new Thread(() -> {
                try {
                    OutputStream out = socket.getOutputStream();
                    out.write(payload);
                    out.flush();
                } catch (IOException e) {
                    throw new RuntimeException(e);
                }
            }, "test-writer");
            writer.start();

            byte[] response = readExactly(socket.getInputStream(), payload.length);
            writer.join(TimeUnit.SECONDS.toMillis(10));
            assertArrayEquals(payload, response);
        }
    }

    @Test
    public void closesClientWhenBackendIsUnreachable() throws Exception {
        int deadPort = findFreePort();
        proxyChannel = proxy.bind(0, "127.0.0.1", deadPort);
        int proxyPort = ((java.net.InetSocketAddress) proxyChannel.localAddress()).getPort();

        try (Socket socket = connect(proxyPort)) {
            socket.setSoTimeout(5000);
            int read = socket.getInputStream().read();
            assertEquals("expected EOF when backend is unreachable", -1, read);
        }
    }

    @Test
    public void multipleClientsAreIsolated() throws Exception {
        int backendPort = startEchoBackend();
        proxyChannel = proxy.bind(0, "127.0.0.1", backendPort);
        int proxyPort = ((java.net.InetSocketAddress) proxyChannel.localAddress()).getPort();

        for (int i = 0; i < 20; i++) {
            try (Socket socket = connect(proxyPort)) {
                byte[] payload = ("client-" + i).getBytes(StandardCharsets.US_ASCII);
                socket.getOutputStream().write(payload);
                socket.getOutputStream().flush();
                assertArrayEquals(payload, readExactly(socket.getInputStream(), payload.length));
            }
        }
    }

    @Test
    public void parsesCommandLineConfiguration() {
        ProxyServer.Config config = ProxyServer.Config.parse(
                new String[]{"-l", "9090", "-r", "example.com", "-p", "1234"});
        assertEquals(9090, config.localPort);
        assertEquals("example.com", config.remoteHost);
        assertEquals(1234, config.remotePort);

        ProxyServer.Config defaults = ProxyServer.Config.parse(new String[]{});
        assertEquals(ProxyServer.LOCAL_PORT, defaults.localPort);
        assertEquals(ProxyServer.REMOTE_HOST, defaults.remoteHost);
        assertEquals(ProxyServer.REMOTE_PORT, defaults.remotePort);
    }

    @Test(expected = IllegalArgumentException.class)
    public void rejectsUnknownArguments() {
        ProxyServer.Config.parse(new String[]{"--nope"});
    }

    @Test(expected = IllegalArgumentException.class)
    public void rejectsInvalidPorts() {
        ProxyServer.Config.parse(new String[]{"-l", "70000"});
    }

    private static Socket connect(int port) throws IOException {
        Socket socket = new Socket("127.0.0.1", port);
        socket.setTcpNoDelay(true);
        socket.setSoTimeout(15000);
        assertNotNull(socket);
        return socket;
    }

    private static byte[] readExactly(InputStream in, int length) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream(length);
        byte[] buffer = new byte[8192];
        int remaining = length;
        while (remaining > 0) {
            int read = in.read(buffer, 0, Math.min(buffer.length, remaining));
            if (read < 0) {
                throw new SocketTimeoutException("Unexpected EOF, " + remaining + " bytes missing");
            }
            out.write(buffer, 0, read);
            remaining -= read;
        }
        return out.toByteArray();
    }

    private static int findFreePort() throws IOException {
        try (java.net.ServerSocket socket = new java.net.ServerSocket(0)) {
            return socket.getLocalPort();
        }
    }

    /** Echo backend: every received buffer is written back unchanged. */
    private int startEchoBackend() {
        backendBoss = new NioEventLoopGroup(1);
        backendWorkers = new NioEventLoopGroup(1);
        try {
            backendChannel = new ServerBootstrap()
                    .group(backendBoss, backendWorkers)
                    .channel(NioServerSocketChannel.class)
                    .childHandler(new ChannelInitializer<SocketChannel>() {
                        @Override
                        protected void initChannel(SocketChannel ch) {
                            ch.pipeline().addLast(new ChannelInboundHandlerAdapter() {
                                @Override
                                public void channelRead(ChannelHandlerContext ctx, Object msg) {
                                    ctx.writeAndFlush(msg);
                                }
                            });
                        }
                    })
                    .bind(0)
                    .sync()
                    .channel();
            assertTrue(backendChannel.isActive());
            return ((java.net.InetSocketAddress) backendChannel.localAddress()).getPort();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }
}
