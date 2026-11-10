# Writing widgets

A widget is a pane whose contents you write in Coil. It's one file,
`widgets/NAME.coil`. Jim compiles it in-process and swaps in the new version every
time you save the file, keeping the pane's state. This guide covers building one,
from an empty file to something tested and shipped. For how the machinery works
inside Jim, see [architecture.md](architecture.md). The full API, with a comment on
every function, is [`src/widget_api.coil`](../src/widget_api.coil).

## The loop

1. Create `widgets/NAME.coil`. In a release, widgets live in
   `~/Library/Application Support/JimCoil/root/widgets/` instead.
2. Open it: in the palette (⌘⇧P), run **Widget: Open widget** and type
   `NAME ARGS…`. From a shell, run `jimc widget open NAME ARGS…`.
3. Edit and save. The pane updates within about half a second. If the new version
   doesn't compile, the old one keeps running and a red band at the bottom of the
   pane shows the error.

A name may use only `a-z`, `0-9`, `-` and `_`. The file's module must be
`widgets.NAME`.

## A first widget

This widget greets someone, counts waves, and remembers both across reloads and
restarts. Save it as `widgets/guide-hello.coil` and open it with
`guide-hello Ada`.

<!-- widget: guide-hello -->
```coil
(module widgets.guide-hello)
(import "coil.alloc" :as alloc)
(import "coil.arraylist" :use *)
(import "coil.serde" :use *)
(import "coil.serde.derive" :use *)
(import "jim.widget-api" :use *)
(import "jim.widget-kit.text" :as text)

;;; What survives reloads and restarts.
(defstruct State [(name (ArrayList u8)) (waves i64)])

(derive (Serialize (field name (with text-ser text-de)))
        (Deserialize (field name (with text-ser text-de))
                     (field waves (default 0)))
        State)

(defstruct Hello [(state State)])

(impl Widget Hello
  (render [(self (ptr Hello)) (ui (ptr Ui))]
    (-> void)
    (title! ui "Hello")
    (vstack! ui 10.0 14.0)
    (text! ui "Hello, " 15.0 0xe6e9f0 true)
    (append! ui (slice (.name (.state self))))
    (hstack! ui 8.0 0.0)
    (input! ui "name" (slice (.name (.state self))) "your name")
    (grow! ui 1.0)
    (button! ui "wave" "Wave")
    (key! ui "w")
    (end! ui)
    (text! ui "waves: " 12.0 0x9098a4 false)
    (append-i64! ui (.waves (.state self)))
    (end! ui))
  (event [(self (ptr Hello)) (e (ptr Event))]
    (-> void)
    (cond (changed? e "name")
            (text/set-str! (field (field self state) name) (.text e))
          (clicked? e "wave")
            (set! (.waves (.state self)) (+ (.waves (.state self)) 1))
          :else (do)))
  (save [(self (ptr Hello)) (s (ptr Snapshot))]
    (-> void)
    (save-state! s (.state self)))
  (animating? [(self (ptr Hello))]
    (-> bool)
    false)
  (destroy! [(self (ptr Hello))]
    (-> void)
    (free! (mut (.name (.state self))))
    (alloc/destroy [Hello] (alloc/malloc-allocator) self)
    (do)))

(defn boot [(saved (ptr Snapshot)) (out (ptr (dyn Widget)))] (-> void)
  (match (load-state [State] saved)
    (Fresh []
           (set! out
                 (alloc/box! (alloc/malloc-allocator)
                             Hello
                             (Hello
                               :state
                                 (State
                                   :name (text/owned (get-text saved "jim.args" "world"))
                                   :waves 0)))))
    (Loaded [state]
            (set! out (alloc/box! (alloc/malloc-allocator) Hello (Hello :state state))))
    (Refused [] (do))))
```

Every widget has the same parts:

- **`(module widgets.NAME)`** and an import of `jim.widget-api`, the contract between
  Jim and widgets.
- **A type implementing `Widget`**, with five methods:
  - `render` describes the pane.
  - `event` handles what the user and Jim send.
  - `save` writes the state that should survive.
  - `animating?` says whether to keep sending ticks.
  - `destroy!` frees everything the widget owns.
