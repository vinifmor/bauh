import logging
import traceback
from pathlib import Path

import yaml

from bauh.api.http import HttpClient
from bauh.gems.web import URL_SUGGESTIONS, TEMP_PATH, SEARCH_INDEX_FILE


class SuggestionsDownloader:

    def __init__(self, http_client: HttpClient, logger: logging.Logger):
        super(SuggestionsDownloader, self).__init__()
        self.http_client = http_client
        self.logger = logger

    def download(self) -> dict:
        self.logger.info("Reading suggestions from {}".format(URL_SUGGESTIONS))
        suggestions = self.http_client.get_yaml(URL_SUGGESTIONS)

        if suggestions:
            self.logger.info("{} suggestions successfully read".format(len(suggestions)))
        else:
            self.logger.warning("Could not read suggestions from {}".format(URL_SUGGESTIONS))

        return suggestions


class SearchIndexGenerator:

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def generate_index(self, suggestions: dict):
        self.logger.info('Indexing {} app suggestions'.format(len(suggestions)))
        index = {}

        for key, sug in suggestions.items():
            name = sug.get('name')

            if name:
                split_name = name.split(' ')
                single_name = ''.join(split_name)

                for word in (*split_name, single_name):
                    word_key = word.lower().strip()
                    mapped = index.get(word_key)

                    if not mapped:
                        mapped = set()
                        index[word_key] = mapped

                    mapped.add(key)

        if index:
            self.logger.info('Preparing search index for writing')

            for key in index.keys():
                index[key] = list(index[key])

            try:
                Path(TEMP_PATH).mkdir(parents=True, exist_ok=True)
            except:
                self.logger.error("Could not generate the directory {}".format(TEMP_PATH))
                traceback.print_exc()
                return

            try:
                self.logger.info('Writing {} indexed keys as {}'.format(len(index), SEARCH_INDEX_FILE))
                with open(SEARCH_INDEX_FILE, 'w+') as f:
                    f.write(yaml.safe_dump(index))
                self.logger.info("Search index successfully written at {}".format(SEARCH_INDEX_FILE))
            except:
                self.logger.error("Could not write the seach index to {}".format(SEARCH_INDEX_FILE))
                traceback.print_exc()
