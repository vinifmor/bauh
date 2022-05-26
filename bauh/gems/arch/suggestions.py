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
from bauh.commons.suggestions import parse


class RepositorySuggestionsDownloader(Thread):

    _file_suggestions: Optional[str] = None
    _file_suggestions_ts: Optional[str] = None

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

    def __init__(self, logger: Logger, http_client: HttpClient, i18n: I18n,
                 create_config: Optional[CreateConfigFile] = None, file_url: Optional[str] = None):
        super(RepositorySuggestionsDownloader, self).__init__()
        self._log = logger
        self.i18n = i18n
        self.http_client = http_client
        self._taskman: Optional[TaskManager] = None
        self.create_config = create_config
        self._file_url = file_url if file_url else 'https://raw.githubusercontent.com/vinifmor/bauh-files' \
                                                   '/master/arch/suggestions.txt'
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

    def should_download(self, arch_config: dict, only_positive_exp: bool = False) -> bool:
        if not self._file_url:
            self._log.error("No Arch suggestions file URL defined")
            return False

        if self._file_url.startswith('/'):
            return False

        try:
            exp_hours = int(arch_config['suggestions_exp'])
        except ValueError:
            self._log.error(f"The Arch configuration property 'suggestions_exp' has a non int value set: "
                            f"{arch_config['suggestions']['expiration']}")
            return not only_positive_exp

        if exp_hours <= 0:
            self._log.info("Suggestions cache is disabled")
            return not only_positive_exp

        if not os.path.exists(self.file_suggestions()):
            self._log.info(f"'{self.file_suggestions()}' not found. It must be downloaded")
            return True

        if not os.path.exists(self.file_suggestions_timestamp()):
            self._log.info(f"'{self.file_suggestions()}' not found. The suggestions file must be downloaded.")
            return True

        with open(self.file_suggestions_timestamp()) as f:
            timestamp_str = f.read()

        try:
            suggestions_timestamp = datetime.fromtimestamp(float(timestamp_str))
        except:
            self._log.error(f'Could not parse the Arch cached suggestions timestamp: {timestamp_str}')
            traceback.print_exc()
            return True

        update = suggestions_timestamp + timedelta(hours=exp_hours) <= datetime.utcnow()

        if update:
            self._log.info("The cached suggestions file is no longer valid")
        else:
            self._log.info("The cached suggestions file is up-to-date")

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

    def read_cached(self, custom_file: Optional[str] = None) -> Optional[Dict[str, SuggestionPriority]]:
        if custom_file:
            file_path, log_ref = custom_file, 'local'
        else:
            file_path, log_ref = self.file_suggestions(), 'cached'

        self._log.info(f"Reading {log_ref} Arch suggestions file '{file_path}'")

        try:
            with open(file_path) as f:
                sugs_str = f.read()
        except FileNotFoundError:
            self._log.warning(f"{log_ref.capitalize()} suggestions file does not exist ({file_path})")
            return

        if not sugs_str:
            self._log.warning(f"{log_ref.capitalize()} suggestions file '{file_path}' is empty")
            return

        return parse(sugs_str, self._log, 'Arch')

    def download(self) -> Optional[Dict[str, SuggestionPriority]]:
        self.taskman.update_progress(self.task_id, progress=1, substatus=None)

        self._log.info(f"Downloading suggestions from {self._file_url}")
        res = self.http_client.get(self._file_url)

        suggestions = None
        if res.status_code == 200 and res.text:
            self.taskman.update_progress(self.task_id, progress=50, substatus=None)
            suggestions = parse(res.text, self._log, 'Arch')

            if suggestions:
                self._save(text=res.text, timestamp=datetime.utcnow().timestamp())
            else:
                self._log.warning(f"Could not parse any Arch suggestion from {self._file_suggestions_ts}")
        else:
            self._log.warning(f"Could not retrieve Arch suggestions. "
                              f"Response (status={res.status_code}, text={res.text})")

        self.taskman.update_progress(self.task_id, progress=100, substatus=None)
        self.taskman.finish_task(self.task_id)
        return suggestions

    def read(self, arch_config: dict) -> Optional[Dict[str, int]]:
        if self._file_url:
            if self.is_custom_local_file_mapped():
                return self.read_cached(custom_file=self._file_url)

            if self.should_download(arch_config=arch_config):
                return self.download()

            return self.read_cached()

    def is_custom_local_file_mapped(self) -> bool:
        return self._file_url and self._file_url.startswith('/')

    def run(self):
        if self.create_config:
            if self.create_config.is_alive():
                self.taskman.update_progress(self.task_id, 0,
                                             self.i18n['task.waiting_task'].format(self.create_config.task_name))
                self.create_config.join()

            if not self.should_download(arch_config=self.create_config.config, only_positive_exp=False):
                self.taskman.update_progress(self.task_id, 100, self.i18n['task.canceled'])
                self.taskman.finish_task(self.task_id)
                return

            self.download()
        else:
            self._log.error(f"No {CreateConfigFile.__class__.__name__} instance set. Aborting..")
            self.taskman.update_progress(self.task_id, 100, self.i18n['error'])
            self.taskman.finish_task(self.task_id)
