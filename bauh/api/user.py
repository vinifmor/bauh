import os
from typing import Optional


def is_root(user_id: Optional[int] = None):
    return user_id == 0 if user_id is not None else os.getuid() == 0
