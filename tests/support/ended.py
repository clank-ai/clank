"""Test support: whether a process has ended, for the tests that cancel a command and check what it started is gone."""

import time

import psutil


def ended(pid: int) -> bool:
    """Whether the process is gone or a zombie (ended, only waiting to be reaped)."""
    try:
        return psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return True


def wait_ended(pid: int, seconds: float = 10) -> bool:
    """Whether the process ends within `seconds`."""
    deadline = time.monotonic() + seconds
    while not ended(pid):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.1)
    return True
