import os
import sys

# When frozen by PyInstaller, all paths resolve relative to the exe.
# When running from source, resolve relative to the project root.
if getattr(sys, "frozen", False):
    ROOT = os.path.dirname(sys.executable)
else:
    ROOT = os.path.join(os.path.dirname(__file__), "..")

ROOT = os.path.abspath(ROOT)

def data(*parts):
    return os.path.join(ROOT, "data", *parts)

def assets(*parts):
    return os.path.join(ROOT, "assets", *parts)

def overlay(*parts):
    return os.path.join(ROOT, "overlay", *parts)

def games(*parts):
    return os.path.join(ROOT, "games", *parts)
