import os
import subprocess
from typing import List

from fpakman import __app_name__
from fpakman.core import resource


class FpakmanProcess:

    def __init__(self, subproc: subprocess.Popen, success_phrase: str = None, wrong_error_phrase: str = '[sudo] password for'):
        self.subproc = subproc
        self.success_pgrase = success_phrase
        self.wrong_error_phrase = wrong_error_phrase


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
    os.system("notify-send -a {} {} '{}'".format(__app_name__, "-i {}".format(icon_path) if icon_path else '', msg))


def cmd_as_root(cmd: List[str], root_password: str) -> subprocess.Popen:
    pwdin, final_cmd = None, []

    if root_password is not None:
        final_cmd.extend(['sudo', '-S'])
        pwdin = stream_cmd(['echo', root_password])

    final_cmd.extend(cmd)
    return subprocess.Popen(final_cmd, stdin=pwdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
