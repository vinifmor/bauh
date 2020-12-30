import os
import traceback
from abc import abstractmethod, ABC
from pathlib import Path
from threading import Thread
from typing import Optional

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


class ConfigManager(ABC):

    @abstractmethod
    def read_config(self) -> Optional[dict]:
        pass

    @abstractmethod
    def get_default_config(self) -> dict:
        pass

    @abstractmethod
    def is_config_cached(self) -> bool:
        pass

    def get_config(self) -> dict:
        default_config = self.get_default_config()

        if default_config:
            cached_config = self.read_config()

            if cached_config:
                self.merge_config(default_config, cached_config)

        return default_config

    @staticmethod
    def merge_config(base_config: dict, current_config: dict):
        util.deep_update(base_config, current_config)

    @abstractmethod
    def save_config(self, config_obj: dict):
        pass


class YAMLConfigManager(ConfigManager, ABC):

    def __init__(self, config_file_path: str):
        self.file_path = config_file_path

    def is_config_cached(self) -> bool:
        return os.path.exists(self.file_path)

    def read_config(self) -> Optional[dict]:
        if self.is_config_cached():
            with open(self.file_path) as f:
                local_config = yaml.safe_load(f.read())

            if local_config is not None:
                return local_config

    def save_config(self, config_obj: dict):
        if config_obj:
            config_dir = os.path.dirname(self.file_path)
            try:
                Path(config_dir).mkdir(parents=True, exist_ok=True)
            except OSError:
                traceback.print_exc()
                return

            try:
                with open(self.file_path, 'w+') as f:
                    f.write(yaml.dump(config_obj))
            except:
                traceback.print_exc()
