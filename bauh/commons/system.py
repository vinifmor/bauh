import os
import re
import subprocess
import sys
import time
from io import StringIO
from subprocess import PIPE
from typing import List, Tuple, Set, Dict, Optional, Iterable, Union, IO, Any

# default environment variables for subprocesses.
from bauh.api.abstract.handler import ProcessWatcher

PY_VERSION = "{}.{}".format(sys.version_info.major, sys.version_info.minor)
GLOBAL_PY_LIBS = '/usr/lib/python{}'.format(PY_VERSION)

PATH = os.getenv('PATH')
DEFAULT_LANG = ''

GLOBAL_INTERPRETER_PATH = ':'.join(PATH.split(':')[1:])

if GLOBAL_PY_LIBS not in PATH:
    PATH = '{}:{}'.format(GLOBAL_PY_LIBS, PATH)

USE_GLOBAL_INTERPRETER = bool(os.getenv('VIRTUAL_ENV'))

RE_SUDO_OUTPUT = re.compile(r'[sudo]\s*[\w\s]+:\s*')


def gen_env(global_interpreter: bool = USE_GLOBAL_INTERPRETER, lang: Optional[str] = DEFAULT_LANG,
            extra_paths: Optional[Set[str]] = None) -> dict:

    custom_env = dict(os.environ)

    if lang is not None:
        custom_env['LANG'] = lang

    if global_interpreter:  # to avoid subprocess calls to the virtualenv python interpreter instead of the global one.
        custom_env['PATH'] = GLOBAL_INTERPRETER_PATH

    else:
        custom_env['PATH'] = PATH

    if extra_paths:
        custom_env['PATH'] = ':'.join(extra_paths) + ':' + custom_env['PATH']

    return custom_env


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

    def __init__(self, cmd: Iterable[str], cwd: str = '.', expected_code: int = 0,
                 global_interpreter: bool = USE_GLOBAL_INTERPRETER, lang: Optional[str] = DEFAULT_LANG, root_password: Optional[str] = None,
                 extra_paths: Set[str] = None, error_phrases: Set[str] = None, wrong_error_phrases: Set[str] = None,
                 shell: bool = False, success_phrases: Set[str] = None, extra_env: Optional[Dict[str, str]] = None,
                 custom_user: Optional[str] = None, preserve_env: Optional[Set] = None):
        pwdin, final_cmd = None, []

        self.shell = shell

        if custom_user:
            final_cmd.extend(['runuser', '-u', custom_user, '--'])
        elif isinstance(root_password, str):
            final_cmd.extend(['sudo', '-S'])

            if preserve_env:
                for var in preserve_env:
                    final_cmd.append(f'--preserve-env={var}')

            pwdin = self._new(['echo', root_password], cwd, global_interpreter, lang).stdout

        final_cmd.extend(cmd)

        self.instance = self._new(final_cmd, cwd, global_interpreter, lang=lang, stdin=pwdin,
                                  extra_paths=extra_paths, extra_env=extra_env)
        self.expected_code = expected_code
        self.error_phrases = error_phrases
        self.wrong_error_phrases = wrong_error_phrases
        self.success_phrases = success_phrases

    def _new(self, cmd: List[str], cwd: str, global_interpreter: bool, lang: Optional[str], stdin = None,
             extra_paths: Set[str] = None, extra_env: Optional[Dict[str, str]] = None) -> subprocess.Popen:

        env = gen_env(global_interpreter=global_interpreter, lang=lang, extra_paths=extra_paths)

        if extra_env:
            for var, val in extra_env.items():
                env[var] = val

        args = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "stdin": stdin if stdin else subprocess.DEVNULL,
            "bufsize": -1,
            "cwd": cwd,
            "env": env,
            "shell": self.shell
        }

        return subprocess.Popen(args=[' '.join(cmd)] if self.shell else cmd, **args)


class ProcessHandler:

    """
    It handles a process execution and notifies a specified watcher.
    """

    def __init__(self, watcher: ProcessWatcher = None):
        self.watcher = watcher

    def _notify_watcher(self, msg: str, as_substatus: bool = False):
        if self.watcher:
            self.watcher.print(msg)

            if as_substatus:
                self.watcher.change_substatus(msg)

    def handle(self, process: SystemProcess, error_output: StringIO = None, output_handler=None) -> bool:
        self._notify_watcher(' '.join(process.subproc.args) + '\n')

        already_succeeded = False

        if not process.skip_stdout:
            for output in process.subproc.stdout:

                try:
                    line = output.decode().strip()
                except UnicodeDecodeError:
                    line = None

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
                try:
                    line = output.decode().strip()
                except UnicodeDecodeError:
                    line = None

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

    def handle_simple(self, proc: SimpleProcess, output_handler=None, notify_watcher: bool = True,
                      output_as_substatus: bool = False) -> Tuple[bool, str]:
        if notify_watcher:
            self._notify_watcher((proc.instance.args if isinstance(proc.instance.args, str) else ' '.join(proc.instance.args)) + '\n')

        output = StringIO()
        for o in proc.instance.stdout:
            if o:
                try:
                    line = o.decode()
                except UnicodeDecodeError:
                    continue

                if line.startswith('[sudo]'):
                    line = RE_SUDO_OUTPUT.split(line)[1]

                output.write(line)

                line = line.strip()

                if line:
                    if output_handler:
                        output_handler(line)

                    if notify_watcher:
                        self._notify_watcher(line, as_substatus=output_as_substatus)

        proc.instance.wait()
        output.seek(0)

        success = proc.instance.returncode == proc.expected_code
        string_output = output.read()

        if proc.success_phrases:
            for phrase in proc.success_phrases:
                if phrase in string_output:
                    success = True
                    break

        if not success and proc.wrong_error_phrases:
            for phrase in proc.wrong_error_phrases:
                if phrase in string_output:
                    success = True
                    break

        if success and proc.error_phrases:
            for phrase in proc.error_phrases:
                if phrase in string_output:
                    success = False
                    break

        return success, string_output


