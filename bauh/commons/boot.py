import time
from logging import Logger
from threading import Thread
from typing import Optional

from bauh.api.abstract.handler import TaskManager
from bauh.commons.config import ConfigManager
from bauh.view.util.translation import I18n


class CreateConfigFile(Thread):
    """
    Generic initialization task to create a configuration file
    """

    def __init__(self, configman: ConfigManager, taskman: TaskManager, task_icon_path: str, i18n: I18n, logger: Logger, config_instance: Optional[dict] = None):
        super(CreateConfigFile, self).__init__(daemon=True)
        self.configman = configman
        self.taskman = taskman
        self.logger = logger
        self.config = config_instance
        self.task_icon_path = task_icon_path
        self.task_id = configman.__class__.__name__
        self.i18n = i18n
        self.task_name = self.i18n['task.checking_config']
        self.taskman.register_task(self.task_id, self.task_name, self.task_icon_path)

    def _log(self, msg: str):
        self.logger.info('{}: {}'.format(self.configman.__class__.__name__, msg))

    def run(self):
        ti = time.time()
        self.taskman.update_progress(self.task_id, 1, None)

        self._log("Reading cached configuration file")
        default_config = self.configman.get_default_config()

        cached_config = self.configman.read_config()

        self.taskman.update_progress(self.task_id, 50, None)

        if cached_config:
            self._log("Merging configuration file")
            self.configman.merge_config(default_config, cached_config)
        else:
            self._log("No cached configuration file found")

        self.config = default_config
        self.taskman.update_progress(self.task_id, 75, self.i18n['task.checking_config.saving'])

        self._log("Writing configuration file")
        self.configman.save_config(default_config)

        self.taskman.update_progress(self.task_id, 100, None)
        self.taskman.finish_task(self.task_id)
        tf = time.time()
        self._log("Finished. Took {0:.2f} seconds".format(tf - ti))
