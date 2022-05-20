import os
import traceback
from datetime import datetime, timedelta
from logging import Logger
from pathlib import Path
from threading import Thread
from typing import Optional, Dict

from bauh.api.abstract.handler import TaskManager
from bauh.api.abstract.model import SuggestionPriority
from bauh.api.http import HttpClient
from bauh.commons.boot import CreateConfigFile
from bauh.gems.arch import ARCH_CACHE_DIR, get_icon_path
from bauh.view.util.translation import I18n


class RepositorySuggestionsDownloader(Thread):

    _file_suggestions: Optional[str] = None
    _file_suggestions_ts: Optional[str] = None
    _url_suggestions: Optional[str] = None

    @classmethod
    def file_suggestions(cls) -> str:
        if cls._file_suggestions is None:
            cls._file_suggestions = f'{ARCH_CACHE_DIR}/suggestions.txt'

        return cls._file_suggestions

    @classmethod
    def file_suggestions_timestamp(cls) -> str:
        if cls._file_suggestions_ts is None:
            cls._file_suggestions_ts = f'{cls.file_suggestions()}.ts'

        return cls._file_suggestions_ts

    @classmethod
    def url_suggestions(cls) -> str:
        if cls._url_suggestions is None:
            cls._url_suggestions = 'https://raw.githubusercontent.com/vinifmor/bauh-files' \
                                   '/master/arch/suggestions.txt'

        return cls._url_suggestions

    def __init__(self, logger: Logger, http_client: HttpClient, i18n: I18n,
                 create_config: Optional[CreateConfigFile] = None):
        super(RepositorySuggestionsDownloader, self).__init__()
        self._log = logger
        self.i18n = i18n
        self.http_client = http_client
        self._taskman: Optional[TaskManager] = None
        self.create_config = create_config
        self.task_id = 'arch.suggs'

    def register_task(self, taskman: Optional[TaskManager]):
        self._taskman = taskman
        if taskman:
            self._taskman.register_task(id_=self.task_id, label=self.i18n['task.download_suggestions'],
                                        icon_path=get_icon_path())

    @property
    def taskman(self) -> TaskManager:
        if self._taskman is None:
            self._taskman = TaskManager()

        return self._taskman

    @classmethod
    def should_download(cls, arch_config: dict, logger: Logger, only_positive_exp: bool = False) -> bool:
        try:
            exp_hours = int(arch_config['suggestions_exp'])
        except ValueError:
            logger.error(f"The Arch configuration property 'suggestions_exp' has a non int value set: "
                         f"{arch_config['suggestions']['expiration']}")
            return not only_positive_exp

        if exp_hours <= 0:
            logger.info("Suggestions cache is disabled")
            return not only_positive_exp

        if not os.path.exists(cls.file_suggestions()):
            logger.info(f"'{cls.file_suggestions()}' not found. It must be downloaded")
            return True

        if not os.path.exists(cls.file_suggestions()):
            logger.info(f"'{cls.file_suggestions()}' not found. The suggestions file must be downloaded.")
            return True

        with open(cls.file_suggestions_timestamp()) as f:
            timestamp_str = f.read()

        try:
            suggestions_timestamp = datetime.fromtimestamp(float(timestamp_str))
        except:
            logger.error(f'Could not parse the Arch cached suggestions timestamp: {timestamp_str}')
            traceback.print_exc()
            return True

        update = suggestions_timestamp + timedelta(hours=exp_hours) <= datetime.utcnow()
        return update

    def _save(self, text: str, timestamp: float):
        self._log.info(f"Caching suggestions to '{self.file_suggestions()}'")

        cache_dir = os.path.dirname(self.file_suggestions())

        try:
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            cache_dir_ok = True
        except OSError:
            self._log.error(f"Could not create cache directory '{cache_dir}'")
            traceback.print_exc()
            cache_dir_ok = False

        if cache_dir_ok:
            try:
                with open(self.file_suggestions(), 'w+') as f:
                    f.write(text)
            except:
                self._log.error(f"An exception happened while writing the file '{self.file_suggestions()}'")
                traceback.print_exc()

            try:
                with open(self.file_suggestions_timestamp(), 'w+') as f:
                    f.write(str(timestamp))
            except:
                self._log.error(f"An exception happened while writing the file '{self.file_suggestions_timestamp()}'")
                traceback.print_exc()

    def parse_suggestions(self, suggestions_str: str) -> Dict[str, SuggestionPriority]:
        output = dict()
        for line in suggestions_str.split('\n'):
            clean_line = line.strip()

            if clean_line:
                line_split = clean_line.split(':', 1)

                if len(line_split) == 2:
                    try:
                        prio = int(line_split[0])
                    except ValueError:
                        self._log.warning(f"Could not parse Arch package suggestion: {line}")
                        continue

                    output[line_split[1]] = SuggestionPriority(prio)

        return output

    def read_cached(self) -> Optional[Dict[str, SuggestionPriority]]:
        self._log.info(f"Reading cached suggestions file '{self.file_suggestions()}'")

        try:
            with open(self.file_suggestions()) as f:
                sugs_str = f.read()
        except FileNotFoundError:
            self._log.warning(f"Cached suggestions file does not exist ({self.file_suggestions()})")
            return

        if not sugs_str:
            self._log.warning(f"Cached suggestions file '{self.file_suggestions()}' is empty")
            return

        return self.parse_suggestions(sugs_str)

    def download(self) -> Optional[Dict[str, SuggestionPriority]]:
        self.taskman.update_progress(self.task_id, progress=1, substatus=None)

        self._log.info(f"Downloading suggestions from {self.url_suggestions()}")
        res = self.http_client.get(self.url_suggestions())

        suggestions = None
        if res.status_code == 200 and res.text:
            self.taskman.update_progress(self.task_id, progress=50, substatus=None)
            suggestions = self.parse_suggestions(res.text)

            if suggestions:
                self._save(text=res.text, timestamp=datetime.utcnow().timestamp())
            else:
                self._log.warning("No Arch suggestions to cache")
        else:
            self._log.warning(f"Could not retrieve Arch suggestions. "
                              f"Response (status={res.status_code}, text={res.text})")

        self.taskman.update_progress(self.task_id, progress=100, substatus=None)
        self.taskman.finish_task(self.task_id)
        return suggestions

    def read(self, arch_config: dict) -> Optional[Dict[str, int]]:
        if self.should_download(arch_config=arch_config, logger=self._log):
            return self.download()

        return self.read_cached()

    def run(self):
        if self.create_config:
            if self.create_config.is_alive():
                self.taskman.update_progress(self.task_id, 0,
                                             self.i18n['task.waiting_task'].format(self.create_config.task_name))
                self.create_config.join()

            if not self.should_download(arch_config=self.create_config.config, logger=self._log,
                                        only_positive_exp=False):
                self.taskman.update_progress(self.task_id, 100, self.i18n['task.canceled'])
                self.taskman.finish_task(self.task_id)
                return

            self.download()
        else:
            self._log.error(f"No {CreateConfigFile.__class__.__name__} instance set. Aborting..")
            self.taskman.update_progress(self.task_id, 100, self.i18n['error'])
            self.taskman.finish_task(self.task_id)
