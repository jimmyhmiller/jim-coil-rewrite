# Restarting the app

After making a change the user asked for, restart the app yourself so they can see
it, without being asked or telling them to. Always use `./scripts/dev-restart.sh`. Do
not substitute `coil run`, a direct binary launch, or a bare `open`: `open` forwards
the caller's environment into the app and every new terminal. Wait for it to print
`verified` before reporting success.

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
1. Run `coil fmt --write src/*.coil tests/*.coil`.
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
protocol changes. Its adoption tests run the real original `jim-daemon` in a private
runtime directory. Never connect to a socket in `/tmp/.terminal-bevy-*` while testing:
connecting drops original Jim's client for that live terminal. Verify real app quit/reopen for renderer integration changes.
Format native Coil boundary code with `coil fmt` and the Ghostty extension with
`zig fmt`. Export
native callbacks with `export-c`; `fnptr-of` then selects their C ABI wrappers
while direct Coil calls retain Coil's internal struct-reference convention.

Only patch the project-local pinned Ghostty dependency under build/deps; never
modify original Jim's checkout or installed Ghostty. Reproduce patches through
scripts/ghostty/session-backend.py.
