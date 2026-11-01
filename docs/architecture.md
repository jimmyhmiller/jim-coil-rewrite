# Jim Coil shell

The current application is macOS-only. Coil owns the window, project canvases,
pane lifetimes, input routing, and live theme loading. Jim’s private session service owns each PTY and a headless Ghostty VT model.
The embedded Ghostty frontend owns shaping and the Metal/IOSurface renderer. AppKit and Core Animation
compose those surfaces into movable panes and project faces without CPU readback.

`canvas_model.coil` contains camera projection, gesture math, and origin feedback.
`canvas.coil` owns dynamic collections of stable heap-allocated panes. The canvas
uses top-left coordinates, with the same top-left wall as Jim; it has no right or
bottom wall. Native pane frames are projected from world coordinates. Pane bounds
remain in world units, preserving native mouse/IME coordinate conversion through
zoom. Moving a pane or camera changes its position without resizing its terminal.
Zoom updates content scale; pane resize updates PTY dimensions. Offscreen panes
retain their sessions and suspend Ghostty drawing.

Each dynamic project has its own camera, pane collection, z-order, focus, and
working directory. Profiles reference global project identities and store hidden
projects plus an active project. They never duplicate canvases or terminal sessions.
Normal selection swaps flat views immediately; cube transforms are opt-in.
Nested canvases and the rest of Jim's pane kinds remain migration work.

The origin indicators match `jim-app/src/canvas.rs`: screen-space edge gradients
are behind panes, and their strength measures how far the origin lies beyond that
viewport edge in world units. Width, saturation distance, strength, and shadow
color are live theme values. Main surfaces and pane chrome also have explicit
tokens. Ghostty's own palette/configuration lives in `config/ghostty`.

The theme is data, not code: `config/theme` is an s-expression that `jim.theme`
decodes into its `Theme` with coil.serde, refusing unknown and missing values,
and validates field by field. Jim reads it on the main thread when it changes
or on ⌘R; a file that does not decode, or a value out of range, preserves the
last good theme.

Layout persistence stores project cameras, pane rectangles, z-order, and focus in
`~/Library/Application Support/JimCoil/layout.json`, using an atomic replacement.
It is separate from original Jim's data. Version 2 adds project/profile metadata
and stable terminal UUIDs. Version 1 migration preserves the earlier rewrite's
layouts. Invalid saved documents are rejected without overwriting them. Session
connection failures retain recoverable panes rather than deleting saved metadata.

The Ghostty dependency is pinned to v1.4.0
(`83fb95624b0439ee660c2679b43b38c8b63769cd`). Its C header is retained under
`vendor/`, and the used ABI subset has compile-time checks in Coil. The session
service declares the libghostty-vt functions it calls in `src/session/server.coil`;
those are checked against `include/ghostty/vt` by hand when the pin moves. The
Objective-C messaging and animation modules come from the existing Coil GPU UI
experiment and are maintained in `src/` as Jim modules; see
[source origins](PROVENANCE.md).

## Session ownership and transport

`src/session/server.coil` is a small per-terminal private service, and
`src/session/transport.coil` owns the shared JIM1 framing and connection API. A same-user,
mode-0700 socket directory and peer-UID checks protect its Unix connection. A file
lock serializes creation of a session UUID. The service owns the PTY child,
terminal query responses, foreground cwd discovery, and an anonymous disk journal.
The launcher uses posix_spawn; the detached service forks the shell before adding
any renderer threads. Closing the GUI does not signal the child. Explicit close
sends a control frame, then the service terminates the shell/foreground process
group and removes its socket. Exited shells remain attachable for inspection.

The JIM1 protocol has a 12-byte big-endian magic/type/length header and 64-KiB
payload limit. Attach, input, resize, and kill requests are distinct from output,
ready, exit, error, and cwd records. A negotiated color-configuration message
keeps the headless core’s default foreground/background/cursor/palette queries
aligned with the renderer. Cwd is out-of-band metadata so it cannot split
an unfinished escape sequence. Reads and writes handle partial frames. A bounded
input queue applies backpressure; output is journaled to disk and streamed without
holding the entire history in RAM. Slow/disconnected clients do not stop PTY reads.

`GhosttySession.zig` adds a native Ghostty IO backend connected directly to this
socket. It replays output and terminal-size changes in order, then processes live
records. The daemon's headless core answers terminal requests even when no GUI is
attached. The frontend suppresses duplicate terminal responses, replayed clipboard
operations, bells, and desktop notifications. A dedicated writer drains queued input, so a shell that stops reading cannot
block Ghostty’s IO thread. Input typed during replay is queued until attachment
is ready. Renderer shutdown shuts down the socket, joins both transport threads,
and frees pending writes; daemon shutdown is a separate explicit action.
Replay is exact for the recorded stream, not a model snapshot. Journal compaction,
reboot recovery, and graphics referencing vanished files require further work.

Coil exports AppKit and Ghostty callbacks with `export-c`; `fnptr-of` selects the
generated C ABI entry point and marshals by-value native structures without a
handwritten adapter. Direct Coil calls retain Coil's internal struct-reference
convention. All objects retained by AppKit have explicit owners;
unparented document views remain owned until NSScrollView takes ownership.

The dependency extension is reproducible through
`scripts/ghostty/session-backend.py`; it only patches the project-local pinned
Ghostty source. `scripts/ghostty/pinned.py` builds both the embedded renderer and headless
VT library on demand, as the package's `ghostty` and `ghostty-vt` native
dependencies; the session service is the `session` executable artifact and links only
the VT library. The separately compiled configuration has its own Coil package so it
cannot load another copy of Ghostty into the process.
