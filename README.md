# pygame-pilot

Drive, frame-step, and observe **unmodified pygame apps** from the
command line. Built so that a test script — or an AI coding agent — can
*play* a game and *see* exactly what a player would see, one
deterministic frame at a time.

```
┌──────────────┐   unix socket    ┌───────────────────────────────┐
│  pilot CLI   │ ───────────────► │ your game (unmodified)        │
│  (any py3)   │   JSON commands  │  + pygamepilot bootstrap shim │
└──────────────┘                  └───────────────────────────────┘
        ▲                                      │
        └── PNG frames of the real display ◄───┘
```

## How it works

`pilot start` launches your app via a bootstrap shim
(`python -m pygamepilot.bootstrap your_game.py`) that patches pygame
*inside the target process*:

- **Frame gate** — `pygame.display.flip()`/`update()` block after
  presenting until the controller grants more frames. The app is always
  frozen at a frame boundary it drew itself, so every screenshot is a
  complete, real frame.
- **Input injection** — keys are delivered both as `KEYDOWN`/`KEYUP`
  events *and* through a wrapped `pygame.key.get_pressed()`, covering
  both styles of input handling.
- **Virtual clock** — `Clock.tick(fps)` doesn't sleep and returns the
  nominal frame time; `pygame.time.get_ticks()` derives from the frame
  counter. Runs are deterministic and as fast as you drive them.
- **Headless by default** — SDL dummy video/audio drivers; pass
  `--headed` to watch live.

No changes to the target app, no dependencies beyond the target's own
pygame. The CLI itself is stdlib-only.

## Quick start

```bash
# launch (paused at its first frame)
python -m pygamepilot start --cwd ~/git/mygame \
    --python ~/git/mygame/venv/bin/python -- main.py

# press Enter on the title screen, advance 6 frames
python -m pygamepilot adv 6 --tap return

# hold right for 60 frames and grab a screenshot
python -m pygamepilot adv 60 --down right --shot running
# → {"frame": 67, "shot": ".pilot/frames/running.png"}

# release, capture a frame every 10 during the next 120
python -m pygamepilot adv 120 --up right --record 10

python -m pygamepilot info   # frame counter, window size, held keys
python -m pygamepilot stop
```

Each session lives in a directory (default `.pilot/`): the control
socket, the app's pid and log, and captured `frames/`.

### Scripted runs

```bash
python -m pygamepilot run --script examples/prince_of_persia.json \
    --cwd ~/git/PrinceOfPersiaPy --python venv/bin/python -- src/main.py
```

A script is a JSON list of raw commands:

```json
[
  {"op": "advance", "frames": 2, "shot": "title"},
  {"op": "advance", "frames": 6, "tap": ["return"]},
  {"op": "advance", "frames": 100, "shot": "landed"},
  {"op": "advance", "frames": 90, "down": ["right"], "shot": "running"}
]
```

### Command reference

| op | fields | effect |
| -- | ------ | ------ |
| `advance` | `frames`, `down[]`, `up[]`, `tap[]`, `shot`, `record` | apply input, run N frames, optionally screenshot (every `record` frames) |
| `shot` | `name` | screenshot the current (frozen) frame |
| `info` | | frame counter, display size, title, held keys |
| `freerun` | `enable` | un-gate frames (approximate real time) |
| `quit` | | ask the app to exit |

Key names are pygame key names (`right`, `left shift`, `a`, `return`);
`shift`, `ctrl`, `alt`, `enter`, `esc` aliases included.

## Using it from an AI agent

This tool exists because "screenshot the real game after exactly these
inputs" turns visual bugs into reproducible artifacts. A typical agent
loop:

1. `pilot start ... -- main.py`
2. `pilot adv N --down right --shot step1` → read the PNG
3. compare with expectation, edit code, restart, repeat

Because frames are gated, the same command sequence produces the same
frames every run — failures are reproducible and bisectable.

## Limitations

- The app must drive its loop through `pygame.display.flip()` or
  `update()` (virtually all pygame apps do).
- `pygame.key.get_mods()` is not yet overlaid (modifier-sensitive apps
  see injected `mod=0` events).
- Mouse injection is not implemented yet.
- One window per process; SDL2-only (pygame 2.x).

## Tests

```bash
python -m pytest tests/   # needs pygame in the interpreter
```

## License

MIT
