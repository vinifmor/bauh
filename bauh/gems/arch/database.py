import logging
import os
import time
import traceback
from datetime import datetime
from logging import Logger
from pathlib import Path
from typing import Optional

from bauh.api.constants import CACHE_PATH
from bauh.commons.system import ProcessHandler

SYNC_FILE = '{}/arch/db_sync'.format(CACHE_PATH)


def should_sync(arch_config: dict, aur_supported: bool, handler: Optional[ProcessHandler], logger: logging.Logger):
    if aur_supported or arch_config['repositories']:
        if os.path.exists(SYNC_FILE):
            with open(SYNC_FILE) as f:
                sync_file = f.read()

            try:
                sync_time = datetime.fromtimestamp(int(sync_file))
                now = datetime.now()

                if now > sync_time and now.day != sync_time.day:
                    logger.info("Package databases synchronization out of date")
                else:
                    msg = "Package databases already synchronized"
                    logger.info(msg)
                    if handler:
                        handler.watcher.print(msg)
                    return False
            except:
                logger.warning("Could not convert the database synchronization time from '{}".format(SYNC_FILE))
                traceback.print_exc()
        return True
    else:
        msg = "Package databases synchronization disabled"
        if handler:
            handler.watcher.print(msg)
        logger.info(msg)
        return False


def register_sync(logger: Logger):
    try:
        Path('/'.join(SYNC_FILE.split('/')[0:-1])).mkdir(parents=True, exist_ok=True)
        with open(SYNC_FILE, 'w+') as f:
            f.write(str(int(time.time())))
    except:
        logger.error("Could not write to database sync file '{}'".format(SYNC_FILE))
        traceback.print_exc()
