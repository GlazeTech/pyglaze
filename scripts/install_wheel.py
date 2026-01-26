# install_wheel.py
import subprocess
from pathlib import Path

wheels = list(Path.cwd().glob("dist/*.whl"))
if wheels:
    subprocess.check_call(["uv", "pip", "install", str(wheels[0])])  # noqa: S603, S607
else:
    msg = "No .whl files found in the dist directory."
    raise FileNotFoundError(msg)
