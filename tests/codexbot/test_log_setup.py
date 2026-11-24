"""stderr filtering drops macOS child-process noise, keeps everything else."""

import subprocess
import sys

CHILD = r"""
import os, time
from codexbot.log_setup import _filter_stderr
_filter_stderr()
os.write(2, b"python3(123) MallocStackLogging: can't turn off malloc stack logging because it was not enabled.\n")
os.write(2, b"Traceback: real problem\n")
# A child process inherits the filtered fd 2 too.
os.system("echo 'python3(124) MallocStackLogging: can'\"'\"'t turn off malloc stack logging x' >&2; echo child-ok >&2")
time.sleep(0.3)
"""


def test_noise_is_dropped_and_real_output_kept():
    result = subprocess.run(
        [sys.executable, "-c", CHILD], capture_output=True, timeout=20
    )
    err = result.stderr.decode()
    assert "MallocStackLogging" not in err
    assert "Traceback: real problem" in err
    assert "child-ok" in err