- **`boot`**, which builds the widget from a saved `Snapshot` and stores it in `out`.
  Jim calls it when the pane opens, after each save of the file, and after a restart.

## Rendering

`render` runs after every event and whenever the pane changes size or scrolls. It
describes the whole pane from scratch each time, and Jim lays it out and draws it.

**Containers** hold other elements. Open one, add children, and close it with `end!`:
- `vstack!` (a column) and `hstack!` (a row), each taking a gap and a padding;
- `table!`, a grid of N columns;
- `dialog!`, a modal panel over the pane.

The whole tree needs one root container, and every container must be closed.

**Elements:**
- text: `text!` (text, size, `0xRRGGBB` color, bold), `append!` and `append-i64!`;
- buttons and toggles: `button!`, `tab!` (a segmented-control button), `toggle!`;
- decoration: `badge!`, `divider!`, `spacer!`;
- native text fields: `input!` (one line) and `textarea!` (several lines).

**Styles** change the element made most recently, so style a container right after
opening it:
- size and spacing: `pad!`, `margin!`, `width!`, `height!`, `grow!` (share a row's
  spare width);
- layout: `align!` (`START`, `CENTER`, `END`, `STRETCH`);
- look: `bg!`, `border!`, `radius!`, `color!`, `variant!` (`PRIMARY`, `DANGER`,
  `SELECTED`, `GHOST`);
- text: `mono!`, `wrap!`;
- behaviour: `clip!`, and `clickable!`, which turns a container into a list row that
  sends a click.

**The pane:**
- `title!` names the pane in its header.
- `(.width ui)`, `(.height ui)` and `(.scroll-y ui)` give the visible area. Use them to
  fill the pane, as the editor's text area does with `height!`, or to build only the
  rows that are on screen.
- The pane scrolls by itself when the content is taller than it.

**Mistakes** such as an `end!` with nothing open, or a style before any element,
stop the frame. The pane then shows what went wrong instead of drawing.

**Colors:** `jim.widget-kit.git-view` has the ones the built-in widgets use: `INK`,
`MUTED`, `ACCENT`, `WARN`, `ERR`.

## Events

Each event has a `kind`, an `id` and a `text`. Test for it with the predicates:

| Predicate | When |
|---|---|
| `(clicked? e ID)` | a `button!`, `tab!` or `clickable!` row was clicked, or its key pressed |
| `(toggled? e ID)` | a `toggle!` flipped; `(.checked e)` is the new value |
| `(changed? e ID)`, `(submitted? e ID)` | a field was edited, or Return (⌘Return in a text area) was pressed; `(.text e)` is the whole text |
| `(tick? e)` | a timer tick while `animating?` returns true; `(.dt e)` is the seconds since the last one |
| `(files-changed? e)` | a path the frame `watch!`ed changed |
| `(message? e TOPIC)` | another widget `emit!`ted on TOPIC; `(.text e)` is the payload |
| `(file-chosen? e "open")`, `(file-chosen? e "save")` | the Open or Save sheet was answered; `(.text e)` is the path |

Ids are text. For lists, encode an index (`"file:3"`) and read it back with
`(id-prefix? e "file:")` and `(id-number e "file:")`.

**Text fields:**
- A field shows the value you pass it, so store the text from each `changed?` event
  and render it back.
- While the user types, Jim leaves the field alone unless the value you render
  changes, so you can still replace the text, for example after reloading a file.

**Keys:**
- `(key! ui "s")` makes ⌘S press the element just made.
- `(shortcut! ui "s" "save")` makes ⌘S send a click with id `"save"`, with nothing on
  screen.
- Either works only while the pane has the keyboard, and Jim's own shortcuts (⌘T, ⌘W,
  …) always win.

## Asking Jim for things

During `event`, a widget can ask Jim to act. Jim carries the requests out after the
event returns.

| Request | Does |
|---|---|
| `open-widget!`, `open-widget-at!` | open another widget pane (`"NAME ARGS…"`), optionally at a place on the canvas |
| `open-terminal!` | open a terminal in a directory |
| `move-widget!`, `move-self!`, `close-widget!`, `reveal-widget!`, `fit-canvas!` | arrange panes |
| `copy-text!` | put text on the clipboard |
| `scroll-to!` | scroll this pane |
| `emit!` | send a message to every other widget |
| `choose-file!`, `choose-save-path!` | show the Open or Save sheet, which answers with `FILE-CHOSEN` |

