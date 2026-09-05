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
