# Jim in Coil

A native macOS shell for the Jim rewrite: Ghostty terminal panes on independent
project canvases, live Coil theme settings, and a composited workspace cube.

## Run

Requires Coil, Zig 0.16.0, Xcode's Metal toolchain, and a local signing identity. On a fresh checkout:

```sh
xcodebuild -downloadComponent MetalToolchain
python3 scripts/prepare-ghostty.py
python3 scripts/run.py
```

`GHOSTTY_SOURCE=/path/to/pinned/ghostty` can reuse an existing source checkout.
The build checks its embedding header against the pinned header. The development
app is `build/JimCoil.app`; it resolves this checkout's configuration and resources.
The build uses the existing `TerminalBevy Local Signing` identity; set
`JIM_SIGN_IDENTITY` to choose another installed identity. Signing preserves the
app identity across rebuilds. macOS may ask for Documents-folder access at first launch.

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
| Drag bottom-right grip | Resize pane |
| ⌘T / ⌘N / New terminal | Add a terminal pane |
| ⌘⇧P | Search actions; arrows or pointer select, Return or click runs |
| ⌘W / pane × | Close focused / selected pane |
| ⌘1–4 | Switch among the first four visible projects |
| ⌘⇧\ / All workspaces | Toggle cube; drag rotates, arrows select, Return enters |

Default empty-canvas left drag does not pan, matching Jim. Zoom spans 0.2×–4×.
Pan stops at the top-left origin; the canvas extends to the right and down.
Directional edge shading points back toward the origin as it leaves the viewport.
The Fit all panes button is an additional way to find the project's panes.

Edit and save `config/shell.coil` to hot-load theme/configuration values. ⌘R forces
a reload. Invalid builds preserve the last good configuration and live terminals.
Terminal configuration is in `config/ghostty` and is read at application startup.

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
