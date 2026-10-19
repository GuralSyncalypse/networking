package com.proxy;

import io.netty.buffer.Unpooled;
import io.netty.channel.Channel;
import io.netty.channel.ChannelFutureListener;
import io.netty.channel.ChannelHandlerContext;
import io.netty.channel.ChannelInboundHandlerAdapter;
import io.netty.util.ReferenceCountUtil;

import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Backend side of the relay: forwards bytes received from the backend back to the client.
 */
public class ProxyBackendHandler extends ChannelInboundHandlerAdapter {

    private static final Logger LOG = Logger.getLogger(ProxyBackendHandler.class.getName());

    private final Channel inboundChannel;

    public ProxyBackendHandler(Channel inboundChannel) {
        this.inboundChannel = inboundChannel;
    }

    @Override
    public void channelActive(ChannelHandlerContext ctx) {
        ctx.read();
    }

    @Override
    public void channelRead(ChannelHandlerContext ctx, Object msg) {
        if (!inboundChannel.isActive()) {
            ReferenceCountUtil.release(msg);
            ctx.close();
            return;
        }
        inboundChannel.write(msg).addListener((ChannelFutureListener) future -> {
            if (!future.isSuccess()) {
                LOG.log(Level.FINE, "Write to client failed", future.cause());
                ctx.close();
                inboundChannel.close();
            }
        });
    }

    @Override
    public void channelReadComplete(ChannelHandlerContext ctx) {
        inboundChannel.flush();
        if (inboundChannel.isActive() && inboundChannel.isWritable() && ctx.channel().isActive()) {
            ctx.read();
        }
    }

    @Override
    public void exceptionCaught(ChannelHandlerContext ctx, Throwable cause) {
        LOG.log(Level.FINE, "Backend connection error", cause);
        ctx.close();
    }

    @Override
    public void channelInactive(ChannelHandlerContext ctx) {
        closeOnFlush(inboundChannel);
    }

    /** Flushes anything already queued, then closes the channel. */
    static void closeOnFlush(Channel ch) {
        if (ch != null && ch.isActive()) {
            ch.writeAndFlush(Unpooled.EMPTY_BUFFER).addListener(ChannelFutureListener.CLOSE);
        }
    }
}
