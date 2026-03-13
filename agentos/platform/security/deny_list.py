from __future__ import annotations

import platform
from pathlib import Path

_UNIX_DENY = [
    "/etc", "/usr", "/bin", "/sbin", "/boot",
    "/proc", "/sys", "/dev", "/var/run", "/var/log",
    "/lib", "/lib64",
]

_WIN_DENY = [
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "C:\\ProgramData",
]


def is_system_path(target: Path) -> bool:
    resolved = str(target.resolve())
    deny_list = _WIN_DENY if platform.system() == "Windows" else _UNIX_DENY
    for deny in deny_list:
        if platform.system() == "Windows":
            if resolved.lower().startswith(deny.lower()):
                return True
        else:
            if resolved == deny or resolved.startswith(deny + "/"):
                return True
    return False
