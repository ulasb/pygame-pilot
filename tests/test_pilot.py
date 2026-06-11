"""End-to-end tests: drive the square app through the harness.

Requires pygame in the python used to run the tests.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = Path(__file__).resolve().parent / "app_square.py"


def pilot(session, *args):
    out = subprocess.run(
        [sys.executable, "-m", "pygamepilot", "--session", session,
         *args],
        capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0, out.stdout + out.stderr
    return json.loads(out.stdout.splitlines()[-1])


@pytest.fixture()
def session():
    with tempfile.TemporaryDirectory() as tmp:
        sess = os.path.join(tmp, "sess")
        info = pilot(sess, "start", "--", str(APP))
        assert info["started"]
        yield sess
        pilot(sess, "stop")


def test_info_and_frame_gating(session):
    info = pilot(session, "info")
    assert info["size"] == [200, 150]
    start = info["frame"]
    pilot(session, "adv", "5")
    assert pilot(session, "info")["frame"] == start + 5


def test_held_keys_move_square(session):
    a = pilot(session, "adv", "1", "--shot", "a")
    b = pilot(session, "adv", "30", "--down", "right", "--shot", "b")
    pilot(session, "adv", "1", "--up", "right")
    assert a["shot"] and b["shot"]
    import pygame
    pygame.init()
    sa = pygame.image.load(a["shot"])
    sb = pygame.image.load(b["shot"])

    def square_x(surf):
        for x in range(surf.get_width()):
            if surf.get_at((x, 75))[:3] == (255, 200, 60):
                return x
        return None

    xa, xb = square_x(sa), square_x(sb)
    assert xa is not None and xb is not None
    assert xb > xa  # held right arrow moved the square

def test_tap_event(session):
    pilot(session, "adv", "30", "--down", "right")
    pilot(session, "adv", "1", "--up", "right")
    moved = pilot(session, "info")
    reply = pilot(session, "adv", "4", "--tap", "return", "--shot", "home")
    import pygame
    pygame.init()
    surf = pygame.image.load(reply["shot"])
    # Return teleports the square back to center x=100
    assert surf.get_at((100, 75))[:3] == (255, 200, 60)
