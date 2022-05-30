import os
import traceback
from datetime import datetime, timedelta
from logging import Logger
from pathlib import Path
from typing import Optional

import requests
import yaml

from bauh.api.http import HttpClient
from bauh.commons.util import map_timestamp_file
from bauh.gems.web import WEB_CACHE_DIR
from bauh.view.util.translation import I18n


class SuggestionsManager:

    def __init__(self, http_client: HttpClient, logger: Logger, i18n: I18n, file_url: Optional[str]):
        self.http_client = http_client
        self.logger = logger
        self.i18n = i18n
        if file_url:
            self._file_url = file_url
        else:
            self._file_url = "https://raw.githubusercontent.com/vinifmor/bauh-files/master/web/env/v2/suggestions.yml"
        self._cached_file_path = f'{WEB_CACHE_DIR}/suggestions.yml'
        self._cached_file_ts_path = map_timestamp_file(self._cached_file_path)

    @property
    def file_url(self) -> Optional[str]:
        return self._file_url

    def is_custom_local_file_mapped(self) -> bool:
        return self._file_url and self._file_url.startswith('/')

    def should_download(self, web_config: dict) -> bool:
        if not self._file_url:
            return False

        if self.is_custom_local_file_mapped():
            return False

        exp = web_config['suggestions']['cache_exp']
        if web_config['suggestions']['cache_exp'] is None:
            self.logger.info("No cache expiration defined for suggestions")
            return True

        try:
            exp = int(exp)
        except ValueError:
            self.logger.error(f"Error while parsing the 'suggestions.cache_exp' ({exp}) settings property")
            return True

        if exp <= 0:
            self.logger.info(f"No cache expiration defined for suggestions ({exp})")
            return True

        if not os.path.exists(self._cached_file_path):
            self.logger.info(f"No suggestions cached file found '{self._cached_file_path}'")
            return True

        if not os.path.exists(self._cached_file_ts_path):
            self.logger.info(f"No suggestions cache file timestamp found '{self._cached_file_ts_path}'")
            return True

        with open(self._cached_file_ts_path) as f:
            timestamp_str = f.read()

        try:
            sugs_timestamp = datetime.fromtimestamp(float(timestamp_str))
        except:
            self.logger.error(f"Could not parse the cached suggestions file timestamp: {timestamp_str}")
            return True

        expired = sugs_timestamp + timedelta(days=exp) <= datetime.utcnow()

        if expired:
            self.logger.info("Cached suggestions file has expired.")
            return True
        else:
            self.logger.info("Cached suggestions file is up to date")
            return False

    def get_cached_file_path(self) -> str:
        return self._file_url if self.is_custom_local_file_mapped() else self._cached_file_path

    def read_cached(self, check_file: bool = True) -> dict:
        if self.is_custom_local_file_mapped():
            file_path, log_ref = self._file_url, 'local'
        else:
            file_path, log_ref = self._cached_file_path, 'cached'

        if check_file and not os.path.exists(file_path):
            self.logger.warning(f"{log_ref.capitalize()} suggestions file does not exist ({file_path})")
            return {}

        self.logger.info(f"Reading {log_ref} suggestions file '{file_path}'")
        with open(file_path) as f:
            sugs_str = f.read()

        if not sugs_str:
            self.logger.warning(f"{log_ref.capitalize()} suggestions file '{file_path}' is empty")
            return {}

        try:
            return yaml.safe_load(sugs_str)
        except:
            self.logger.error("An unexpected exception happened")
            traceback.print_exc()
            return {}

    def download(self) -> dict:
        self.logger.info(f"Reading suggestions from {self._file_url}")
        try:
            suggestions = self.http_client.get_yaml(self._file_url, session=False)

            if suggestions:
                self.logger.info(f"{len(suggestions)} suggestions successfully read")
            else:
                self.logger.warning(f"Could not read suggestions from {self._file_url}")

        except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout):
            self.logger.warning("Internet seems to be off: it was not possible to retrieve the suggestions")
            suggestions = {}

        self.logger.info("Finished")
        return suggestions

    def save_to_disk(self, suggestions: dict, timestamp: float):
        if not suggestions:
            return

        if self.is_custom_local_file_mapped():
            return

        self.logger.info(f'Caching {len(suggestions)} suggestions to the disk')
        suggestions_file_dir = os.path.dirname(self._cached_file_path)

        try:
            Path(suggestions_file_dir).mkdir(parents=True, exist_ok=True)
        except OSError:
            self.logger.error(f"Could not generate the directory {suggestions_file_dir}")
            traceback.print_exc()
            return

        try:
            with open(self._cached_file_path, 'w+') as f:
                f.write(yaml.safe_dump(suggestions))
        except:
            self.logger.error(f"Could write to {self._cached_file_path}")
            traceback.print_exc()
            return

        self.logger.info(f"{len(suggestions)} suggestions successfully cached to file '{self._cached_file_path}'")

        try:
            with open(self._cached_file_ts_path, 'w+') as f:
                f.write(str(timestamp))
        except:
            self.logger.error(f"Could not write to {self._cached_file_ts_path}")
            traceback.print_exc()
            return

        self.logger.info(f"Suggestions cached file timestamp ({timestamp}) "
                         f"successfully saved at '{self._cached_file_ts_path}'")
