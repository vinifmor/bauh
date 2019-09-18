import os
import subprocess
from subprocess import PIPE
from typing import List

# default environment variables for subprocesses.
from bauh.api.abstract.handler import ProcessWatcher

GLOBAL_INTERPRETER_PATH = ':'.join(os.getenv('PATH').split(':')[1:])
USE_GLOBAL_INTERPRETER = bool(os.getenv('VIRTUAL_ENV'))


def gen_env(global_interpreter: bool) -> dict:
    res = {'LANG': 'en'}

    if global_interpreter:  # to avoid subprocess calls to the virtualenv python interpreter instead of the global one.
        res['PATH'] = GLOBAL_INTERPRETER_PATH

    return res


class SystemProcess:

    """
    Represents a system process being executed.
    """

    def __init__(self, subproc: subprocess.Popen, success_phrase: str = None, wrong_error_phrase: str = '[sudo] password for', check_error_output: bool = True):
        self.subproc = subproc
        self.success_phrase = success_phrase
        self.wrong_error_phrase = wrong_error_phrase
        self.check_error_output = check_error_output

    def wait(self):
        self.subproc.wait()


class ProcessHandler:

    """
    It handles a process execution and notifies a specified watcher.
    """

    def __init__(self, watcher: ProcessWatcher = None):
        self.watcher = watcher

    def _notify_watcher(self, msg: str):
        if self.watcher:
            self.watcher.print(msg)

    def handle(self, process: SystemProcess) -> bool:
        self._notify_watcher(' '.join(process.subproc.args) + '\n')

        already_succeeded = False

        for output in process.subproc.stdout:
            line = output.decode().strip()
            if line:
                self._notify_watcher(line)

                if process.success_phrase and process.success_phrase in line:
                    already_succeeded = True

        if already_succeeded:
            return True

        for output in process.subproc.stderr:
            line = output.decode().strip()
            if line:
                self._notify_watcher(line)

                if process.check_error_output:
                    if process.wrong_error_phrase and process.wrong_error_phrase in line:
                        continue
                    else:
                        return False

        return process.subproc.returncode is None or process.subproc.returncode == 0


def run_cmd(cmd: str, expected_code: int = 0, ignore_return_code: bool = False, print_error: bool = True,
            cwd: str = '.', global_interpreter: bool = USE_GLOBAL_INTERPRETER) -> str:
    """
    runs a given command and returns its default output
    :param cmd:
    :param expected_code:
    :param ignore_return_code:
    :param print_error:
    :param global_interpreter
    :return:
    """
    args = {
        "shell": True,
        "stdout": PIPE,
        "env": gen_env(global_interpreter),
        'cwd': cwd
    }

    if not print_error:
        args["stderr"] = subprocess.DEVNULL

    res = subprocess.run(cmd, **args)
    return res.stdout.decode() if ignore_return_code or res.returncode == expected_code else None


def new_subprocess(cmd: List[str], cwd: str = '.', shell: bool = False, stdin = None,
                   global_interpreter: bool = USE_GLOBAL_INTERPRETER) -> subprocess.Popen:
    args = {
        "stdout": PIPE,
        "stderr": PIPE,
        "cwd": cwd,
        "shell": shell,
        "env": gen_env(global_interpreter)
    }

    if input:
        args['stdin'] = stdin

    return subprocess.Popen(cmd, **args)


def new_root_subprocess(cmd: List[str], root_password: str, cwd: str = '.',
                        global_interpreter: bool = USE_GLOBAL_INTERPRETER) -> subprocess.Popen:
    pwdin, final_cmd = None, []

    if root_password is not None:
        final_cmd.extend(['sudo', '-S'])
        pwdin = new_subprocess(['echo', root_password], global_interpreter=global_interpreter).stdout

    final_cmd.extend(cmd)
    return subprocess.Popen(final_cmd, stdin=pwdin, stdout=PIPE, stderr=PIPE, cwd=cwd)


def notify_user(msg: str, app_name: str, icon_path: str):
    os.system("notify-send -a {} {} '{}'".format(app_name, "-i {}".format(icon_path) if icon_path else '', msg))
