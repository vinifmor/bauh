import os
import subprocess
import sys
import time
from io import StringIO
from subprocess import PIPE
from typing import List, Tuple

# default environment variables for subprocesses.
from bauh.api.abstract.handler import ProcessWatcher

PY_VERSION = "{}.{}".format(sys.version_info.major, sys.version_info.minor)
GLOBAL_PY_LIBS = '/usr/lib/python{}'.format(PY_VERSION)

PATH = os.getenv('PATH')
DEFAULT_LANG = 'en'

GLOBAL_INTERPRETER_PATH = ':'.join(PATH.split(':')[1:])

if GLOBAL_PY_LIBS not in PATH:
    PATH = '{}:{}'.format(GLOBAL_PY_LIBS, PATH)

USE_GLOBAL_INTERPRETER = bool(os.getenv('VIRTUAL_ENV'))


def gen_env(global_interpreter: bool, lang: str = DEFAULT_LANG) -> dict:
    res = {}

    if lang:
        res['LANG'] = lang

    if global_interpreter:  # to avoid subprocess calls to the virtualenv python interpreter instead of the global one.
        res['PATH'] = GLOBAL_INTERPRETER_PATH
    else:
        res['PATH'] = PATH

    return res


class SystemProcess:

    """
    Represents a system process being executed.
    """

    def __init__(self, subproc: subprocess.Popen, success_phrases: List[str] = None, wrong_error_phrase: str = '[sudo] password for',
                 check_error_output: bool = True, skip_stdout: bool = False, output_delay: float = None):
        self.subproc = subproc
        self.success_phrases = success_phrases
        self.wrong_error_phrase = wrong_error_phrase
        self.check_error_output = check_error_output
        self.skip_stdout = skip_stdout
        self.output_delay = output_delay

    def wait(self):
        self.subproc.wait()


class SimpleProcess:

    def __init__(self, cmd: List[str], cwd: str = '.', expected_code: int = None, global_interpreter: bool = USE_GLOBAL_INTERPRETER,
                 lang: str = DEFAULT_LANG, root_password: str = None):
        pwdin, final_cmd = None, []

        if root_password is not None:
            final_cmd.extend(['sudo', '-S'])
            pwdin = self._new(['echo', root_password], cwd, global_interpreter, lang).stdout

        final_cmd.extend(cmd)

        self.instance = self._new(final_cmd, cwd, global_interpreter, lang, stdin=pwdin)
        self.expected_code = expected_code

    def _new(self, cmd: List[str], cwd: str, global_interpreter: bool, lang: str, stdin = None) -> subprocess.Popen:

        args = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "bufsize": -1,
            "cwd": cwd,
            "env": gen_env(global_interpreter, lang)
        }

        if stdin:
            args['stdin'] = stdin

        return subprocess.Popen(cmd, **args)


class ProcessHandler:

    """
    It handles a process execution and notifies a specified watcher.
    """

    def __init__(self, watcher: ProcessWatcher = None):
        self.watcher = watcher

    def _notify_watcher(self, msg: str):
        if self.watcher:
            self.watcher.print(msg)

    def handle(self, process: SystemProcess, error_output: StringIO = None) -> bool:
        self._notify_watcher(' '.join(process.subproc.args) + '\n')

        already_succeeded = False

        if not process.skip_stdout:
            for output in process.subproc.stdout:
                line = output.decode().strip()
                if line:
                    self._notify_watcher(line)

                    if process.success_phrases and [p in line for p in process.success_phrases]:
                        already_succeeded = True

                if not already_succeeded and process.output_delay:
                    time.sleep(process.output_delay)

            if already_succeeded:
                return True

        for output in process.subproc.stderr:
            if output:
                line = output.decode().strip()
                if line:
                    self._notify_watcher(line)

                    if error_output is not None:
                        error_output.write(line)

                    if process.check_error_output:
                        if process.wrong_error_phrase and process.wrong_error_phrase in line:
                            continue
                        else:
                            return False
                    elif process.skip_stdout and process.success_phrases and [p in line for p in process.success_phrases]:
                        already_succeeded = True

                if not already_succeeded and process.output_delay:
                    time.sleep(process.output_delay)

        if already_succeeded:
            return True

        return process.subproc.returncode is None or process.subproc.returncode == 0

    def handle_simple(self, proc: SimpleProcess) -> Tuple[bool, str]:
        self._notify_watcher(' '.join(proc.instance.args) + '\n')

        output = StringIO()
        for o in proc.instance.stdout:
            if o:
                line = o.decode()
                output.write(line)

                line = line.strip()

                if line:
                    self._notify_watcher(line)

        output.seek(0)
        return proc.instance.returncode == proc.expected_code, output.read()


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
                   global_interpreter: bool = USE_GLOBAL_INTERPRETER, lang: str = DEFAULT_LANG) -> subprocess.Popen:
    args = {
        "stdout": PIPE,
        "stderr": PIPE,
        "cwd": cwd,
        "shell": shell,
        "env": gen_env(global_interpreter, lang)
    }

    if input:
        args['stdin'] = stdin

    return subprocess.Popen(cmd, **args)


def new_root_subprocess(cmd: List[str], root_password: str, cwd: str = '.',
                        global_interpreter: bool = USE_GLOBAL_INTERPRETER, lang: str = DEFAULT_LANG) -> subprocess.Popen:
    pwdin, final_cmd = None, []

    if root_password is not None:
        final_cmd.extend(['sudo', '-S'])
        pwdin = new_subprocess(['echo', root_password], global_interpreter=global_interpreter, lang=lang).stdout

    final_cmd.extend(cmd)

    return subprocess.Popen(final_cmd, stdin=pwdin, stdout=PIPE, stderr=PIPE, cwd=cwd, env=gen_env(global_interpreter, lang))


def notify_user(msg: str, app_name: str, icon_path: str):
    os.system("notify-send -a {} {} '{}'".format(app_name, "-i {}".format(icon_path) if icon_path else '', msg))
