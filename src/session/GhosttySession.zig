//! Native Ghostty IO backend for Jim's authenticated local session service.
//! A reader consumes the ordered journal/live stream. A separate writer keeps
//! socket backpressure off Ghostty’s IO thread; no PTY relay, shell wrapper, or terminal multiplexer.
const Session = @This();
const std = @import("std");
const global = @import("../global.zig");
const termio = @import("../termio.zig");
const renderer = @import("../renderer.zig");
const terminal = @import("../terminal/main.zig");
const Allocator = std.mem.Allocator;
const ProcessInfo = @import("../pty.zig").ProcessInfo;
extern "c" fn jim_session_send(c_int, u32, ?[*]const u8, usize) c_int;
extern "c" fn jim_session_receive(c_int, *u32, [*]u8, usize) c_int;
extern "c" fn jim_session_shutdown(c_int) void;
extern "c" fn jim_session_close(c_int) void;

fd: c_int,
reader: ?std.Thread = null,
writer: ?std.Thread = null,
allocator: Allocator = undefined,
queue_mutex: std.Io.Mutex = .init,
queue_changed: std.Io.Condition = .init,
head: ?*Frame = null,
tail: ?*Frame = null,
closed: std.atomic.Value(bool) = .init(false),
ready: std.atomic.Value(bool) = .init(false),
stopping: std.atomic.Value(bool) = .init(false),
colors: [777]u8 = undefined,
cols: u16 = 80,
rows: u16 = 24,
width: u16 = 0,
height: u16 = 0,
const Frame = struct { next: ?*Frame = null, kind: u32, bytes: []u8 };
pub const ThreadData = struct {
    pub fn deinit(_: *ThreadData, _: Allocator) void {}
};
pub fn deinit(self: *Session) void {
    while (self.head) |frame| {
        self.head = frame.next;
        self.allocator.free(frame.bytes);
        self.allocator.destroy(frame);
    }
    jim_session_close(self.fd);
}
pub fn initTerminal(self: *Session, t: *terminal.Terminal) void {
    self.cols = t.cols;
    self.rows = t.rows;
    const defaults = [_]terminal.color.RGB{
        t.colors.foreground.default orelse .{ .r = 255, .g = 255, .b = 255 },
        t.colors.background.default orelse .{ .r = 0, .g = 0, .b = 0 },
        t.colors.cursor.default orelse t.colors.foreground.default orelse .{ .r = 255, .g = 255, .b = 255 },
    } ++ t.colors.palette.original;
    for (defaults, 0..) |rgb, i| {
        self.colors[i * 3] = rgb.r;
        self.colors[i * 3 + 1] = rgb.g;
        self.colors[i * 3 + 2] = rgb.b;
    }
}
fn sendSize(self: *Session, kind: u32) !void {
    var bytes: [8]u8 = undefined;
    std.mem.writeInt(u16, bytes[0..2], self.cols, .big);
    std.mem.writeInt(u16, bytes[2..4], self.rows, .big);
    std.mem.writeInt(u16, bytes[4..6], self.width, .big);
    std.mem.writeInt(u16, bytes[6..8], self.height, .big);
    try self.enqueue(kind, &bytes);
}
pub fn threadEnter(self: *Session, allocator: Allocator, io: *termio.Termio, td: *termio.Termio.ThreadData) !void {
    self.allocator = allocator;
    td.backend = .{ .session = .{} };
    io.terminal_stream.handler.session_render_only = true;
    io.terminal_stream.handler.session_replaying = true;
    try self.sendSize(3);
    self.writer = try std.Thread.spawn(.{}, writeLoop, .{self});
    errdefer {
        self.closeTransport();
        self.writer.?.join();
        self.writer = null;
    }
    self.reader = try std.Thread.spawn(.{}, readLoop, .{ self, io });
}
pub fn threadExit(self: *Session, _: *termio.Termio.ThreadData) void {
    self.stopping.store(true, .release);
    self.closeTransport();
    if (self.reader) |thread| thread.join();
    if (self.writer) |thread| thread.join();
    self.reader = null;
    self.writer = null;
}
pub fn focusGained(_: *Session, _: *termio.Termio.ThreadData, _: bool) !void {}
pub fn resize(self: *Session, grid: renderer.GridSize, pixels: renderer.ScreenSize) !void {
    self.cols = grid.columns;
    self.rows = grid.rows;
    self.width = @intCast(@min(pixels.width, 65535));
    self.height = @intCast(@min(pixels.height, 65535));
    if (self.reader != null) try self.sendSize(3);
}
pub fn queueWrite(self: *Session, _: Allocator, _: *termio.Termio.ThreadData, data: []const u8, linefeed: bool) !void {
    var buffer: [65536]u8 = undefined;
    var at: usize = 0;
    for (data) |byte| {
        if (at >= buffer.len - 1) {
            try self.enqueue(2, buffer[0..at]);
            at = 0;
        }
        buffer[at] = byte;
        at += 1;
        if (linefeed and byte == '\r') {
            buffer[at] = '\n';
            at += 1;
        }
    }
    if (at > 0) try self.enqueue(2, buffer[0..at]);
}
pub fn childExitedAbnormally(_: *Session, _: Allocator, _: *terminal.Terminal, _: u32, _: u64) !void {}
pub fn getProcessInfo(_: *Session, comptime info: ProcessInfo) ?ProcessInfo.Type(info) {
    return null;
}
fn closeTransport(self: *Session) void {
    self.closed.store(true, .release);
    jim_session_shutdown(self.fd);
    self.queue_mutex.lockUncancelable(global.io());
    self.queue_changed.signal(global.io());
    self.queue_mutex.unlock(global.io());
}
fn enqueue(self: *Session, kind: u32, bytes: []const u8) !void {
    const frame = try self.allocator.create(Frame);
    errdefer self.allocator.destroy(frame);
    frame.* = .{ .kind = kind, .bytes = try self.allocator.dupe(u8, bytes) };
    errdefer self.allocator.free(frame.bytes);
    self.queue_mutex.lockUncancelable(global.io());
    defer self.queue_mutex.unlock(global.io());
    if (self.closed.load(.acquire)) return error.SessionDisconnected;
    // Configure defaults before any input queued while the history was replaying.
    if (kind == 5) {
        frame.next = self.head;
        self.head = frame;
        if (self.tail == null) self.tail = frame;
    } else {
        if (self.tail) |tail| tail.next = frame else self.head = frame;
        self.tail = frame;
    }
    self.queue_changed.signal(global.io());
}
fn writeLoop(self: *Session) void {
    while (true) {
        self.queue_mutex.lockUncancelable(global.io());
        while (!self.closed.load(.acquire) and (self.head == null or !self.ready.load(.acquire))) {
            self.queue_changed.waitUncancelable(global.io(), &self.queue_mutex);
        }
        if (self.closed.load(.acquire)) {
            self.queue_mutex.unlock(global.io());
            return;
        }
        const frame = self.head.?;
        self.head = frame.next;
        if (self.head == null) self.tail = null;
        self.queue_mutex.unlock(global.io());
        const result = jim_session_send(self.fd, frame.kind, frame.bytes.ptr, frame.bytes.len);
        self.allocator.free(frame.bytes);
        self.allocator.destroy(frame);
        if (result < 0) {
            self.closeTransport();
            return;
        }
    }
}
fn readLoop(self: *Session, io: *termio.Termio) void {
    var buffer: [65536]u8 = undefined;
    var exited = false;
    while (true) {
        var kind: u32 = 0;
        const n = jim_session_receive(self.fd, &kind, &buffer, buffer.len);
        if (n < 0) break;
        const bytes = buffer[0..@intCast(n)];
        switch (kind) {
            16 => {
                io.processOutput(bytes);
                io.renderer_state.yieldToDemand(global.io());
            },
            3 => {
                if (bytes.len != 8) break;
                const cols = std.mem.readInt(u16, bytes[0..2], .big);
                const rows = std.mem.readInt(u16, bytes[2..4], .big);
                if (cols == 0 or rows == 0) break;
                io.renderer_state.mutex.lockUncancelable(global.io());
                io.terminal.resize(io.alloc, .{ .cols = cols, .rows = rows, .cell_size_px = .{
                    .width = std.mem.readInt(u16, bytes[4..6], .big) / cols,
                    .height = std.mem.readInt(u16, bytes[6..8], .big) / rows,
                } }) catch {};
                io.renderer_state.mutex.unlock(global.io());
            },
            20 => {
                io.renderer_state.mutex.lockUncancelable(global.io());
                io.terminal_stream.handler.reportPwd(bytes) catch {};
                io.renderer_state.mutex.unlock(global.io());
            },
            17 => {
                if (bytes.len == 1 and bytes[0] >= 1) {
                    self.enqueue(5, &self.colors) catch break;
                }
                io.renderer_state.mutex.lockUncancelable(global.io());
                io.terminal_stream.handler.session_replaying = false;
                io.renderer_state.mutex.unlock(global.io());
                self.queue_mutex.lockUncancelable(global.io());
                self.ready.store(true, .release);
                self.queue_changed.signal(global.io());
                self.queue_mutex.unlock(global.io());
                io.processOutput(if (exited) "\r\n[Session exited]\r\n" else "");
            },
            18 => {
                exited = true;
                if (self.ready.load(.acquire)) io.processOutput("\r\n[Session exited]\r\n");
            },
            19 => {
                io.processOutput("\r\n[Terminal service error]\r\n");
                break;
            },
            else => break,
        }
    }
    self.ready.store(false, .release);
    self.closeTransport();
    if (!exited and !self.stopping.load(.acquire)) {
        io.renderer_state.mutex.lockUncancelable(global.io());
        io.terminal_stream.handler.session_replaying = false;
        io.renderer_state.mutex.unlock(global.io());
        io.processOutput("\r\n[Disconnected. Use Terminal: Reconnect in the action palette.]\r\n");
    }
}
