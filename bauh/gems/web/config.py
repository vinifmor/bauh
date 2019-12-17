import os
from pathlib import Path

import yaml

from bauh.api.constants import CONFIG_PATH
from bauh.commons import util
from bauh.gems.web import CONFIG_FILE


def read_config(update_file: bool = False) -> dict:
    default_config = {
        'environment': {
            'system': False,
            'electron': {'version': None}
        }
    }
    if not os.path.exists(CONFIG_FILE):
        Path(CONFIG_PATH).mkdir(parents=True, exist_ok=True)

        with open(CONFIG_FILE, 'w+') as f:
            f.write(yaml.dump(default_config))

    else:
        with open(CONFIG_FILE) as f:
            local_config = yaml.safe_load(f.read())

        util.deep_update(default_config, local_config)

        if update_file:
            with open(CONFIG_FILE, 'w+') as f:
                f.write(yaml.dump(default_config))

    return default_config
