import os
from pathlib import Path

import yaml

from bauh.api.constants import CONFIG_PATH
from bauh.gems.web import CONFIG_FILE


def read_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        config = {'environment': {'system': False}}

        Path(CONFIG_PATH).mkdir(parents=True, exist_ok=True)

        with open(CONFIG_FILE, 'w+') as f:
            f.write(yaml.dump(config))
    else:
        with open(CONFIG_FILE) as f:
            config = yaml.safe_load(f.read())

    return config
