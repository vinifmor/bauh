import os
import traceback
from datetime import datetime, timedelta
from logging import Logger
from pathlib import Path

import requests
import yaml

from bauh.api.http import HttpClient
from bauh.gems.web import URL_SUGGESTIONS, SUGGESTIONS_CACHE_FILE, SUGGESTIONS_CACHE_TS_FILE
from bauh.view.util.translation import I18n


class SuggestionsManager:

    def __init__(self, http_client: HttpClient, logger: Logger, i18n: I18n):
        self.http_client = http_client
        self.logger = logger
        self.i18n = i18n

    def should_download(self, web_config: dict) -> bool:
        exp = web_config['suggestions']['cache_exp']
        if web_config['suggestions']['cache_exp'] is None:
            self.logger.info("No cache expiration defined for suggestions")
            return True

        try:
            exp = int(exp)
        except ValueError:
            self.logger.error("Error while parsing the 'suggestions.cache_exp' ({}) settings property".format(exp))
            return True

        if exp <= 0:
            self.logger.info("No cache expiration defined for suggestions ({})".format(exp))
            return True

        if not os.path.exists(SUGGESTIONS_CACHE_FILE):
            self.logger.info("No suggestions cached file found '{}'".format(SUGGESTIONS_CACHE_FILE))
            return True

        if not os.path.exists(SUGGESTIONS_CACHE_TS_FILE):
            self.logger.info("No suggestions cache file timestamp found '{}'".format(SUGGESTIONS_CACHE_TS_FILE))
            return True

        with open(SUGGESTIONS_CACHE_TS_FILE) as f:
            timestamp_str = f.read()

        try:
            sugs_timestamp = datetime.fromtimestamp(float(timestamp_str))
        except:
            self.logger.error("Could not parse the cached suggestions file timestamp: {}".format(timestamp_str))
            return True

        expired = sugs_timestamp + timedelta(days=exp) <= datetime.utcnow()

        if expired:
            self.logger.info("Cached suggestions file has expired.")
            return True
        else:
            self.logger.info("Cached suggestions file is up to date")
            return False

    def read_cached(self, check_file: bool = True) -> dict:
        if check_file and not os.path.exists(SUGGESTIONS_CACHE_FILE):
            self.logger.warning("Cached suggestions file does not exist ({})".format(SUGGESTIONS_CACHE_FILE))
            return {}

        self.logger.info("Reading cached suggestions file '{}'".format(SUGGESTIONS_CACHE_FILE))
        with open(SUGGESTIONS_CACHE_FILE) as f:
            sugs_str = f.read()

        if not sugs_str:
            self.logger.warning("Cached suggestions file '{}' is empty".format(SUGGESTIONS_CACHE_FILE))
            return {}

        try:
            return yaml.safe_load(sugs_str)
        except:
            self.logger.error("An unexpected exception happened")
            traceback.print_exc()
            return {}

    def download(self) -> dict:
        self.logger.info("Reading suggestions from {}".format(URL_SUGGESTIONS))
        try:
            suggestions = self.http_client.get_yaml(URL_SUGGESTIONS, session=False)

            if suggestions:
                self.logger.info("{} suggestions successfully read".format(len(suggestions)))
            else:
                self.logger.warning("Could not read suggestions from {}".format(URL_SUGGESTIONS))

        except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout):
            self.logger.warning("Internet seems to be off: it was not possible to retrieve the suggestions")
            suggestions = {}

        self.logger.info("Finished")
        return suggestions

    def save_to_disk(self, suggestions: dict, timestamp: float):
        if not suggestions:
            return

        self.logger.info('Caching {} suggestions to the disk'.format(len(suggestions)))
        suggestions_file_dir = os.path.dirname(SUGGESTIONS_CACHE_FILE)
        try:
            Path(suggestions_file_dir).mkdir(parents=True, exist_ok=True)
        except OSError:
            self.logger.error("Could not generate the directory {}".format(suggestions_file_dir))
            traceback.print_exc()
            return

        try:
            with open(SUGGESTIONS_CACHE_FILE, 'w+') as f:
                f.write(yaml.safe_dump(suggestions))
        except:
            self.logger.error("Could write to {}".format(SUGGESTIONS_CACHE_FILE))
            traceback.print_exc()
            return

        self.logger.info("{} suggestions successfully cached to file '{}'".format(len(suggestions), SUGGESTIONS_CACHE_FILE))

        try:
            with open(SUGGESTIONS_CACHE_TS_FILE, 'w+') as f:
                f.write(str(timestamp))
        except:
            self.logger.error("Could not write to {}".format(SUGGESTIONS_CACHE_TS_FILE))
            traceback.print_exc()
            return

        self.logger.info("Suggestions cached file timestamp ({}) successfully saved at '{}'".format(timestamp, SUGGESTIONS_CACHE_TS_FILE))
