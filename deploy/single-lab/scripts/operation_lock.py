"""Serialize operations which pause writers, including nested upgrade/rollback calls."""
import fcntl
import os
import sys
from pathlib import Path

if sys.argv[1] == "--inherited":
    try:
        inherited = int(os.environ["PLATFORM_MAINTENANCE_FD"])
        matching = os.path.samestat(os.fstat(inherited), os.stat(sys.argv[2]))
    except (KeyError, ValueError, OSError):
        matching = False
    sys.exit(0 if matching else 1)

path = Path(sys.argv[1])
path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    sys.exit("Another Platform maintenance operation is running. Try again later.")
os.set_inheritable(fd, True)
os.environ["PLATFORM_MAINTENANCE_FD"] = str(fd)
os.execv("/bin/bash", ["bash", *sys.argv[2:]])
