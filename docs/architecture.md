# Jim Coil shell

The current application is macOS-only. Coil owns the window, project canvases,
pane lifetimes, input routing, and live theme loading. Ghostty owns each PTY,
terminal model, shaping, and Metal/IOSurface renderer. AppKit and Core Animation
compose those surfaces into movable panes and project faces without CPU readback.

`canvas_model.coil` contains camera projection, gesture math, and origin feedback.
`canvas.coil` owns dynamic collections of stable heap-allocated panes. The canvas
uses top-left coordinates, with the same top-left wall as Jim; it has no right or
bottom wall. Native pane frames are projected from world coordinates. Pane bounds
remain in world units, preserving native mouse/IME coordinate conversion through
zoom. Moving a pane or camera changes its position without resizing its terminal.
Zoom updates content scale; pane resize updates PTY dimensions. Offscreen panes
retain their sessions and suspend Ghostty drawing.

Each of the four initial project slots has its own camera, pane collection,
z-order, and focus. The cube retains those canvas views as its four faces. Project
creation, nested canvases, and the rest of Jim's pane kinds remain migration work.

The origin indicators match `jim-app/src/canvas.rs`: screen-space edge gradients
are behind panes, and their strength measures how far the origin lies beyond that
viewport edge in world units. Width, saturation distance, strength, and shadow
color are live Coil theme values. Main surfaces and pane chrome also have explicit
tokens. Ghostty's own palette/configuration lives in `config/ghostty`.

The live configuration boundary is versioned: a separately compiled Coil dylib
exports a version and indexed numeric values. Compilation runs in an NSTask; a
failed compile, unsupported ABI, or invalid value preserves the last good config.
The host copies validated values and unloads the image. No pointer into the dylib
is retained. This is trusted native code; execution budgets and metaprogram-based
isolation have not been implemented. The boundary should grow into versioned pane
providers without moving terminal ownership into reloadable code.

Layout persistence stores project cameras, pane rectangles, z-order, and focus in
`~/Library/Application Support/JimCoil/layout.json`, using an atomic replacement.
It is separate from original Jim's data. Reopening starts new shells in the saved
layout. Hot reload preserves the existing shells; app-restart PTY persistence is
future work.

The Ghostty dependency is pinned to `7aa9591746ffa4d2eee458960c76554352832595`.
Its C header is retained under `vendor/`, and the used ABI subset has checks in
both C and Coil. The Objective-C messaging and animation modules come from the
existing Coil GPU UI experiment; see `vendor/PROVENANCE.md`.
