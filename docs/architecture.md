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
terminal query responses, foreground cwd discovery, and an in-memory journal.
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
input queue applies backpressure; output is journaled in memory, never on disk, and streamed. Slow/disconnected clients do not stop PTY reads.

The journal keeps the newest 64 MiB of frames, original Jim's limit. Trimmed frames
leave from the front on a frame boundary and fresh pages replace theirs, returning the memory,
so offsets never move and nothing is copied. Frames a client has yet to read are kept
until it falls 256 MiB behind, when it loses its connection instead. Replay after a
trim starts with the size and directory the trimmed frames established, and ends with
the input modes and Kitty keyboard flags the session's core reports as set, so keys
and mice keep working. It may begin mid-sequence, as original Jim's replay can.

`GhosttySession.zig` adds a native Ghostty IO backend connected directly to this
socket. It replays output and terminal-size changes in order, then processes live
records. The daemon's headless core answers terminal requests even when no GUI is
attached. The frontend suppresses duplicate terminal responses, replayed clipboard
operations, bells, and desktop notifications. A dedicated writer drains queued input, so a shell that stops reading cannot
block Ghostty’s IO thread. Input typed during replay is queued until attachment
is ready. Renderer shutdown shuts down the socket, joins both transport threads,
and frees pending writes; daemon shutdown is a separate explicit action.
The renderer holds its frames until replay ends, so history is not seen scrolling past.
Attaching leaves the terminal's size alone: the client reports only its newest size,
once replay ends, so a running TUI is not resized unless the size really changed.
Replay is exact for the retained stream, not a model snapshot. Reboot recovery and
graphics referencing vanished files require further work.

## Previewing terminal images

Clicking an image a program drew in a terminal picks it, with an outline, as selecting
a file does in Finder. Space then opens Quick Look, and Space or Escape closes it. Any
other key drops the pick and goes to the terminal, as does the image leaving the screen,
so Space means preview only straight after a click and typing is never eaten.

Programs often send only a thumbnail and print where the full image is. Codex sends
52x96 of a 921x1708 file. `image_original.coil` reads the text around the image for
image paths and file URLs, rejoining ones the program wrapped, and accepts a file only
if it has the thumbnail's shape and, scaled down to it, differs by at most 10 of 255 per
channel. Codex's original measured 3.9 and the closest other image, an earlier version of
the same page, 20.5. With no match Quick Look shows the terminal's own pixels, from a
temporary copy deleted on close. Relative paths and paths with bare spaces are not found.

The lookups are additions to the Ghostty patch. Placements come from the renderer's own
list under its draw mutex, so a hit is exactly what was drawn. A private `RenderState`
would consume the terminal's dirty flags from under the renderer.

## Adopting original Jim's daemons

`jim-session --adopt UPSTREAM SOCKET CWD RESOURCES` serves the JIM1 protocol as usual,
with a connection to an original Jim daemon where the PTY would be, so nothing above
the service changes. It speaks that daemon's length-prefixed bincode protocol and owns
the terminal core that answers queries, since the daemon has none. It connects before
detaching, so the launcher's exit status can report a daemon that is gone.

A daemon serves only its newest client and original Jim reconnects when dropped, so
sharing one would have the two apps replaying history at each other forever. The app
therefore refuses to adopt while `~/.jim/socket` answers, and a service that loses its
connection stops and never reconnects. Connecting to a daemon drops its client, so
nothing connects to one while original Jim is open.

Clients are held off until the daemon's replay is journaled, so all of it reaches
them as replay and its bells, notifications and clipboard writes stay suppressed.
Queries in that history go unanswered. The shell's pid comes from the socket's peer
and `proc_listchildpids`; its controlling terminal gives the current size, so attaching
causes no SIGWINCH and history replays at its width, and its foreground group drives
cwd reporting. The attach placeholder size is not applied to an adopted terminal.

An adopted pane stores the daemon's number as `original` beside its session UUID, to
adopt again if the service stops. Explicit close sends the daemon Kill, directly if
the service has stopped, unless original Jim is open and so owns the terminal again.

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

## When something fails

Terminal history never touches the disk, so a full disk can't pause or end a terminal.
Failures that cost only a resize or some input are logged and survived. What still ends a
service: poll failing, an adopted daemon's connection failing, and being told to.

`~/.jim-coil/sessions/events.log` records each lifecycle event with its time and reason.
A service writes it from the binary it started with, so a running one logs nothing new.

## Dictation

⌘⇧T starts hands-free dictation into whatever has the keyboard, and Escape or ⌘⇧T stops
it. Return also stops it, and reaches the target once the last words have landed, except
in the palette, where it would run whichever action they left selected. AudioQueue delivers
16 kHz floats to a worker thread (`src/dictation.coil`), which cuts them into phrases and
decodes them on the Phonon server shared with original Jim (`src/dictation_core.coil`).
Each buffer also sets the pill's level meter.

A terminal gets a revision as DEL × n then a paste of what changed, sent only while
`ghostty_surface_revisable` says the child is a line editor. Otherwise the transcript stays
on the pill and lands as one paste at the end. Typing during dictation ends it.

Everything else that takes text is AppKit's: the palette, a project being renamed, a
widget's input or text area. All go through the window's first responder, an `NSTextView`,
which for a field is the one field editor they share. A write replaces the text it last
wrote, through `insertText:replacementRange:` so listeners hear it. It stops writing if that
text has changed, so an edit is never overwritten, or if the target has lost the keyboard.

If Phonon isn't installed, the first ⌘⇧T runs original Jim's installer, compiled in, on a
background thread and doesn't open the microphone. The pill says when it's ready. It uses
original Jim's files and lock in `~/.jim/phonon`, and the lock is inherited by the script,
so an app that quits mid-install leaves it running and the next one waits for it. Any
finished install counts, whichever pin, so the two apps can't reinstall over each other.
