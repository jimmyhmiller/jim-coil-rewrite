# Jim in Coil

A native macOS shell for the Jim rewrite: Ghostty terminal panes on independent
project canvases, a live theme, and a composited workspace cube.

## Run

Requires Coil, Xcode's Metal toolchain, and a local signing identity. Jim's
session service and transport are Coil; Zig is used only to build the pinned
Ghostty dependency (v1.4.0) and its project-local backend extension. The build
downloads the Zig that Ghostty needs (0.17.0, checked against its digest) into
`build/deps`, so the Zig on PATH is left alone. On a fresh checkout:

```sh
xcodebuild -downloadComponent MetalToolchain
./scripts/dev-restart.sh
```

Pinned Ghostty is a Coil native dependency (`scripts/ghostty/link-flags.py`),
so every `coil build`, `coil run`, and `coil test` rebuilds its libraries when
the pin, patch, backend extension, or Zig version changes.
`scripts/prepare-ghostty.py` does the same step on its own. The terminal session
service is the package's `session` executable artifact: a bare `coil build` or
`coil run` also produces `build/jim-session`, linked against the Ghostty VT library.
`GHOSTTY_SOURCE=/path/to/pinned/ghostty` can reuse an existing source checkout.
Ghostty is built without its Sentry crash reporter, which would claim Jim's
crashes as Ghostty's. Its version is given as the pinned revision; left alone,
Ghostty's build reads this repository's git.
The build checks its embedding header against the pinned header. The development
app is `build/JimCoil.app`; it resolves this checkout's configuration and resources.
The build uses the existing `TerminalBevy Local Signing` identity; set
`JIM_SIGN_IDENTITY` to choose another installed identity. Signing preserves the
app identity across rebuilds. macOS may ask for Documents-folder access at first launch.

### Release

`python3 scripts/release.py` builds a self-contained `build/dist/JimCoil.app`
and `build/dist/JimCoil-<commit>-macos-arm64.zip` from a clean tree. It runs
on an Apple silicon Mac without this checkout, Coil, or LLVM: Jim is built with
`jit = "tpde"` (`Coil.toml`), so its widget JIT links no LLVM, and nothing it
does at run time needs a compiler.

- `Contents/Resources/coil` holds the standard library of the `coil` that built
  Jim, which widgets compile against. The rest of the installed toolchain is
  left out; `scripts/release.py` says why.
- `Contents/Resources/root` holds what Jim reads at run time: a manifest for
  widget imports, `src/`, `widgets/`, `config/`, `jimc`, and
  Ghostty's resources. `Contents/MacOS` holds `jim-session` beside the app.

The release never writes into its bundle. On first launch, and whenever the
release changes, it copies its root to
`~/Library/Application Support/JimCoil/root` and works there
(`src/runtime.coil`). Widgets and `config/` in that copy are yours to edit, so
a newer release adds only the files they lack. Layouts and terminal sessions
are shared with the development app. The release has its own bundle
identifier, so macOS asks for its permissions separately. It is signed ad hoc
(set `JIM_RELEASE_SIGN_IDENTITY` to choose an identity) and not notarized: on
another Mac, clear the download's quarantine first with
`xattr -dr com.apple.quarantine JimCoil.app`.

## Controls

Canvas controls follow the original Jim handler:

| Input | Behavior |
|---|---|
| ⌘ + scroll | Pan the canvas |
| ⌘⌥ + scroll | Zoom at the pointer |
| Pinch | Zoom at the pointer, with Jim's 3.5 gain |
| Middle drag or Space + left drag | Pan |
| Plain / Option-only scroll | Scroll the pane under the pointer |
| ⌘= / ⌘− | Zoom at window center |
| ⌘0 | Reset zoom to 1×, retaining pan |
| ⌘⇧0 | Reset pan and zoom |
| ⌘⇧Z | Toggle zoom |
| Double-click a pane away from 1× | Jump to 1× with a 24-point margin |
| Drag pane header | Move pane |
| Drag any pane edge or corner | Resize pane |
| ⌘T / ⌘N / New terminal | Add a terminal pane |
| ⌘⇧P | Search actions; arrows or pointer select, Return or click runs |
| ⌘W / pane × | Close focused / selected pane |
| Right-click (or Control-click) a pane header | Pane menu: Pin to background, Move to project, Close |
| Right-click a pinned pane anywhere | Pane menu: Unpin, Move to project, Close |
| ⌘1–4 | Switch among the first four visible projects |
| ⌘⇧\ / All workspaces | Toggle cube; drag spins and tilts, scroll zooms, click or Return enters, Esc returns |
| ⌘⇧E | Toggle Exposé; click a pane to focus it, Esc returns |

