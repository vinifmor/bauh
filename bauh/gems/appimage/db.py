import os
import time


def acquire_lock(db_path: str):
    lock_path = db_path + '.lock'
    while True:
        if not os.path.exists(lock_path):
            open(lock_path, 'a').close()
            break
        else:
            time.sleep(0.0001)


def release_lock(db_path: str):
    lock_path = db_path + '.lock'
    if os.path.exists(lock_path):
        os.remove(lock_path)
