import os
from pathlib import Path
from threading import Thread

import yaml

from bauh.api.constants import CONFIG_PATH
from bauh.commons import util


def read_config(file_path: str, template: dict, update_file: bool = False, update_async: bool = False) -> dict:
    if not os.path.exists(file_path):
        Path(CONFIG_PATH).mkdir(parents=True, exist_ok=True)
        save_config(template, file_path)
    else:
        with open(file_path) as f:
            local_config = yaml.safe_load(f.read())

        if local_config:
            util.deep_update(template, local_config)

        if update_file:
            if update_async:
                Thread(target=save_config, args=(template, file_path), daemon=True).start()
            else:
                save_config(template, file_path)

    return template


def save_config(config: dict, file_path: str):
    with open(file_path, 'w+') as f:
        f.write(yaml.dump(config))