Default empty-canvas left drag does not pan, matching Jim. Zoom spans 0.2×–4×.
Pan stops at the top-left origin; the canvas extends to the right and down.
Directional edge shading points back toward the origin as it leaves the viewport.
The Fit all panes button is an additional way to find the project's panes.

**The cube.** ⌘⇧\ pulls back from the project into a ring with one face per
visible project, after Jim's Compiz-style cube (`jim-app/src/cube.rs`): the
camera stands back and above the ring, under a night sky with twinkling stars,
and the ring is reflected in the floor. Each face shows its project's whole
layout scaled to fit, its panes floating off the face. A drag throws the ring,
which coasts to a stop; scrolling moves the camera in and out; clicking a face
dives into it. Dragging up and down tips the ring as Compiz's cube did under
XGL (its first `rotate.c`): about its center, around the screen's horizontal
axis however the ring is turned, up to 100° either way. Released, it springs
back level on Compiz's own spring. Tipped, the ring rises to rest its lowest
corner on the floor, as Compiz's cube reflection did by default. Every face is drawn, turned away or not; depth decides what
shows. The sky and floor are views beside the cube's stage rather than
inside it: Core Animation depth-tests layers under one perspective, and an
opaque sky at depth 0 would hide the ring behind it.

**Pinned panes.** As in Jim, a pane pinned to the background sits behind every
other pane, loses its header and background, and never takes the keyboard. Clicks,
scrolling and drops pass through it, except onto a widget's buttons, links and text
fields. Exposé leaves it where it is, and the cube lays it flat on its face. Pinning is
saved with the layout. "Move to project" lists the projects the profile shows; the
pane keeps its place on the canvas, its pin and its shell.

**Exposé.** ⌘⇧E spreads every pane of the project into a grid, after Jim's
(`jim-app/src/expose.rs`): each goes to the cell nearest where it lies, shrunk
to fit and never resized, so terminals and widgets keep their layout. Hovering
lifts a pane; clicking it, Esc or ⌘⇧E brings the panes home, and a clicked pane
is focused and raised. The camera moves only when that pane would be entirely
out of view at home. Nothing is saved from the grid.

Both the cube and Exposé move panes by their frames and animate the move with
the layer transform. AppKit draws no view whose frame lies outside the window,
so a pane only carried into view by its transform would show up blank. A
zoomed pane's layer is as big as its bounds and AppKit scales it onto the
frame with the layer's transform, so every transform the canvas sets starts
from that scale. AppKit also anchors each view's layer at its corner and puts
that anchor back whenever it updates the layer from its view, which it first
does at some point after launch. So the cube never moves an anchor: the stage's
perspective, the reflection, the cube and its faces carry their centers in
their transforms.

The theme is data: `config/theme`, an s-expression read into `jim.theme`'s
`Theme` with Coil's serde. Edit and save it to apply it; ⌘R reads it again. A
file that does not read as a theme, or a value out of range, keeps the last good
theme, and Jim prints why. Terminal configuration is in `config/ghostty` and is
read at application startup.

## Actions and diagnostics

The palette opens inside the main window over a dimmed backdrop. Escape or an
outside click dismisses it and restores focus. It searches the current shell
action registry, including terminals,
canvas navigation, projects, theme reload, and frame timings. It uses native
text editing and IME input. Palette rows and sidebar buttons have hover states;
unhandled keys are silent, and terminal audio bells are disabled.

Search for `fps` in the palette to toggle the timing overlay inside the main
window. It shows 120 display-callback intervals with average, p95, maximum,
and late-callback count, plus measured main-thread stages: input/action dispatch,
maintenance, AppKit updates, Ghostty app ticks, and the overlay's own cost.
A display callback is not proof of a presented terminal frame. Ghostty's
separate rendering thread and GPU timings are not exposed by this integration.
The display link pauses when the overlay is hidden.

Pane dragging and resizing use the current camera, so a held pane continues
to follow the pointer during Command-scroll, even without mouse movement.

## Controlling Jim from a shell

