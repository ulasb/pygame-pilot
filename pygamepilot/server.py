"""
Command server running inside the target process.

Listens on a Unix domain socket; each connection carries one JSON
command and receives one JSON reply. Commands execute while the app is
blocked at the frame gate, so reads of the display surface are stable.

Commands (op):
  advance  {frames=1, down=[], up=[], tap=[], shot=null}
           apply input changes, let the app present N frames, then
           (optionally) save a screenshot. Returns {frame, shot}.
  shot     {name=null}  save a screenshot of the current frame.
  info     {}           frame counter, display size, title.
  freerun  {enable}     un-gate frames (real-time); disable re-gates.
  quit     {}           ask the app to exit.
"""

import json
import os
import socket
import threading
import traceback

import pygame

from . import patches


def _screenshot(out_dir: str, name: str | None) -> str | None:
    surface = pygame.display.get_surface()
    if surface is None:
        return None
    frame = patches.STATE.frame
    fname = name or f"frame_{frame:06d}.png"
    if not fname.endswith(".png"):
        fname += ".png"
    path = os.path.join(out_dir, "frames", fname)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pygame.image.save(surface, path)
    return path


def _handle(cmd: dict, out_dir: str) -> dict:
    st = patches.STATE
    op = cmd.get("op", "advance")

    if op == "info":
        surface = pygame.display.get_surface()
        return {
            "frame": st.frame,
            "size": list(surface.get_size()) if surface else None,
            "title": pygame.display.get_caption()[0] if surface else None,
            "held": sorted(pygame.key.name(k) for k in st.held),
        }

    if op == "shot":
        return {"frame": st.frame,
                "shot": _screenshot(out_dir, cmd.get("name"))}

    if op == "freerun":
        st.free_run = bool(cmd.get("enable", True))
        if st.free_run:
            st.grant(1)
        return {"frame": st.frame, "free_run": st.free_run}

    if op == "quit":
        patches.request_quit()
        return {"ok": True}

    if op == "advance":
        for key in cmd.get("up", []):
            patches.release(key)
        for key in cmd.get("down", []):
            patches.press(key)
        for key in cmd.get("tap", []):
            patches.press(key)
        frames = int(cmd.get("frames", 1))
        taps = list(cmd.get("tap", []))
        if taps and frames < 2:
            frames = 2
        record = int(cmd.get("record", 0))  # screenshot every N frames
        shots = []

        def advance(n):
            while n > 0:
                step = min(n, record) if record else n
                st.grant(step)
                st.wait_consumed()
                n -= step
                if record:
                    shots.append(_screenshot(out_dir, None))

        if frames > 0:
            if taps:
                # release tapped keys after a couple of frames so both the
                # event queue and held-state observers see them
                advance(2)
                for key in taps:
                    patches.release(key)
                advance(frames - 2)
            else:
                advance(frames)
        shot = None
        if cmd.get("shot") is not None:
            shot = _screenshot(out_dir, cmd.get("shot") or None)
        reply = {"frame": st.frame, "shot": shot}
        if shots:
            reply["shots"] = shots
        return reply

    return {"error": f"unknown op {op!r}"}


def _serve(sock_path: str, out_dir: str) -> None:
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        os.unlink(sock_path)
    except FileNotFoundError:
        pass
    server.bind(sock_path)
    server.listen(8)
    while True:
        conn, _ = server.accept()
        try:
            data = conn.makefile("r").readline()
            if not data:
                continue
            try:
                reply = _handle(json.loads(data), out_dir)
            except Exception as exc:  # surface errors to the controller
                reply = {"error": f"{exc.__class__.__name__}: {exc}",
                         "trace": traceback.format_exc()}
            conn.sendall((json.dumps(reply) + "\n").encode())
        finally:
            conn.close()


def start(sock_path: str, out_dir: str) -> None:
    thread = threading.Thread(
        target=_serve, args=(sock_path, out_dir), daemon=True)
    thread.start()
