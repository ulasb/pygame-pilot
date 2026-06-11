"""
Bootstrap: runs INSIDE the target process.

    python -m pygamepilot.bootstrap <app.py> [app args...]

Environment:
    PILOT_OUT     session directory (frames/, log)
    PILOT_SOCK    Unix socket path for the command server
    PILOT_HEADED  set to 1 to show a real window (default: SDL dummy)

The target script runs unmodified via runpy with patched pygame. The
app blocks at its first display flip until the controller grants
frames.
"""

import os
import runpy
import sys


def main() -> None:
    out_dir = os.environ.get("PILOT_OUT", ".pilot")
    sock = os.environ.get("PILOT_SOCK",
                          os.path.join(out_dir, "pilot.sock"))
    os.makedirs(out_dir, exist_ok=True)

    if not os.environ.get("PILOT_HEADED"):
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

    import pygame  # noqa: F401  (import before patching)
    from . import patches, server

    patches.install()
    server.start(sock, out_dir)

    if len(sys.argv) < 2:
        print("usage: python -m pygamepilot.bootstrap <app.py> [args...]",
              file=sys.stderr)
        sys.exit(2)

    target = sys.argv[1]
    sys.argv = sys.argv[1:]
    # behave like `python app.py`: script directory on sys.path
    sys.path.insert(0, os.path.dirname(os.path.abspath(target)))
    runpy.run_path(target, run_name="__main__")


if __name__ == "__main__":
    main()
