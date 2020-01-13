import os


def is_root():
    return os.getuid() == 0
