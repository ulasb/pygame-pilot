"""
Pygame monkeypatches installed inside the target process.

The core idea: the app's own `pygame.display.flip()` (or `update()`)
becomes the frame gate. After presenting a frame, the app blocks until
the controller grants more frames. While blocked, the controller can
inspect the display surface, so every screenshot is a frame boundary
the app itself produced.

Input is injected two ways at once, because pygame apps read keys two
ways: synthetic KEYDOWN/KEYUP events are posted to the event queue, and
`pygame.key.get_pressed()` is wrapped to overlay the controller's
currently-held keys (the SDL dummy driver never updates real key state).

Time is virtualized: `Clock.tick(fps)` doesn't sleep and returns the
nominal frame duration, and `pygame.time.get_ticks()` is derived from
the frame counter, so runs are deterministic and as fast as the
controller drives them.
"""

import threading

import pygame


class PilotState:
    def __init__(self):
        self.lock = threading.Condition()
        self.frame = 0           # frames presented so far
        self.allowance = 0       # frames the app may still present
        self.parked = False      # app is blocked inside the gate
        self.free_run = False    # don't gate frames (real-time mode)
        self.fps = 60            # last fps passed to Clock.tick
        self.held = set()        # key codes currently held down
        self.quitting = False

    # ---- controller side -------------------------------------------------
    def grant(self, frames: int) -> None:
        with self.lock:
            self.allowance += frames
            self.lock.notify_all()

    def wait_consumed(self, timeout: float = 30.0) -> bool:
        """Wait until the allowance is spent AND the app is parked at the
        gate again — i.e. the surface holds a complete, just-flipped
        frame and the app cannot touch it until the next grant."""
        with self.lock:
            return self.lock.wait_for(
                lambda: (self.allowance <= 0 and self.parked)
                or self.quitting or self.free_run, timeout)

    # ---- app side --------------------------------------------------------
    def gate(self) -> None:
        with self.lock:
            self.frame += 1
            if self.free_run or self.quitting:
                self.lock.notify_all()
                return
            self.parked = True
            self.lock.notify_all()
            self.lock.wait_for(
                lambda: self.allowance > 0 or self.free_run or self.quitting)
            if self.allowance > 0:
                self.allowance -= 1
            self.parked = False
            self.lock.notify_all()


STATE = PilotState()


class _HeldKeys:
    """get_pressed() result that overlays controller-held keys."""

    def __init__(self, real, held):
        self._real = real
        self._held = held

    def __getitem__(self, key):
        if key in self._held:
            return True
        try:
            return bool(self._real[key])
        except IndexError:
            return False

    def __len__(self):
        return len(self._real)


def install() -> PilotState:
    st = STATE

    real_flip = pygame.display.flip
    real_update = pygame.display.update

    def flip():
        result = real_flip()
        st.gate()
        return result

    def update(*args, **kwargs):
        result = real_update(*args, **kwargs)
        st.gate()
        return result

    pygame.display.flip = flip
    pygame.display.update = update

    real_get_pressed = pygame.key.get_pressed

    def get_pressed():
        try:
            real = real_get_pressed()
        except pygame.error:
            real = {}
        return _HeldKeys(real, set(st.held))

    pygame.key.get_pressed = get_pressed

    class PilotClock:
        """Non-sleeping Clock with deterministic timing."""

        def __init__(self):
            self._last_frame = st.frame

        def tick(self, framerate=0):
            if framerate:
                st.fps = framerate
            ms = int(1000 / (st.fps or 60))
            self._last_frame = st.frame
            return ms

        tick_busy_loop = tick

        def get_time(self):
            return int(1000 / (st.fps or 60))

        get_rawtime = get_time

        def get_fps(self):
            return float(st.fps or 60)

    pygame.time.Clock = PilotClock
    pygame.time.get_ticks = lambda: int(st.frame * 1000 / (st.fps or 60))
    pygame.time.delay = lambda ms: 0
    pygame.time.wait = lambda ms: 0

    return st


def key_code(name: str) -> int:
    """Resolve a friendly key name ('right', 'shift', 'a', 'return')."""
    aliases = {
        "shift": "left shift", "ctrl": "left ctrl", "alt": "left alt",
        "enter": "return", "esc": "escape",
    }
    return pygame.key.key_code(aliases.get(name, name))


def press(name: str) -> None:
    code = key_code(name)
    STATE.held.add(code)
    pygame.event.post(pygame.event.Event(
        pygame.KEYDOWN, key=code, mod=0, unicode=""))


def release(name: str) -> None:
    code = key_code(name)
    STATE.held.discard(code)
    pygame.event.post(pygame.event.Event(pygame.KEYUP, key=code, mod=0))


def request_quit() -> None:
    STATE.quitting = True
    try:
        pygame.event.post(pygame.event.Event(pygame.QUIT))
    except pygame.error:
        pass
    STATE.grant(10_000)  # let the app run out and exit
