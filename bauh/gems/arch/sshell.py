from typing import Optional, Tuple

from bauh.commons.system import execute


def mkdir(dir_path: str, parent: bool = True, custom_user: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    code, output = execute(f'mkdir {"-p " if parent else ""}"{dir_path}"', shell=True, custom_user=custom_user)
    return code == 0, output
