import os
import subprocess
from typing import List

from fpakman.core import resource


def run_cmd(cmd: str, expected_code: int = 0, ignore_return_code: bool = False, print_error: bool = True) -> str:
    args = {
        "shell": True,
        "stdout": subprocess.PIPE,
        "env": {'LANG': 'en'}
    }

    if not print_error:
        args["stderr"] = subprocess.DEVNULL

    res = subprocess.run(cmd, **args)
    return res.stdout.decode() if ignore_return_code or res.returncode == expected_code else None


def stream_cmd(cmd: List[str]):
    return cmd_to_subprocess(cmd).stdout


def cmd_to_subprocess(cmd: List[str]):
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={'LANG': 'en'})


def notify_user(msg: str, icon_path: str = resource.get_path('img/logo.svg')):
    os.system("notify-send {} '{}'".format("-i {}".format(icon_path) if icon_path else '', msg))