def run_cmd(cmd: str, expected_code: int = 0, ignore_return_code: bool = False, print_error: bool = True,
            cwd: str = '.', global_interpreter: bool = USE_GLOBAL_INTERPRETER, extra_paths: Set[str] = None,
            custom_user: Optional[str] = None, lang: Optional[str] = DEFAULT_LANG) -> Optional[str]:
    """
    runs a given command and returns its default output
    :return:
    """
    args = {
        "shell": True,
        "stdout": PIPE,
        "env": gen_env(global_interpreter=global_interpreter, lang=lang, extra_paths=extra_paths),
        'cwd': cwd
    }

    if not print_error:
        args["stderr"] = subprocess.DEVNULL

    final_cmd = f"runuser -u {custom_user} -- {cmd}" if custom_user else cmd
    res = subprocess.run(final_cmd, **args)

    if ignore_return_code or res.returncode == expected_code:
        try:
            return res.stdout.decode()
        except UnicodeDecodeError:
            pass


def new_subprocess(cmd: Iterable[str], cwd: str = '.', shell: bool = False, stdin: Optional[Union[None, int, IO[Any]]] = None,
                   global_interpreter: bool = USE_GLOBAL_INTERPRETER, lang: Optional[str] = DEFAULT_LANG,
                   extra_paths: Set[str] = None, custom_user: Optional[str] = None) -> subprocess.Popen:
    args = {
        "stdout": PIPE,
        "stderr": PIPE,
        "cwd": cwd,
        "shell": shell,
        "env": gen_env(global_interpreter, lang, extra_paths),
        "stdin": stdin if stdin else subprocess.DEVNULL
    }

    final_cmd = ['runuser', '-u', custom_user, '--', *cmd] if custom_user else cmd
    return subprocess.Popen(final_cmd, **args)


def new_root_subprocess(cmd: Iterable[str], root_password: Optional[str], cwd: str = '.',
                        global_interpreter: bool = USE_GLOBAL_INTERPRETER, lang: str = DEFAULT_LANG,
                        extra_paths: Set[str] = None, shell: bool = False) -> subprocess.Popen:
    pwdin, final_cmd = subprocess.DEVNULL, []

    if isinstance(root_password, str):
        final_cmd.extend(['sudo', '-S'])
        pwdin = new_subprocess(['echo', root_password], global_interpreter=global_interpreter, lang=lang).stdout

    final_cmd.extend(cmd)

    if shell:
        final_cmd = ' '.join(final_cmd)

    return subprocess.Popen(final_cmd, stdin=pwdin, stdout=PIPE, stderr=PIPE, cwd=cwd,
                            env=gen_env(global_interpreter, lang, extra_paths), shell=shell)


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


def run(cmd: List[str], success_code: int = 0, custom_user: Optional[str] = None) -> Tuple[bool, str]:
    final_cmd = ['runuser', '-u', custom_user, '--', *cmd] if custom_user else cmd
    p = subprocess.run(final_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)

    try:
        output = p.stdout.decode()
    except UnicodeDecodeError:
        output = ''

    return p.returncode == success_code, output


def check_active_services(*names: str) -> Dict[str, bool]:
    output = run_cmd('systemctl is-active {}'.format(' '.join(names)), print_error=False)

    if not output:
        return {n: False for n in names}
    else:
        status = output.split('\n')
        return {s: status[i].strip().lower() == 'active' for i, s in enumerate(names) if s}


def check_enabled_services(*names: str) -> Dict[str, bool]:
    output = run_cmd('systemctl is-enabled {}'.format(' '.join(names)), print_error=False)

    if not output:
        return {n: False for n in names}
    else:
        status = output.split('\n')
        return {s: status[i].strip().lower() == 'enabled' for i, s in enumerate(names) if s}


def execute(cmd: str, shell: bool = False, cwd: Optional[str] = None, output: bool = True, custom_env: Optional[dict] = None,
            stdin: bool = True, custom_user: Optional[str] = None) -> Tuple[int, Optional[str]]:

    final_cmd = f"runuser -u {custom_user} -- {cmd}" if custom_user else cmd

    params = {
        'args': final_cmd.split(' ') if not shell else [final_cmd],
        'stdout': subprocess.PIPE if output else subprocess.DEVNULL,
        'stderr': subprocess.STDOUT if output else subprocess.DEVNULL,
        'shell': shell
    }

    if not stdin:
        params['stdin'] = subprocess.DEVNULL

    if cwd is not None:
        params['cwd'] = cwd

    if custom_env is not None:
        params['env'] = custom_env

    p = subprocess.run(**params)

    output = None
    if p.stdout:
        try:
            output = p.stdout.decode()
        except UnicodeDecodeError:
            output = None

    return p.returncode, output
