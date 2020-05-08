import os
import subprocess
import sys
import time
from io import StringIO
from subprocess import PIPE
from typing import List, Tuple, Set

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

SIZE_MULTIPLIERS = ((0.001, 'Kb'), (0.000001, 'Mb'), (0.000000001, 'Gb'), (0.000000000001, 'Tb'))


def gen_env(global_interpreter: bool, lang: str = DEFAULT_LANG, extra_paths: Set[str] = None) -> dict:
    res = {}

    if lang:
        res['LANG'] = lang

    if global_interpreter:  # to avoid subprocess calls to the virtualenv python interpreter instead of the global one.
        res['PATH'] = GLOBAL_INTERPRETER_PATH
    else:
        res['PATH'] = PATH

    if extra_paths:
        res['PATH'] = ':'.join(extra_paths) + ':' + res['PATH']

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

    def __init__(self, cmd: List[str], cwd: str = '.', expected_code: int = 0,
                 global_interpreter: bool = USE_GLOBAL_INTERPRETER, lang: str = DEFAULT_LANG, root_password: str = None,
                 extra_paths: Set[str] = None, error_phrases: Set[str] = None):
        pwdin, final_cmd = None, []

        if root_password is not None:
            final_cmd.extend(['sudo', '-S'])
            pwdin = self._new(['echo', root_password], cwd, global_interpreter, lang).stdout

        final_cmd.extend(cmd)

        self.instance = self._new(final_cmd, cwd, global_interpreter, lang, stdin=pwdin, extra_paths=extra_paths)
        self.expected_code = expected_code
        self.error_phrases = error_phrases

    def _new(self, cmd: List[str], cwd: str, global_interpreter: bool, lang: str, stdin = None, extra_paths: Set[str] = None) -> subprocess.Popen:

        args = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "bufsize": -1,
            "cwd": cwd,
            "env": gen_env(global_interpreter, lang, extra_paths=extra_paths)
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

    def handle(self, process: SystemProcess, error_output: StringIO = None, output_handler=None) -> bool:
        self._notify_watcher(' '.join(process.subproc.args) + '\n')

        already_succeeded = False

        if not process.skip_stdout:
            for output in process.subproc.stdout:
                line = output.decode().strip()
                if line:
                    self._notify_watcher(line)

                    if output_handler:
                        output_handler(line)

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

                    if output_handler:
                        output_handler(line)

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

    def handle_simple(self, proc: SimpleProcess, output_handler=None) -> Tuple[bool, str]:
        self._notify_watcher(' '.join(proc.instance.args) + '\n')

        output = StringIO()
        for o in proc.instance.stdout:
            if o:
                line = o.decode()

                output.write(line)

                line = line.strip()

                if line:
                    if output_handler:
                        output_handler(line)
                        
                    self._notify_watcher(line)

        proc.instance.wait()
        output.seek(0)

        success = proc.instance.returncode == proc.expected_code
        string_output = output.read()

        if proc.error_phrases:
            for phrase in proc.error_phrases:
                if phrase in string_output:
                    success = False
                    break
        return success, string_output


def run_cmd(cmd: str, expected_code: int = 0, ignore_return_code: bool = False, print_error: bool = True,
            cwd: str = '.', global_interpreter: bool = USE_GLOBAL_INTERPRETER, extra_paths: Set[str] = None) -> str:
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
        "env": gen_env(global_interpreter, extra_paths=extra_paths),
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


def get_dir_size(start_path='.'):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)

            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)

    return total_size


def get_human_size_str(size) -> str:
    int_size = int(size)

    if int_size == 0:
        return '0'

    for m in SIZE_MULTIPLIERS:
        size_str = str(int_size * m[0])

        if len(size_str.split('.')[0]) < 4:
            return '{0:.2f}'.format(float(size_str)) + ' ' + m[1]
    return str(int_size)


def run(cmd: List[str], success_code: int = 0) -> Tuple[bool, str]:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.returncode == success_code, p.stdout.decode()
