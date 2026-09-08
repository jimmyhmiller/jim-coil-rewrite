# Coil development workflow

Before writing Coil, read the relevant installed guide topics, especially
`coil guide structs operators build`. Bare `coil guide` lists topics;
`coil guide --all` prints the complete reference.

Use modern Coil syntax in application code:
- Read fields with `(.field value)`.
- Write places with `(set! place value)`, including `(set! (.field value) new-value)`.
- Borrow fields with `(mut (.field value))`.
- Use variadic `and` and `or` instead of nesting the same operator.
- Keep explicit pointer operations where an address or raw-memory operation is needed.
- Treat vendored examples as implementation references, not the language style guide.

Before completing Coil changes:
1. Run `coil fmt --write src/*.coil tests/*.coil config/*.coil`.
2. Run `coil lint --fix`. Apply it to separately compiled entries as needed.
3. Run format again after lint fixes, inspect the diff, and run the relevant checks,
   including `scripts/test.sh` for changes covered by the project suites.
4. Keep vendor provenance accurate when formatting or modernizing copied files.

Use the `jim-coil-rewrite` pad as the project index and working record.
Report dependency bugs in that dependency's bugs pad following its reporting rules.
If creating worktrees, put them under the project's ignored `.worktrees/` directory.

Terminal sessions belong to Jim's private service. Do not introduce tmux or
another terminal multiplexer. App shutdown detaches; explicit pane/project
closure terminates the corresponding sessions. Preserve stable session IDs.
Run `python3 tests/session_test.py` after building the service for lifecycle or
protocol changes. Verify real app quit/reopen for renderer integration changes.
Format native Coil boundary code with `coil fmt` and the Ghostty extension with
`zig fmt`. Export
native callbacks with `export-c`; `fnptr-of` then selects their C ABI wrappers
while direct Coil calls retain Coil's internal struct-reference convention.

Only patch the project-local pinned Ghostty dependency under build/deps; never
modify original Jim's checkout or installed Ghostty. Reproduce patches through
scripts/ghostty/session-backend.py. Compile config/ from its own package directory
so hot configuration libraries cannot link a second copy of Ghostty into the app.
