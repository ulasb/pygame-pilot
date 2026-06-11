"""
pygame-pilot controller CLI (stdlib only; runs with any python3).

    pilot start [--session DIR] [--python BIN] [--cwd DIR] [--headed]
                -- <app.py> [app args...]
    pilot cmd   [--session DIR] '<json>'
    pilot adv   [--session DIR] N [--down k,k] [--up k,k] [--tap k,k]
                [--shot NAME]
    pilot shot  [--session DIR] [NAME]
    pilot info  [--session DIR]
    pilot quit  [--session DIR]
    pilot run   [--session DIR] ... --script FILE -- <app.py> [args...]

A session directory (default .pilot) holds the socket, the app's pid
and log, and captured frames/.
"""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def session_paths(session: str) -> dict:
    return {
        "dir": session,
        "sock": os.path.join(session, "pilot.sock"),
        "pid": os.path.join(session, "pilot.pid"),
        "log": os.path.join(session, "log.txt"),
    }


def send(session: str, cmd: dict, timeout: float = 60.0) -> dict:
    paths = session_paths(session)
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(timeout)
    conn.connect(paths["sock"])
    conn.sendall((json.dumps(cmd) + "\n").encode())
    data = conn.makefile("r").readline()
    conn.close()
    return json.loads(data)


def wait_for_socket(session: str, timeout: float = 20.0) -> bool:
    paths = session_paths(session)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(paths["sock"]):
            try:
                send(session, {"op": "info"}, timeout=5)
                return True
            except OSError:
                pass
        time.sleep(0.2)
    return False


def cmd_start(args, app_argv) -> int:
    paths = session_paths(args.session)
    os.makedirs(args.session, exist_ok=True)
    for stale in (paths["sock"],):
        if os.path.exists(stale):
            os.unlink(stale)

    env = dict(os.environ)
    env["PILOT_OUT"] = os.path.abspath(args.session)
    env["PILOT_SOCK"] = os.path.abspath(paths["sock"])
    env["PYTHONPATH"] = PKG_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUNBUFFERED"] = "1"
    if args.headed:
        env["PILOT_HEADED"] = "1"

    python = args.python or sys.executable
    target = app_argv[0]
    if not os.path.isabs(target) and not args.cwd:
        target = os.path.abspath(target)
        app_argv = [target] + app_argv[1:]

    log = open(paths["log"], "w")
    proc = subprocess.Popen(
        [python, "-m", "pygamepilot.bootstrap"] + app_argv,
        cwd=args.cwd or None, env=env, stdout=log, stderr=log,
        start_new_session=True)
    with open(paths["pid"], "w") as f:
        f.write(str(proc.pid))

    if not wait_for_socket(args.session):
        print("error: app did not come up; log follows", file=sys.stderr)
        log.flush()
        sys.stderr.write(open(paths["log"]).read())
        return 1
    info = send(args.session, {"op": "info"})
    print(json.dumps({"started": True, "pid": proc.pid, **info}))
    return 0


def cmd_stop(args) -> int:
    paths = session_paths(args.session)
    try:
        send(args.session, {"op": "quit"}, timeout=5)
    except OSError:
        pass
    try:
        pid = int(open(paths["pid"]).read())
        time.sleep(0.5)
        os.kill(pid, signal.SIGKILL)
    except (FileNotFoundError, ValueError, ProcessLookupError):
        pass
    print(json.dumps({"stopped": True}))
    return 0


def _print_reply(reply: dict) -> int:
    print(json.dumps(reply))
    return 1 if reply.get("error") else 0


def cmd_adv(args) -> int:
    cmd = {"op": "advance", "frames": args.frames}
    if args.down:
        cmd["down"] = args.down.split(",")
    if args.up:
        cmd["up"] = args.up.split(",")
    if args.tap:
        cmd["tap"] = args.tap.split(",")
    if args.shot is not None:
        cmd["shot"] = args.shot
    if args.record:
        cmd["record"] = args.record
    return _print_reply(send(args.session, cmd, timeout=300))


def cmd_run(args, app_argv) -> int:
    rc = cmd_start(args, app_argv)
    if rc:
        return rc
    try:
        steps = json.load(open(args.script))
        for i, step in enumerate(steps):
            reply = send(args.session, step)
            print(f"step {i}: {json.dumps(reply)}")
            if reply.get("error"):
                return 1
    finally:
        cmd_stop(args)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pilot")
    parser.add_argument("--session", default=".pilot")
    sub = parser.add_subparsers(dest="op", required=True)

    p_start = sub.add_parser("start")
    p_start.add_argument("--python")
    p_start.add_argument("--cwd")
    p_start.add_argument("--headed", action="store_true")

    p_run = sub.add_parser("run")
    p_run.add_argument("--python")
    p_run.add_argument("--cwd")
    p_run.add_argument("--headed", action="store_true")
    p_run.add_argument("--script", required=True)

    p_cmd = sub.add_parser("cmd")
    p_cmd.add_argument("json")

    p_adv = sub.add_parser("adv")
    p_adv.add_argument("frames", type=int)
    p_adv.add_argument("--down")
    p_adv.add_argument("--up")
    p_adv.add_argument("--tap")
    p_adv.add_argument("--shot", nargs="?", const="", default=None)
    p_adv.add_argument("--record", type=int, default=0,
                       help="screenshot every N frames during the advance")

    p_shot = sub.add_parser("shot")
    p_shot.add_argument("name", nargs="?")

    sub.add_parser("info")
    sub.add_parser("quit")
    sub.add_parser("stop")

    argv = list(sys.argv[1:] if argv is None else argv)
    app_argv = []
    if "--" in argv:
        split = argv.index("--")
        app_argv = argv[split + 1:]
        argv = argv[:split]
    args = parser.parse_args(argv)

    if args.op == "start":
        return cmd_start(args, app_argv)
    if args.op == "run":
        return cmd_run(args, app_argv)
    if args.op == "stop":
        return cmd_stop(args)
    if args.op == "quit":
        return _print_reply(send(args.session, {"op": "quit"}))
    if args.op == "info":
        return _print_reply(send(args.session, {"op": "info"}))
    if args.op == "shot":
        return _print_reply(send(
            args.session, {"op": "shot", "name": args.name}))
    if args.op == "adv":
        return cmd_adv(args)
    if args.op == "cmd":
        return _print_reply(send(args.session, json.loads(args.json)))
    return 2


if __name__ == "__main__":
    sys.exit(main())
