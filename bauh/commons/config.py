import os
from pathlib import Path

import yaml

from bauh.commons import util


def read_config(file_path: str, template: dict, update_file: bool = False) -> dict:
    if not os.path.exists(file_path):
        Path(file_path).mkdir(parents=True, exist_ok=True)

        with open(file_path, 'w+') as f:
            f.write(yaml.dump(template))

    else:
        with open(file_path) as f:
            local_config = yaml.safe_load(f.read())

        if local_config:
            util.deep_update(template, local_config)

        if update_file:
            with open(file_path, 'w+') as f:
                f.write(yaml.dump(template))

    return template