## State that survives

**The state struct:**
- Keep whatever should survive in one struct deriving `Serialize` and `Deserialize`.
- `save` calls `(save-state! s state)`.
- `boot` matches `(load-state [State] saved)`:
  - `Fresh` for a new pane;
  - `Loaded` with the state from the last save;
  - `Refused` when the saved state no longer fits. In that case just return; the pane
    explains why.
- Jim saves widget state with the layout within a fraction of a second of an event, so
  it survives a quit or a crash.

**Changing the struct:**
- Give a field you add `(default …)`, or reloads will refuse to boot until the pane
  is reopened.
- Removing a field is fine: the saved value is skipped.
- Owned text fields take `(with text-ser text-de)`, because the snapshot they're read
  from is freed after `boot`.

**Context from Jim:** besides your own state, every snapshot has two entries:
- `(get-text saved "jim.dir" ".")`, the project's directory;
- `(get-text saved "jim.args" "")`, whatever followed the widget's name when it was
  opened.

A widget keeps the meaning of its arguments on a first boot. A restored pane usually
goes by its own state.

## Slow work: processes and tasks

Widget code runs on Jim's main thread. A widget that runs for more than two seconds
is stopped, so anything slow happens elsewhere, and the widget checks on it every
tick:

- **Processes.** `jim.widget-kit.proc` runs a command without blocking. `proc/start!`
  returns at once, and `proc/poll!` on each tick says when it's done.
- **Tasks.** Implement `Task` with a `run` method and hand it to
  `(start-task host task)`. Jim runs it on a worker thread. Check
  `(task-done? host handle)` on ticks, use the result on the main thread, and then
  `release-task`. A task must touch only its own data while it runs.

Get the host at boot with `(host saved)`. Return true from `animating?` while
anything is outstanding, so the ticks keep coming.

This widget shows the project's latest commit. Open it with `guide-head`.

<!-- widget: guide-head -->
```coil
(module widgets.guide-head)
(import "coil.alloc" :as alloc)
(import "coil.arraylist" :use *)
(import "jim.widget-api" :use *)
(import "jim.widget-kit.text" :as text)
(import "jim.widget-kit.proc" :as proc)

;;; The project's latest commit, from git, read again on Refresh.
(defstruct Head [(job proc/Job) (dir (ArrayList u8)) (line (ArrayList u8))])

(defn refresh! [(h (ptr Head))] (-> void)
  (proc/start! (field h job) ["git" "log" "-1" "--oneline"] (slice (.dir h)) 0))

(impl Widget Head
  (render [(self (ptr Head)) (ui (ptr Ui))]
    (-> void)
    (vstack! ui 8.0 14.0)
    (text! ui
           (if (proc/running? (field self job)) "Reading…" (slice (.line self)))
           13.0
           0xe6e9f0
           false)
    (mono! ui)
    (button! ui "refresh" "Refresh")
    (end! ui))
  (event [(self (ptr Head)) (e (ptr Event))]
    (-> void)
    (cond (and (tick? e) (proc/poll! (field self job)))
            (do
              (text/set-str! (field self line)
                             (text/trim (proc/output (field self job))))
              (proc/reset! (field self job)))
          (clicked? e "refresh") (refresh! self)
          :else (do)))
  (save [(self (ptr Head)) (s (ptr Snapshot))] (-> void) (do))
  (animating? [(self (ptr Head))]
    (-> bool)
    (proc/running? (field self job)))
  (destroy! [(self (ptr Head))]
    (-> void)
    (proc/free! (field self job))
    (free! (mut (.dir self)))
    (free! (mut (.line self)))
    (alloc/destroy [Head] (alloc/malloc-allocator) self)
    (do)))

(defn boot [(saved (ptr Snapshot)) (out (ptr (dyn Widget)))] (-> void)
  (let [h
          (alloc/box! (alloc/malloc-allocator)
                      Head
                      (Head
                        :job (proc/job-new (host saved))
                        :dir (text/owned (get-text saved "jim.dir" "."))
                        :line (ArrayList::new [u8] (alloc/malloc-allocator))))]
    (refresh! h)
    (set! out h)))
```

