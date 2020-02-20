import logging
import traceback
from pathlib import Path

import requests
import yaml

from bauh.api.abstract.handler import TaskManager
from bauh.api.http import HttpClient
from bauh.gems.web import URL_SUGGESTIONS, TEMP_PATH, SEARCH_INDEX_FILE, SUGGESTIONS_CACHE_FILE, get_icon_path
from bauh.view.util.translation import I18n


class SuggestionsDownloader:

    def __init__(self, http_client: HttpClient, logger: logging.Logger, i18n: I18n, taskman: TaskManager = None):
        super(SuggestionsDownloader, self).__init__()
        self.http_client = http_client
        self.logger = logger
        self.taskman = taskman
        self.i18n = i18n

    def _finish_task(self):
        if self.taskman:
            self.taskman.update_progress('web_sugs', 100, None)
            self.taskman.finish_task('web_sugs')

    def download(self) -> dict:
        if self.taskman:
            self.taskman.register_task('web_sugs', self.i18n['web.task.suggestions'], get_icon_path())
            self.taskman.update_progress('web_sugs', 10, None)

        self.logger.info("Reading suggestions from {}".format(URL_SUGGESTIONS))
        try:
            suggestions = self.http_client.get_yaml(URL_SUGGESTIONS, session=False)

            if suggestions:
                self.logger.info("{} suggestions successfully read".format(len(suggestions)))
            else:
                self.logger.warning("Could not read suggestions from {}".format(URL_SUGGESTIONS))

        except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout):
            self.logger.warning("Internet seems to be off: it was not possible to retrieve the suggestions")
            self._finish_task()
            return {}

        self._finish_task()
        return suggestions


class SearchIndexGenerator:

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def generate_index(self, suggestions: dict):
        self.logger.info('Caching {} suggestions to the disk'.format(len(suggestions)))

        try:
            Path(TEMP_PATH).mkdir(parents=True, exist_ok=True)
        except:
            self.logger.error("Could not generate the directory {}".format(TEMP_PATH))
            traceback.print_exc()
            return

        try:
            with open(SUGGESTIONS_CACHE_FILE, 'w+') as f:
                f.write(yaml.safe_dump(suggestions))

            self.logger.info('{} successfully cached to the disk as {}'.format(len(suggestions), SUGGESTIONS_CACHE_FILE))
        except:
            self.logger.error("Could write to {}".format(SUGGESTIONS_CACHE_FILE))
            traceback.print_exc()
            return

        self.logger.info('Indexing suggestions')
        index = {}

        for key, sug in suggestions.items():
            name = sug.get('name')

            if name:
                split_name = name.lower().strip().split(' ')
                single_name = ''.join(split_name)

                for word in (*split_name, single_name):
                    mapped = index.get(word)

                    if not mapped:
                        mapped = set()
                        index[word] = mapped

                    mapped.add(key)

        if index:
            self.logger.info('Preparing search index for writing')

            for key in index.keys():
                index[key] = list(index[key])

            try:
                self.logger.info('Writing {} indexed keys as {}'.format(len(index), SEARCH_INDEX_FILE))
                with open(SEARCH_INDEX_FILE, 'w+') as f:
                    f.write(yaml.safe_dump(index))
                self.logger.info("Search index successfully written at {}".format(SEARCH_INDEX_FILE))
            except:
                self.logger.error("Could not write the seach index to {}".format(SEARCH_INDEX_FILE))
                traceback.print_exc()