`jimc` is to this app what `jimctl` is to original Jim: scripts and agents use it to
drive a running Jim. Building links it as `~/.local/bin/jimc`. `jimc help` lists
everything:

```sh
jimc diff-wall 'exclude=**/tests/**'        # this directory's working diff, on a new project
jimc diff-wall range main --background      # the same, without switching to it
jimc project list
jimc pane list --project Recursion
jimc term new --dir . --at 100,100,800,500  # prints the new pane, and its id
jimc term send 3 'cargo test' --enter
jimc term read 3
jimc widget open markdown README.md
jimc action run 'Canvas: Fit all panes'     # anything the palette does
jimc action run 'Project: Set directory' --answer ~/code/x
```

Every reply is one line of JSON with `ok` and, when that is false, `error`; the exit
code is 1 then, and 2 for a command line `jimc` can't make sense of. A project is its
name or id, and defaults to the selected one. A pane's id lasts until Jim restarts; a
terminal's `session` lasts as long as the terminal.

`jimc` never brings the app to the front, and panes it opens leave the keyboard where it
is. Only `project activate`, `pane focus` and `action run` move the keyboard, as do
`project new` and `diff-wall`, which switch to what they make unless given
`--background`.

The protocol is one JSON object per line on `~/.jim-coil/control/socket`, or the path in
`$JIM_COIL_SOCKET`, so anything can speak it directly with `jimc raw` or `nc -U`. Only
your own user can connect. The first app running owns the socket, so with the
development app and a release both open, `jimc` reaches whichever started first and
`jimc status` says which. A release ships `jimc` in its root; link it yourself with
`ln -s ~/Library/Application\ Support/JimCoil/root/build/jimc ~/.local/bin/jimc`.

`jimctl git …` and `jimctl review …` read the repository and need no app, so they are
still how you do those things. Everything else in `jimctl` talks to original Jim.

## Widgets

A widget is a Coil source file, `widgets/NAME.coil`, that Jim compiles in-process
with Coil's JIT and hot-reloads on save. Open one with the palette action
**Widget: Open widget** and enter `NAME ARGS…`:

| Widget | Port of | Open with |
|---|---|---|
| `diff` | `diff.ft` | `diff`, `diff range main HEAD`, `diff pr 123`, `diff file x.patch`; a leading `repo=PATH` picks another repository |
| `diffwall` | `jimctl git diff-wall` | `jimc diff-wall`, or the palette's **Diff: Open diff wall**, below |
| `stage` | `stage.ft` | `stage [REPO]` — stage/unstage hunks or files, commit |
| `branches` | `branches.ft` | `branches [REPO]` — checkout, new branch, worktrees, diffs |
| `markdown` | `markdown.ft` | `markdown [PATH]` |
| `counter` | `controls_demo.ft` | `counter` |
| `git` | — | `git` — status and recent commits |

**Diff: Open diff wall** lays a whole diff out across a new project's canvas, one
pane per file, for reading a change at once and in place. Its prompt takes:

```text
[repo=PATH] [working|staged|unstaged|range BASE [HEAD]|pr N]
[per=file|hunk] [path=GLOB]… [exclude=GLOB]… [max=N]
```

The default is everything that differs from `HEAD`, untracked files included. Globs
are relative to the repository and match files or directories, as in
`exclude=**/tests/**`; exclusions win. Whitespace-only changes are left out. A word
can't hold a space, so give a path with spaces through **Project: Set directory**
on the current project rather than `repo=`.

The first pane is the wall's index: click a file to go to its tile, or use **Fit**
to see the wall again. **By hunk** gives each hunk its own tile, **Arrange** tidies
tiles you've moved, and **Copy comments** puts the open review threads on the
clipboard to paste to whoever will act on them. Click a line in a tile to comment,
as in `diff`.

The wall stays current while its index pane is open: tiles update in place, a file
that starts differing gets a tile in the shortest column, and the tile of a file with
nothing left to review closes. Tiles stay where you put them; only **Arrange** moves
them. Closing the index leaves its tiles as they last were. A tile you close stays
closed until its file leaves the diff and comes back. A pull request's wall refreshes
only when you press ↻.