To keep up with changes outside the widget:
- `(watch! ui PATH)` in `render` delivers `FILES-CHANGED` when anything under PATH
  changes. Declare it in every frame.
- `jim.widget-kit.live`'s `Refresher` coalesces a burst of notices into one refresh at
  most every half second. See `widgets/git.coil`.

## The widget kit

`src/widget_kit/` holds helpers any widget can import:

| Module | Has |
|---|---|
| `jim.widget-kit.text` | byte-string helpers: `set-str!`, `push-str!`, `owned`, `trim`, `lines!`, `basename`, `dirname`, `push-resolved!` (a path relative to the project) |
| `jim.widget-kit.proc` | child processes that never block |
| `jim.widget-kit.live` | coalescing refreshes after outside changes |
| `jim.widget-kit.json` | reading JSON replies, such as `jimctl`'s |
| `jim.widget-kit.diff`, `git-view`, `highlight` | unified diffs, their rows, and syntax highlighting |
| `jim.widget-kit.wall` | the diff wall's layout |

## Memory

- **Allocate with `(alloc/malloc-allocator)`, and free everything in `destroy!`.**
- **Copy what you keep.** An event's `id` and `text`, and a snapshot's text, belong to
  Jim and last only for the call.
- **Panes of a widget share its code**, and so its module-level mutable state. Keep
  per-pane state in the widget's own struct.

## When a widget breaks

**A compile error** leaves the previous version running, with the error in a band at
the bottom of the pane.

**A crash stops the widget, not Jim.** The pane says what happened and offers
**Restart**, which boots the widget again from its last good save. Saving the file
runs the new code. Jim stops a widget that:
- crashes;
- fails a check or assertion, or panics;
- runs past two seconds without returning.

Widgets are compiled with Coil's safety checks (`coil.safety`). An index out of
bounds, a null read, an overflowing cast or a double free then stops the widget where
it happens, instead of corrupting memory to fail somewhere else later. Under those
checks `malloc-allocator` is Coil's debug allocator.

**Where to look:** a panic's message and line go to Jim's log. In a development build
that's `$TMPDIR/jim-coil.log`, written by `scripts/dev-restart.sh`.

## Testing

`tests/widgets_test.coil` runs widgets without a window. It drives them directly:

```coil
(let [r (widgets/create "guide-hello" "." "Ada")]
  (widgets/reload! r)
  (assert (widgets/settle! r))                  ; wait for the compile
  (assert (widgets/render! r 400.0 300.0 0.0))  ; false on a fault or crash
  (widgets/activate! r (find-id r "wave"))      ; a click, by element id
  (widgets/input! r "name" "Grace" false)       ; an edit; true for Return
  (widgets/free! r))
```

Other things a test can do:
- read the frame through `(.ui r)`, with `find-id`, `has-text?` and `element-text` in
  the test file;
- check what the widget asked for with `(widgets/requests r)`;
- save and restore state with `widgets/save-state!` and `widgets/restore-state!`, to
  check it survives a restart.

Add each new widget to `every-widget-compiles-and-boots`. Run the widget tests with
`coil test widgets`, or everything with `scripts/test.sh`. The examples in this guide
are tested too: `the-guides-widgets-work` extracts them from this file and runs them.

## Before you commit

1. `coil fmt --write widgets/NAME.coil`, then `coil lint --fix widgets/NAME.coil`, then
   format again.
2. Run `coil test widgets`.
3. List the widget in the README's widget table. If it deserves a palette action, add
   one in `src/actions.coil` and `src/main.coil`, as **Editor: New note** does.
4. `scripts/build.py` builds every widget ahead of time into `build/widget-cache`, so
   launches load it at once. There's nothing to do by hand: a widget edited since
   simply compiles when it opens.

Changing `src/widget_api.coil` means rebuilding Jim. Until then, widgets refuse to load
against an API Jim wasn't built with.
