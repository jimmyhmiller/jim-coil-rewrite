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
python3 scripts/run.py
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
  widget imports, `src/`, `widgets/`, `config/`, `jim-session`, and Ghostty's
  resources.

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

## Widgets

A widget is a Coil source file, `widgets/NAME.coil`, that Jim compiles in-process
with Coil's JIT and hot-reloads on save. Open one with the palette action
**Widget: Open widget** and enter `NAME ARGS…`:

| Widget | Port of | Open with |
|---|---|---|
| `diff` | `diff.ft` | `diff`, `diff range main HEAD`, `diff pr 123`, `diff file x.patch`; a leading `repo=PATH` picks another repository |
| `stage` | `stage.ft` | `stage [REPO]` — stage/unstage hunks or files, commit |
| `branches` | `branches.ft` | `branches [REPO]` — checkout, new branch, worktrees, diffs |
| `markdown` | `markdown.ft` | `markdown [PATH]` |
| `counter` | `controls_demo.ft` | `counter` |
| `git` | — | `git` — status and recent commits |

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
widget or a terminal. Jim calls widgets only through the trait's vtable. There is
no C interface between them.

`src/widget_kit/` holds widget-side helpers compiled into each widget: text
utilities, non-blocking child processes (`proc`), JSON replies (`json`), a
unified-diff model and parser (`diff`), a lexical syntax highlighter
(`highlight`), and the shared diff row primitives (`git-view`). The git widgets
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

Each open widget holds two JIT sessions, used alternately so the next version
can compile while the current one runs. Closed widgets return their sessions to
a pool for reuse. The first compile in a process allocates large short-lived
compiler buffers, which raises the process footprint once; later widgets and
reloads reuse that memory.

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
terminal multiplexer. Closing the app detaches all renderers. Opening it reconnects
the same shells; explicitly closing a pane terminates its session. “Terminal:
Reconnect focused terminal” retries an unavailable connection without discarding
its saved identity. An exited shell remains readable until its pane is closed.

Recovery uses an ordered, lossless disk journal of output and resizes, not a
truncated byte tail. Its disk use and replay time grow with session output; there
is no checkpoint compaction yet. Sessions survive app closure, not daemon crashes
or machine restarts. Recovery of terminal graphics that reference temporary files
has not been validated. The original Jim application and its data are untouched;
this rewrite migrates its own earlier layout format, not original Jim sessions.