A widget declares `(module widgets.NAME)`, imports `jim.widget-api`, implements
its `Widget` trait (`render`, `event`, `save`, `animating?`, `destroy!`), and
defines `boot`, which builds the widget from a saved `Snapshot` (plus Jim's
`jim.dir` project directory and `jim.args`). `render` describes an element tree:
`vstack!`, `hstack!`, `table!`, `dialog!` containers; `text!`, `button!`, `tab!`,
`toggle!`, `badge!`, `divider!`, `spacer!`; native `input!` and `textarea!` fields;
and setters for padding, margin, size, grow, alignment, colors, borders, clipping,
monospace, wrapping and clickable rows. Jim lays it out, draws it, scrolls the
pane (passing the offset so widgets can build only visible rows), and routes
clicks, edits and timer ticks back as events. Events can ask Jim to open another
widget or a terminal, place, move, close or reveal widget panes on its canvas, fit
the canvas, or copy text. Jim calls widgets only through the trait's vtable. There
is no C interface between them.

`src/widget_kit/` holds widget-side helpers compiled into each widget: text
utilities, non-blocking child processes (`proc`), JSON replies (`json`), a
unified-diff model and parser (`diff`), a lexical syntax highlighter
(`highlight`), the shared diff row primitives (`git-view`), and the diff wall's
specs, tiles and layout (`wall`). The git widgets
talk to git through `jimctl git …` and `jimctl review …`. Jim adopts the login
shell's `PATH` at startup so those tools are found when launched from Finder.

Widgets never block Jim's main thread for long work:

- **Compiling.** On save, the new version compiles on Jim's compiler thread (the
  only thread that touches the JIT, with its own malloc zone) while the current
  version keeps running and responding. When it is ready, the main thread saves
  the running widget's state, boots the new version from it and switches over;
  that swap costs one render. Each save compiles once, with Coil's native JIT
  backend (tpde), live in 0.15–0.3 s. A save made during a compile is compiled
  after it. The old generation retires once any background
  tasks it started have finished, then its session is reset, which unmaps its
  code. A compile error or API misuse leaves the previous version running and
  shows the error in the pane.
- **Processes and tasks.** Widgets reach Jim through the `Host` trait
  (`(api/host saved)`): `spawn`/`poll`/`release` run child processes, launched
  on a background thread with non-blocking output and `GIT_OPTIONAL_LOCKS=0`;
  `start-task`/`task-done?`/`release-task` run a widget's `Task` (for example
  parsing and highlighting a large diff) on Jim's worker threads. A widget
  returns true from `animating?` while any of these are outstanding so it keeps
  receiving ticks.

Jim remembers text measurements by text, font and wrap width, so a refresh that
repeats earlier text costs tens of microseconds. For example, a README in the
markdown widget refreshes in about 0.4 ms. With five widgets reloading every
second, swaps between generations never took more than 5 ms of main-thread
time. The longest passes were first opens, when all of a widget's text is new:
up to about 14 ms for the markdown widget, under one 60 Hz frame. The first
text field or text view a process creates sets up AppKit's text system, so Jim
creates and discards one of each at startup, before its window opens.

**Live refresh.** `watch!` in `render` names paths to watch. Jim follows them
with FSEvents and delivers changes as `FILES-CHANGED` events. `emit!` sends a
`MESSAGE` to every other open widget; for example, stage sends `git.changed`
after staging or committing, and diff sends `review.changed` after editing a
review thread. The kit's `live/Refresher` coalesces notices so a widget
refreshes at most every 500 ms and never while a refresh is still running.

**Persistence.** A widget keeps what should survive in a `State` struct that
derives `coil.serde`'s `Serialize` and `Deserialize`:

```coil
(defstruct State [(file i64) (message (ArrayList u8))])

(derive (Serialize (field message (with text-ser text-de)))
        (Deserialize (field message (with text-ser text-de)))
        State)
```

`save` calls `(save-state! s (.state self))`, which stores the state as one JSON
entry in the `Snapshot`. `boot` matches `(load-state [State] saved)`: `Fresh` on
a first boot, `Loaded` with the decoded state, or `Refused`. A field the saved
JSON lacks takes its `(default …)` option, and saved fields the struct no longer
has are skipped. If a new field has no default, the reload is refused: the
previous version keeps running and the pane names the missing field. The
`text-ser`/`text-de` hooks store an owned `(ArrayList u8)` as a JSON string. Jim
uses the snapshot both across reloads and across app restarts: the layout file
stores each widget pane's spec and its saved state, and on relaunch the widget
boots from that state.

