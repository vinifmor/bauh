import os
import time
import traceback
from logging import Logger
from typing import Optional

import yaml

from bauh.gems.web import SEARCH_INDEX_FILE


class SearchIndexManager:

    def __init__(self, logger: Logger):
        self.logger = logger

    def generate(self, suggestions: dict) -> Optional[dict]:
        if suggestions:
            ti = time.time()
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

            tf = time.time()
            self.logger.info("Took {0:.4f} seconds to generate the index".format(tf - ti))

            return index

    def read(self) -> Optional[dict]:
        if os.path.exists(SEARCH_INDEX_FILE):
            with open(SEARCH_INDEX_FILE) as f:
                return yaml.safe_load(f.read())
        else:
            self.logger.warning("No search index found at {}".format(SEARCH_INDEX_FILE))

    def write(self, index: dict) -> bool:
        if index:
            self.logger.info('Preparing search index for writing')  # YAML does not work with 'sets'

            for key in index.keys():
                index[key] = list(index[key])

            try:
                self.logger.info('Writing {} indexed keys as {}'.format(len(index), SEARCH_INDEX_FILE))
                with open(SEARCH_INDEX_FILE, 'w+') as f:
                    f.write(yaml.safe_dump(index))
                self.logger.info("Search index successfully written at {}".format(SEARCH_INDEX_FILE))
                return True
            except:
                self.logger.error("Could not write the search index to {}".format(SEARCH_INDEX_FILE))
                traceback.print_exc()

        return False
