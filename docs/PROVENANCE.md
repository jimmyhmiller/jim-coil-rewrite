# Source origins

`src/objc.coil` and `src/animation.coil` originated in the user's
coil-experiments/src/experiments/coil_gpui, revision
f039d19600ba89608586c3032ff83a907688cf53. They are now maintained as Jim's own
`jim.objc` and `jim.animation` modules, with modern Coil syntax and the same
formatting and lint checks as the rest of the application.

The Objective-C helper supplies typed message dispatch; the animation module
supplies easing and spring mathematics. See [design attribution](THIRD_PARTY_NOTICES.md).

The external Ghostty embedding header and its license remain in `vendor/`.
The header is pinned and checked by the dependency build and ABI tests.

`src/session/server.coil` and `src/session/transport.coil` are Jim's native session
and transport implementation. `src/session/GhosttySession.zig` and
`scripts/ghostty/session-backend.py` form the Ghostty-side dependency extension. It is applied
only to the local pinned Ghostty source under `build/deps`. No project-owned C
source remains; native aggregate callbacks are exported directly from Coil.
The service links Ghostty's public headless VT library from the same revision as
the renderer. Both retain Ghostty's MIT license (`vendor/GHOSTTY-LICENSE`).