Editing `src/widget_api.coil` requires rebuilding Jim, and widgets refuse to
load until then.

All panes of a widget share its compiled code, so a second pane opens at once and
costs only its own state, and a save compiles once however many panes show it. The
next version compiles into a second JIT session while the current one runs, which
is then reset and kept for the next save. Sharing code means sharing module-level
mutable state, so a widget keeps per-pane state in its own struct. A pane whose
state a new version refuses stays on the old version, which stays mapped until it
moves on. Closing a widget's last pane frees its sessions. The first compile in a
process allocates large short-lived compiler buffers, which raises the process
footprint once; later widgets and reloads reuse that memory.

## Checks and scope

```sh
scripts/test.sh
```

Tests cover Ghostty ABI layouts, camera projection, original Jim's input routing
and sensitivity, origin shading, hot-load validation, project/profile semantics,
and real daemon detach/reconnect, terminal responses, and shell exit. See
[architecture](docs/architecture.md) for ownership and extension boundaries.

This is the shell foundation. It does not yet migrate Jim's editor, browser,
whiteboard, nested canvases, or every existing pane type. Projects and profiles are dynamic. App restart reconnects the saved terminal
sessions through Jim’s private service, preserving running shells and their state. Native IME/Unicode wiring is present;
full input-method and accessibility parity still needs broader interactive QA.

## Projects, profiles, and persistent terminals

The sidebar lists global projects in drag order. Each project has its own default
working directory, canvas, pane positions, and focused pane. Drag a project row to
reorder it; drag the sidebar edge to resize it. The visibility buttons hide/show
projects in the current profile. “Show hidden projects” exposes hidden rows.
The profile menu switches visibility/selection sets; horizontal trackpad scrolling
across the sidebar also switches profiles. New profiles copy the current selection
and visibility, while new projects are hidden in other profiles.

Use the inline action palette to create/rename/delete projects and profiles, set a
project directory, or use the focused terminal’s current directory. New terminals
start in that directory. Project deletion explicitly confirms its name and closes
its terminals. Hiding a project or changing profiles leaves its terminals running.
Pane focus changes only the titlebar color.

Jim’s own `jim-session` process owns each terminal’s PTY and a headless Ghostty VT
core. It uses a private, same-user Unix socket; there is no tmux dependency or
terminal multiplexer. Closing the app detaches all renderers, and force quitting it leaves
terminals opened by this build running. Opening it reconnects the same shells; explicitly closing a pane terminates its session. “Terminal:
Reconnect focused terminal” retries an unavailable connection without discarding
its saved identity. An exited shell remains readable until its pane is closed.

Recovery uses an ordered in-memory journal of output and resizes that keeps the newest
64 MiB of each session, the same limit as original Jim, so disk use and replay time
are bounded. Older output is gone from recovery; a client replaying a trimmed journal
is told the size, directory and input modes the trimmed part established. Sessions
survive app closure, not daemon crashes or machine restarts. Recovery of terminal
graphics that reference temporary files has not been validated.

### Bringing projects across from original Jim

Run “Project: Import from original Jim” from the action palette and pick one project.
The list holds only projects with something left to bring across, those with terminals
first. The project joins one of the same name, or is created with its saved directory,
and is shown. Every terminal of it still running under original Jim's daemons comes
with it, and those shells keep running throughout. Original Jim's saved data is only
read. Widgets and other non-terminal panes are not brought across.

Original Jim must be closed for its terminals to come. If it is open the project is
still imported, and importing it again after quitting brings them. The list then shows
every saved terminal, since checking which are alive would disturb them, and original
Jim may not have saved its newest changes.

An imported pane is a `jim-session --adopt` service in front of that daemon. Closing
the app detaches from the service as usual; closing the pane ends the shell. Reopening
original Jim takes its terminals back: the service stops without touching the shell
and never reconnects, and the pane offers Terminal: Reconnect. While original Jim is
open, the rewrite will not adopt a daemon. After a machine restart a pane whose daemon
is gone starts a new shell, like any other pane.

Imported shells keep the environment they started with, including `TERM`. Commands
that need the original app, such as `jimctl open`, need it running, and the original
daemons' shells still cannot launch GUI apps. History comes from the daemon's own
64 MiB buffer, which records no resizes and may begin mid-sequence, so old scrollback
can look as it does when original Jim relaunches. Modes set before that buffer begins
are unknown to everyone, until the program sets them again.
