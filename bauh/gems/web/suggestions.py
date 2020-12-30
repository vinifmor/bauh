import os
import traceback
from logging import Logger
from pathlib import Path

import requests
import yaml

from bauh.api.http import HttpClient
from bauh.gems.web import URL_SUGGESTIONS, SUGGESTIONS_CACHE_FILE
from bauh.view.util.translation import I18n


class SuggestionsManager:

    def __init__(self, http_client: HttpClient, logger: Logger, i18n: I18n):
        self.http_client = http_client
        self.logger = logger
        self.i18n = i18n

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

    def save_to_disk(self, suggestions: dict):
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

            self.logger.info("{} suggestions successfully cached to file '{}'".format(len(suggestions), SUGGESTIONS_CACHE_FILE))
        except:
            self.logger.error("Could write to {}".format(SUGGESTIONS_CACHE_FILE))
            traceback.print_exc()
            return
