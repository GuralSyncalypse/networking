package com.proxy;

import io.netty.bootstrap.ServerBootstrap;
import io.netty.channel.Channel;
import io.netty.channel.ChannelInitializer;
import io.netty.channel.ChannelOption;
import io.netty.channel.EventLoopGroup;
import io.netty.channel.nio.NioEventLoopGroup;
import io.netty.channel.socket.SocketChannel;
import io.netty.channel.socket.nio.NioServerSocketChannel;
import io.netty.util.concurrent.DefaultThreadFactory;

import java.util.concurrent.TimeUnit;
import java.util.logging.Logger;

/**
 * TCP reverse proxy (Layer 4) 1-1: client &lt;-&gt; proxy &lt;-&gt; backend.
 *
 * <p>Each accepted client connection gets its own outbound connection to the backend.
 * No protocol parsing is performed, so any TCP protocol (HTTP, TLS, SSH, ...) works.
 */
public final class ProxyServer {

    static final int LOCAL_PORT = 8080;
    static final String REMOTE_HOST = "127.0.0.1";
    static final int REMOTE_PORT = 9999;

    private static final Logger LOG = Logger.getLogger(ProxyServer.class.getName());

    private final EventLoopGroup bossGroup;
    private final EventLoopGroup workerGroup;

    public ProxyServer() {
        this(new NioEventLoopGroup(1, new DefaultThreadFactory("proxy-boss")),
             new NioEventLoopGroup(0, new DefaultThreadFactory("proxy-worker")));
    }

    ProxyServer(EventLoopGroup bossGroup, EventLoopGroup workerGroup) {
        this.bossGroup = bossGroup;
        this.workerGroup = workerGroup;
    }

    /**
     * Binds the proxy and starts accepting clients.
     *
     * @param localPort  port to listen on ({@code 0} picks a free port, useful for tests)
     * @param remoteHost backend host
     * @param remotePort backend port
     * @return the bound server channel
     */
    public Channel bind(int localPort, String remoteHost, int remotePort) throws InterruptedException {
        if (localPort < 0 || localPort > 65535) {
            throw new IllegalArgumentException("Invalid local port: " + localPort);
        }
        if (remotePort < 1 || remotePort > 65535) {
            throw new IllegalArgumentException("Invalid remote port: " + remotePort);
        }

        ServerBootstrap bootstrap = new ServerBootstrap();
        bootstrap.group(bossGroup, workerGroup)
                .channel(NioServerSocketChannel.class)
                .option(ChannelOption.SO_BACKLOG, 1024)
                .option(ChannelOption.SO_REUSEADDR, true)
                .childOption(ChannelOption.TCP_NODELAY, true)
                .childOption(ChannelOption.SO_KEEPALIVE, true)
                // Backpressure is driven explicitly by the relay handlers.
                .childOption(ChannelOption.AUTO_READ, false)
                .childHandler(new ChannelInitializer<SocketChannel>() {
                    @Override
                    protected void initChannel(SocketChannel ch) {
                        ch.pipeline().addLast(new ProxyFrontendHandler(remoteHost, remotePort));
                    }
                });

        Channel channel = bootstrap.bind(localPort).sync().channel();
        int boundPort = ((java.net.InetSocketAddress) channel.localAddress()).getPort();
        LOG.info(() -> "Proxy listening on port " + boundPort
                + " -> " + remoteHost + ":" + remotePort);
        return channel;
    }

    /** Releases all event loop threads. Safe to call more than once. */
    public void shutdown() {
        bossGroup.shutdownGracefully(0, 5, TimeUnit.SECONDS);
        workerGroup.shutdownGracefully(0, 5, TimeUnit.SECONDS);
    }

    public static void main(String[] args) throws Exception {
        Config config;
        try {
            config = Config.parse(args);
        } catch (IllegalArgumentException e) {
            System.err.println("Error: " + e.getMessage());
            System.err.println();
            printUsage();
            System.exit(2);
            return;
        }
        if (config.help) {
            printUsage();
            return;
        }

        ProxyServer proxy = new ProxyServer();
        try {
            Channel serverChannel = proxy.bind(config.localPort, config.remoteHost, config.remotePort);
            Runtime.getRuntime().addShutdownHook(new Thread(() -> {
                LOG.info("Shutting down...");
                serverChannel.close();
                proxy.shutdown();
            }, "proxy-shutdown"));
            serverChannel.closeFuture().sync();
        } finally {
            proxy.shutdown();
        }
    }

    private static void printUsage() {
        System.out.println("Usage: java -jar mini-gateway.jar [options]");
        System.out.println();
        System.out.println("Options:");
        System.out.println("  -l, --local-port <port>    Port to listen on (default: " + LOCAL_PORT + ")");
        System.out.println("  -r, --remote-host <host>   Backend host (default: " + REMOTE_HOST + ")");
        System.out.println("  -p, --remote-port <port>   Backend port (default: " + REMOTE_PORT + ")");
        System.out.println("  -h, --help                 Show this help");
        System.out.println();
        System.out.println("Example: java -jar mini-gateway.jar -l 8080 -r 127.0.0.1 -p 9999");
    }

    /** Command line configuration. */
    static final class Config {
        final int localPort;
        final String remoteHost;
        final int remotePort;
        final boolean help;

        private Config(int localPort, String remoteHost, int remotePort, boolean help) {
            this.localPort = localPort;
            this.remoteHost = remoteHost;
            this.remotePort = remotePort;
            this.help = help;
        }

        static Config parse(String[] args) {
            int localPort = LOCAL_PORT;
            String remoteHost = REMOTE_HOST;
            int remotePort = REMOTE_PORT;
            boolean help = false;

            for (int i = 0; i < args.length; i++) {
                String arg = args[i];
                switch (arg) {
                    case "-l":
                    case "--local-port":
                        localPort = parsePort(nextValue(args, ++i, arg), arg);
                        break;
                    case "-p":
                    case "--remote-port":
                        remotePort = parsePort(nextValue(args, ++i, arg), arg);
                        break;
                    case "-r":
                    case "--remote-host":
                        remoteHost = nextValue(args, ++i, arg);
                        break;
                    case "-h":
                    case "--help":
                        help = true;
                        break;
                    default:
                        throw new IllegalArgumentException("Unknown argument: " + arg);
                }
            }

            if (remoteHost.isEmpty()) {
                throw new IllegalArgumentException("Remote host must not be empty");
            }
            return new Config(localPort, remoteHost, remotePort, help);
        }

        private static String nextValue(String[] args, int index, String option) {
            if (index >= args.length) {
                throw new IllegalArgumentException("Missing value for " + option);
            }
            return args[index];
        }

        private static int parsePort(String value, String option) {
            try {
                int port = Integer.parseInt(value);
                if (port < 0 || port > 65535) {
                    throw new IllegalArgumentException("Port out of range for " + option + ": " + value);
                }
                return port;
            } catch (NumberFormatException e) {
                throw new IllegalArgumentException("Invalid port for " + option + ": " + value);
            }
        }
    }
}
