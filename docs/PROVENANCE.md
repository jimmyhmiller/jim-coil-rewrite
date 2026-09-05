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
