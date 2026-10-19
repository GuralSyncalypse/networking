package com.proxy;

import io.netty.bootstrap.Bootstrap;
import io.netty.channel.Channel;
import io.netty.channel.ChannelFuture;
import io.netty.channel.ChannelFutureListener;
import io.netty.channel.ChannelHandlerContext;
import io.netty.channel.ChannelInboundHandlerAdapter;
import io.netty.channel.ChannelInitializer;
import io.netty.channel.ChannelOption;
import io.netty.channel.socket.SocketChannel;
import io.netty.channel.socket.nio.NioSocketChannel;
import io.netty.util.ReferenceCountUtil;

import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Client side of the relay: accepts bytes from the client and forwards them to the backend.
 * A dedicated backend connection is opened for every accepted client connection.
 */
public class ProxyFrontendHandler extends ChannelInboundHandlerAdapter {

    private static final Logger LOG = Logger.getLogger(ProxyFrontendHandler.class.getName());

    private final String remoteHost;
    private final int remotePort;

    /** Set once the backend connection attempt has been initiated. */
    private volatile Channel outboundChannel;

    public ProxyFrontendHandler(String remoteHost, int remotePort) {
        this.remoteHost = remoteHost;
        this.remotePort = remotePort;
    }

    @Override
    public void channelActive(ChannelHandlerContext ctx) {
        final Channel inboundChannel = ctx.channel();

        Bootstrap b = new Bootstrap();
        b.group(inboundChannel.eventLoop())
                .channel(NioSocketChannel.class)
                .option(ChannelOption.TCP_NODELAY, true)
                .option(ChannelOption.SO_KEEPALIVE, true)
                .option(ChannelOption.AUTO_READ, false)
                .handler(new ChannelInitializer<SocketChannel>() {
                    @Override
                    protected void initChannel(SocketChannel ch) {
                        ch.pipeline().addLast(new ProxyBackendHandler(inboundChannel));
                    }
                });

        ChannelFuture connectFuture = b.connect(remoteHost, remotePort);
        outboundChannel = connectFuture.channel();

        connectFuture.addListener((ChannelFutureListener) future -> {
            if (!future.isSuccess()) {
                LOG.log(Level.WARNING, "Cannot connect to backend " + remoteHost + ":" + remotePort, future.cause());
                inboundChannel.close();
                return;
            }

            Channel outbound = future.channel();
            // Resume reading from the client whenever the backend becomes writable again.
            outbound.pipeline().addFirst("frontend-writability", new ChannelInboundHandlerAdapter() {
                @Override
                public void channelWritabilityChanged(ChannelHandlerContext outCtx) {
                    if (outbound.isWritable() && inboundChannel.isActive()) {
                        inboundChannel.read();
                    }
                    outCtx.fireChannelWritabilityChanged();
                }
            });

            inboundChannel.read();
        });
    }

    @Override
    public void channelRead(ChannelHandlerContext ctx, Object msg) {
        Channel outbound = outboundChannel;
        if (outbound != null && outbound.isActive()) {
            outbound.write(msg).addListener((ChannelFutureListener) future -> {
                if (!future.isSuccess()) {
                    LOG.log(Level.FINE, "Write to backend failed", future.cause());
                    closeBoth(ctx.channel(), outbound);
                }
            });
        } else {
            ReferenceCountUtil.release(msg);
            closeBoth(ctx.channel(), outbound);
        }
    }

    @Override
    public void channelReadComplete(ChannelHandlerContext ctx) {
        Channel outbound = outboundChannel;
        if (outbound == null) {
            return;
        }
        outbound.flush();
        if (outbound.isActive() && outbound.isWritable() && ctx.channel().isActive()) {
            ctx.read();
        }
    }

    @Override
    public void channelWritabilityChanged(ChannelHandlerContext ctx) {
        Channel outbound = outboundChannel;
        // Responses for this client are backed up; stop pulling data from the backend.
        if (ctx.channel().isWritable() && outbound != null && outbound.isActive()) {
            outbound.read();
        }
        ctx.fireChannelWritabilityChanged();
    }

    @Override
    public void exceptionCaught(ChannelHandlerContext ctx, Throwable cause) {
        LOG.log(Level.FINE, "Client connection error", cause);
        closeBoth(ctx.channel(), outboundChannel);
    }

    @Override
    public void channelInactive(ChannelHandlerContext ctx) {
        ProxyBackendHandler.closeOnFlush(outboundChannel);
    }

    private static void closeBoth(Channel inbound, Channel outbound) {
        if (inbound != null) {
            inbound.close();
        }
        if (outbound != null) {
            outbound.close();
        }
    }
}
