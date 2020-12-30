import logging
import time
import traceback
from datetime import datetime
from threading import Thread
from typing import Optional

from bauh.api.abstract.handler import TaskManager
from bauh.commons.boot import CreateConfigFile
from bauh.commons.html import bold
from bauh.gems.web import get_icon_path
from bauh.gems.web.environment import EnvironmentUpdater
from bauh.gems.web.search import SearchIndexManager
from bauh.gems.web.suggestions import SuggestionsManager
from bauh.view.util.translation import I18n


class SuggestionsLoader(Thread):

    def __init__(self, taskman: TaskManager, manager: SuggestionsManager,
                 i18n: I18n, logger: logging.Logger, suggestions_callback, create_config: CreateConfigFile,
                 internet_connection: bool, suggestions: Optional[dict] = None):
        super(SuggestionsLoader, self).__init__(daemon=True)
        self.taskman = taskman
        self.task_id = 'web_sugs'
        self.manager = manager
        self.suggestions_callback = suggestions_callback
        self.i18n = i18n
        self.logger = logger
        self.suggestions = suggestions
        self.create_config = create_config
        self.internet_connection = internet_connection
        self.task_name = self.i18n['web.task.suggestions']
        self.taskman.register_task(self.task_id, self.task_name, get_icon_path())

    def run(self):
        ti = time.time()
        self.taskman.update_progress(self.task_id, 0, self.i18n['task.waiting_task'].format(bold(self.create_config.task_name)))
        self.create_config.join()

        self.taskman.update_progress(self.task_id, 10, None)

        if not self.internet_connection:
            self.logger.warning("No internet connection. Only cached suggestions can be loaded")
            self.suggestions = self.manager.read_cached(check_file=True)
        elif not self.manager.should_download(self.create_config.config):
            self.suggestions = self.manager.read_cached(check_file=False)
        else:
            try:
                timestamp = datetime.utcnow().timestamp()
                self.suggestions = self.manager.download()

                if self.suggestions:
                    self.taskman.update_progress(self.task_id, 50, self.i18n['web.task.suggestions.saving'])
                    self.manager.save_to_disk(self.suggestions, timestamp)
            except:
                self.logger.error("Unexpected exception")
                traceback.print_exc()

        if self.suggestions_callback:
            self.taskman.update_progress(self.task_id, 75, None)
            try:
                self.suggestions_callback(self.suggestions)
            except:
                self.logger.error("Unexpected exception")
                traceback.print_exc()

        self.taskman.update_progress(self.task_id, 100, None)
        self.taskman.finish_task(self.task_id)
        tf = time.time()
        self.logger.info("Finished. Took {0:.4f} seconds".format(tf - ti))


class SearchIndexGenerator(Thread):

    def __init__(self, taskman: TaskManager, idxman: SearchIndexManager, suggestions_loader: SuggestionsLoader, i18n: I18n, logger: logging.Logger):
        super(SearchIndexGenerator, self).__init__(daemon=True)
        self.taskman = taskman
        self.idxman = idxman
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
            self.taskman.update_progress(self.task_id, 1, None)
            self.logger.info('Indexing suggestions')
            index = self.idxman.generate(self.suggestions_loader.suggestions)

            if index:
                self.taskman.update_progress(self.task_id, 50, self.i18n['web.task.suggestions.saving'])
                self.idxman.write(index)

        self.taskman.update_progress(self.task_id, 100, None)
        self.taskman.finish_task(self.task_id)
        tf = time.time()
        self.logger.info("Finished. Took {0:.4f} seconds".format(tf - ti))


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
