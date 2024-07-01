# install_wheel.py
import subprocess
import sys
from pathlib import Path

wheels = list(Path.cwd().glob("dist/*.whl"))
if wheels:
    subprocess.check_call([sys.executable, "-m", "pip", "install", wheels[0]])  # noqa: S603
else:
    msg = "No .whl files found in the dist directory."
    raise FileNotFoundError(msg)
