import shutil


def is_available() -> bool:
    return bool(shutil.which('npm'))
