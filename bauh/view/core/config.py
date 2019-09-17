import json
import os
from pathlib import Path
from typing import List

from bauh import __app_name__
from bauh.api.constants import HOME_PATH

CONFIG_PATH = '{}/.config/{}'.format(HOME_PATH, __app_name__)
FILE_PATH = '{}/config.json'.format(CONFIG_PATH)


class Configuration:

    def __init__(self, enabled_gems: List[str] = None, style: str = None):
        self.enabled_gems = enabled_gems
        self.style = style


def read() -> Configuration:
    if os.path.exists(FILE_PATH):
        with open(FILE_PATH) as f:
            config_file = f.read()

        return Configuration(**json.loads(config_file))

    return Configuration()


def save(config: Configuration):
    Path(CONFIG_PATH).mkdir(parents=True, exist_ok=True)

    with open(FILE_PATH, 'w+') as f:
        f.write(json.dumps(config.__dict__, indent=2))
