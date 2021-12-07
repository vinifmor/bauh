import multiprocessing
import os
import traceback
from pwd import getpwnam
from typing import Callable, Optional, TypeVar

R = TypeVar('R')


class CallAsUser:

    def __init__(self, target: Callable[[], R], user: str):
        self._target = target
        self._user = user

    def __call__(self, *args, **kwargs) -> R:
        try:
            os.setuid(getpwnam(self._user).pw_uid)
            return self._target()
        except:
            traceback.print_exc()


class WriteToFile:

    def __init__(self, file_path: str, content: str):
        self._file_path = file_path
        self._content = content

    def __call__(self, *args, **kwargs) -> bool:
        try:
            with open(self._file_path, 'w+') as f:
                f.write(self._content)

            return True
        except:
            traceback.print_exc()
            return False


def exec_as_user(target: Callable[[], R], user: Optional[str] = None) -> R:
    if user:
        with multiprocessing.Pool(1) as pool:
            return pool.apply(CallAsUser(target, user))
    else:
        return target()


def write_as_user(content: str, file_path: str, user: Optional[str] = None) -> bool:
    return exec_as_user(target=WriteToFile(file_path=file_path, content=content),
                        user=user)
