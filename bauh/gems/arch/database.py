import time
import traceback
from logging import Logger
from pathlib import Path

from bauh.api.constants import TEMP_DIR

DB_SYNC_FILE = '{}/arch/sync'.format(TEMP_DIR)


def register_sync(logger: Logger):
    try:
        Path('/'.join(DB_SYNC_FILE.split('/')[0:-1])).mkdir(parents=True, exist_ok=True)
        with open(DB_SYNC_FILE, 'w+') as f:
            f.write(str(int(time.time())))
    except:
        logger.error("Could not write to database sync file '{}'".format(DB_SYNC_FILE))
        traceback.print_exc()
