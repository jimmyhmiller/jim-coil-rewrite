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

## Pinned panes and the pane menu

A canvas's pane array is its z-order, back to front, and pinned panes are its first
entries, so no pane is ever raised behind one. A pane's host view is a `JimPaneView`
whose `hitTest:` answers NSView's, except that a pinned pane returns nil unless the
point is on a widget element that takes clicks (`widget-view/reacts-at?`) or inside
one of its text fields. AppKit then routes clicks, scrolls and drops to whatever is
behind it. The canvas's own gestures skip pinned panes the same way.

`src/pane_menu.coil` builds the pane menu as a native NSMenu with a project submenu.
What was picked waits for the main loop and names its pane by project and pane id,
because the pane can close while the menu is open. Moving a pane between projects
reparents its view onto the other canvas and gives it that canvas's next id. Its
terminal keeps its session, and both layouts are marked dirty. jimc's `pane pin`,
`pane unpin` and `pane move-to` do the same things.

## Session ownership and transport

`src/session/server.coil` is a small per-terminal private service, and
`src/session/transport.coil` owns the shared JIM1 framing and connection API. A same-user,
mode-0700 socket directory and peer-UID checks protect its Unix connection. A file
lock serializes creation of a session UUID. The service owns the PTY child,
terminal query responses, foreground cwd discovery, and an in-memory journal.
The detached service forks the shell before adding any renderer threads. Closing the
GUI does not signal the child. Explicit close sends a control frame, then the service
terminates the shell/foreground process group and removes its socket. Exited shells
remain attachable for inspection.

A force quit, from the Dock, Cmd-Opt-Esc or the low-memory dialog, sends SIGTERM to every
process in the app's coalition, and a child stays in its parent's coalition however it
detaches. So the launcher runs as a launchd job, which gives it and the service a coalition
of their own. `src/session/transport.coil` writes the arguments and environment to a private
request file, since launchd passes neither, boots a job running `jim-session --launched
REQUEST`, waits for the launcher's wait status in `REQUEST.status`, and boots the job out.
The job outlives none of this, and a launch launchd can't do fails rather than falling back
to a direct spawn. Each service logs its coalition in `service-start`.

macOS attributes a shell's use of protected folders to the service, so the service lives in
the bundle, at `Contents/MacOS/jim-session`, signed with the app's identity, and shares the
app's privacy permissions. Unbundled, it is a separate subject, and if it is under
`~/Documents` it waits on a privacy prompt before `main` runs. `coil run` starts it that way
from `build/`. The tests run a copy from `/tmp` with a clean environment for the same reason.
Only the Dock and loginwindow hold the entitlement for a force quit, so no test can run one:
`tests/session_launch_test.coil` checks the coalition, and a force quit is checked by hand.

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

## Asking for attention

A terminal asks for attention by ringing the bell or by sending a desktop notification,
and Ghostty reports either as a surface action. Each adds to the project's count, unless
the app is active with that project selected. Being there clears it. A project's count
shows in its sidebar row, capped at `99+`, and the total of all projects on the Dock icon,
including projects hidden in the current profile. Counts are not saved, and replayed
history rings nothing, so a restart starts them at zero. Jim posts no system notifications.

Agents need no event stream of their own for this. Claude Code rings or notifies through
its `preferredNotifChannel`, and Codex through its `notification_method = "bel"` setting;
`~/.claude/settings.json` also rings from a `Stop` hook. Unlike original Jim, nothing here
reads Claude's hook events from `~/.claude/bus.sock`. Those events reach Jim only as the
bell they ring, so a Claude configured with `notifications_disabled` and no `Stop` hook
stays silent.

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

## The diff wall

`widgets/diffwall.coil` lays a diff across a project's canvas, a port of original Jim's
`jimctl git diff-wall`, whose patch files never changed once written. Here the index pane
is the only thing that talks to git and `jimctl review`, however many tiles there are. It
runs one diff, divides it on a worker task (`src/widget_kit/wall.coil`) and writes each
tile's patch and the threads under `$TMPDIR/jim-diff-wall/ID`, only where the bytes differ.
It then emits one `diffwall.changed` naming the tiles that changed, so unchanged tiles read
nothing. A tile is the `diff` widget with its source set to `tile`; it watches nothing and
spawns only to write a comment.

Those files are a cache. A restart re-runs the diff and rewrites any that are gone, and
tiles wait until told. Slots live in the index's saved state, which is why a restart opens
nothing twice and a tile someone closed stays closed.

A wall is only possible because panes of a widget share compiled code. `src/widgets.coil`
keeps one `Source` per file with the `Generation`s compiled from it, reference counted by
the widgets running each. One JIT session is hundreds of megabytes, and a wall can have 150
panes. Panes placed by a widget (`open-widget-at!`) never take the keyboard, and closing a
pane other than the focused one leaves focus alone, since either can happen mid-comment.

## Control from outside

`jimc` (`src/jimc/main.coil`) spells a command line as one JSON request, sends it and
prints the reply. It knows nothing else, and links no frameworks. What a request means is
in `src/main.coil`, under the `jimc` heading, since commands need the shell's state.

`src/remote.coil` serves the socket on the main thread. Original Jim reads requests on
worker threads and queues them, because a client that never finished could otherwise wedge
it. Here nothing can block: every socket is non-blocking and a client that goes quiet is
dropped after five seconds. A command therefore runs between events, in the same place as
a palette action, and can touch AppKit without a queue or a lock. A `CFFileDescriptor` per
socket tells the run loop when one is ready, only so it can post the event that ends the
loop's wait. Without it a request would wait up to 200 ms for the next pass.

The socket's directory must be private to the user, and each connection's peer UID is
checked as well. Something answering at the path means another app has it, which is left
alone; a socket file nothing answers on was left by a crash, and is replaced.

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
