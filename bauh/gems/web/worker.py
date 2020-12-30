import logging
import time
import traceback
from threading import Thread
from typing import Optional

import yaml

from bauh.api.abstract.handler import TaskManager
from bauh.commons.boot import CreateConfigFile
from bauh.commons.html import bold
from bauh.gems.web import SEARCH_INDEX_FILE, get_icon_path
from bauh.gems.web.environment import EnvironmentUpdater
from bauh.gems.web.suggestions import SuggestionsManager
from bauh.view.util.translation import I18n


class SuggestionsLoader(Thread):

    def __init__(self, taskman: TaskManager, manager: SuggestionsManager,
                 i18n: I18n, logger: logging.Logger, suggestions_callback, suggestions: Optional[dict] = None):
        super(SuggestionsLoader, self).__init__(daemon=True)
        self.taskman = taskman
        self.task_id = 'web_sugs'
        self.manager = manager
        self.suggestions_callback = suggestions_callback
        self.i18n = i18n
        self.logger = logger
        self.suggestions = suggestions
        self.task_name = self.i18n['web.task.suggestions']
        self.taskman.register_task(self.task_id, self.task_name, get_icon_path())

    def run(self):
        ti = time.time()
        self.taskman.update_progress(self.task_id, 10, None)
        try:
            self.suggestions = self.manager.download()

            if self.suggestions_callback:
                self.suggestions_callback(self.suggestions)

            if self.suggestions:
                self.taskman.update_progress(self.task_id, 50, self.i18n['web.task.suggestions.saving'])
                self.manager.save_to_disk(self.suggestions)

        except:
            self.logger.error("Unexpected exception")
            traceback.print_exc()
        finally:
            self.taskman.update_progress(self.task_id, 100, None)
            self.taskman.finish_task(self.task_id)
            tf = time.time()
            self.logger.info("Finished. Took {0:.2f} seconds".format(tf - ti))


class SearchIndexGenerator(Thread):

    def __init__(self, taskman: TaskManager, suggestions_loader: SuggestionsLoader, i18n: I18n, logger: logging.Logger):
        super(SearchIndexGenerator, self).__init__(daemon=True)
        self.taskman = taskman
        self.i18n = i18n
        self.logger = logger
        self.suggestions_loader = suggestions_loader
        self.task_id = 'web_idx_gen'
        self.taskman.register_task(self.task_id, self.i18n['web.task.search_index'], get_icon_path())

    def run(self):
        ti = time.time()
        self.taskman.update_progress(self.task_id, 0, self.i18n['task.waiting_task'].format(bold(self.suggestions_loader.task_name)))
        self.suggestions_loader.join()

        if self.suggestions_loader.suggestions:
            self.generate_index(self.suggestions_loader.suggestions)
        else:
            self.taskman.update_progress(self.task_id, 100, None)
            self.taskman.finish_task(self.task_id)

        tf = time.time()
        self.logger.info("Finished. Took {0:.2f} seconds".format(tf - ti))

    def generate_index(self, suggestions: dict):
        self.taskman.update_progress(self.task_id, 1, None)
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
            self.taskman.update_progress(self.task_id, 50, self.i18n['web.task.suggestions.saving'])
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

        self.taskman.update_progress(self.task_id, 100, None)
        self.taskman.finish_task(self.task_id)


class UpdateEnvironmentSettings(Thread):

    def __init__(self, env_updater: EnvironmentUpdater, taskman: TaskManager, i18n: I18n, create_config: CreateConfigFile):
        super(UpdateEnvironmentSettings, self).__init__(daemon=True)
        self.env_updater = env_updater
        self.taskman = taskman
        self.create_config = create_config
        self.task_id = env_updater.task_read_settings_id
        self.i18n = i18n

    def run(self):
        self.taskman.register_task(self.task_id, self.i18n['web.task.download_settings'], get_icon_path())
        self.taskman.update_progress(self.task_id, 1,  self.i18n['task.waiting_task'].format(bold(self.create_config.task_name)))
        self.create_config.join()

        web_config = self.create_config.config
        if self.env_updater.should_download_settings(web_config):
            self.env_updater.read_settings(web_config=web_config, cache=False)
        else:
            self.taskman.update_progress(self.task_id, 100, None)
            self.taskman.finish_task(self.task_id)
