"""pygame-pilot: drive, step, and observe unmodified pygame apps.

A small bootstrap shim launches the target app with pygame patched so
that an external controller (a human, a test script, or an AI agent)
can inject input, advance the game a precise number of frames, and
capture exactly what is on the display surface.
"""

__version__ = "0.1.0"
