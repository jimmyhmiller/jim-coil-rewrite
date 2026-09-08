# Jim Atelier

Atelier explores a different organizing idea for Jim: work has a physical place.
A terminal is a work slip. A note can sit beside it or live in a bound notebook.
A live program produces a specimen you can carry back to the desk. Setting a
thing aside keeps it available.

The baseline before this exploration is commit `b3f1a10`. The existing app and
its project/profile state remain available through `scripts/run.py`. Atelier is
an additional native app in this project, with separate settings.

## Try it

```sh
python3 scripts/build-atelier.py
open 'build/Jim Atelier.app'
```

The development bundle expects to remain in this checkout's `build` directory.
The sibling `paper-test/lib/paper` and `paper-test/lib/layout` packages provide
the renderer and layout library. They are read-only dependencies, not copied or
modified checkouts. The build uses the same project-local pinned Ghostty library
and private session service as the original Coil shell.

The desk starts on moss felt. Open a shell, drag a slip by its top edge, or use
its minus button to put it away. The tray brings a slip back. “Gather the loose
ends” restores the initial arrangement. Moving slips is bounded so they cannot
disappear offscreen. A higher paper card clips the native terminal underneath it.
The sun button moves the light and adjusts relief and grain.

Fieldnotes saves thoughts locally and pages through them three at a time. Your
latest thought also appears on the loose desk note. The material cabinet offers
felt, woven linen, cork, suede, veneer, and cardstock. Its little punched stock
samples show light and depth against each surface; choosing one changes the desk.

In Workshop, open `plugins/rosette.coil`, change the return value from 12 to a
number between 3 and 24, and save. A new paper rosette arrives on the bench and
on the desk. A compile error or a native crash keeps the last accepted specimen.
Pause suspends source watching and, when one is running, the actual worker
process. Resume continues it. Compile & publish retries the current source.
The log button opens the compiler and worker output.

The accepted specimen, notes, material, and slip positions persist in the
`dev.jim.atelier` NSUserDefaults suite. Snapshot mode uses a fresh fixture and
does not write preferences or start terminals or plugins.

## What works, and the current boundary

This is a functional design exploration with one desktop, one terminal and
three reusable slips. It is not yet the replacement for Jim's multi-project,
multi-pane canvas. Its tray restores existing slips rather than making an
unbounded number of copies. Fieldnotes stores plain text; it is not a file
editor. Native text selection/IME come from AppKit and Ghostty.

The terminal uses Jim's private service. Closing the app detaches the renderer
and preserves the shell and its stable UUID. Hiding the slip also preserves it.
Atelier does not currently offer a destructive session-close control; type
`exit` in the shell to end it. The original shell still has explicit pane and
project closure. Original Jim's data and all neighboring source trees are
untouched.

The plugin interface is deliberately small and implemented:

```coil
(defn specimen [] (-> i64)
  12)
```

`tools/plugin-worker` embeds `coil.jit`. It loads a complete definition snapshot
with `jit-replace-source!`, declares the host result callback, then evaluates
`specimen`. The worker writes a versioned result record. The app validates the
result and only publishes after exit status zero. Failed compilation, invalid
values, and worker crashes leave the previous value intact. A running worker
has a 30-second deadline; time spent paused is excluded by resetting the
deadline when resumed. Compiler logs are written to a file so a full pipe cannot
deadlock the UI. This is process isolation for trusted local code, not a security
sandbox: plugins retain the user's filesystem and process permissions.

Each run has a fresh JIT session. Arbitrary plugin state does not survive a
generation. Only the validated specimen result does. The UI's code-shaped card
illustrates the interface and displays the accepted value; edit the actual file
to change the implementation.

## What the Coil experiments suggest next

The inspected `coil-experiments` live runtime already has stable function slots,
transactional replacement, staged app callback publication, generation leases,
schema migration, and cooperative loop-backedge checks. Its nREPL transport can
publish changes while an app stays on its main-thread event loop. Paper's live
host demonstrates this integration with its real renderer.

For Jim, keep the current process boundary and put a retained live controller
inside each plugin worker. Extend the integer record to a versioned, bounded
document of paper objects and actions. Give each object a stable ID and let the
host own all drawing and hit testing; no native pointers should cross workers.
Stage a candidate, validate its document and migration, then publish the entire
generation. Retain old code while callbacks still hold leases.

Cooperative pause points can expose a stopped computation and its typed state.
They cannot make arbitrary native memory corruption safe inside the UI process.
If a worker crashes, show its last accepted objects beside a diagnostic slip,
then restart from an explicit snapshot. A useful repair surface would contain
the source, rejected generation, state migration, and retry action together.

Original Jim's nested canvases suggest project folios: gather a set of terminal,
editor, drawing, and browser objects into a folder, shelve it, and reopen it in
the same arrangement. Its whiteboard suggests tracing-paper annotations over
work. Paper currently renders opaque height fields, so actual translucent
tracing stock and folded meshes would need renderer work; the present app does
not fake those capabilities. These are next steps, not implemented features.

## Verification

```sh
scripts/test.sh
coil build tests/atelier_integration.coil -o build/atelier-integration
python3 tests/atelier_test.py
```

The native integration test opens real windows, changes pages and materials,
saves a note, pauses/resumes the plugin, sends a command and a Return key through
native terminal routing, closes, and reopens. It checks the same shell PID and
session ID, retained notes, and retention of a successful specimen after a
compiler rejection and an abort in later worker processes. Test preferences
have a unique suite and test-owned terminal sessions are explicitly terminated.

Render the four fixture pages for visual inspection:

```sh
mkdir -p build/atelier-previews
'build/Jim Atelier.app/Contents/MacOS/jim-atelier' --app 0 --snapshot build/atelier-previews/desk.png
'build/Jim Atelier.app/Contents/MacOS/jim-atelier' --app 1 --snapshot build/atelier-previews/fieldnotes.png
'build/Jim Atelier.app/Contents/MacOS/jim-atelier' --app 2 --snapshot build/atelier-previews/materials.png
'build/Jim Atelier.app/Contents/MacOS/jim-atelier' --app 3 --snapshot build/atelier-previews/workshop.png
```

Fixtures render the unconnected terminal state. Automated window checks do not
replace broad manual accessibility, IME, trackpad, and overlapping-card visual
QA. The current tool session did not expose Computer Use's required `node_repl`
tool; no claim of manual pointer testing is made.
