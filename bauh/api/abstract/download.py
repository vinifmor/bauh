from abc import ABC, abstractmethod

from bauh.api.abstract.handler import ProcessWatcher


class FileDownloader(ABC):

    @abstractmethod
    def download(self, file_url: str, watcher: ProcessWatcher, output_path: str, cwd: str) -> bool:
        """
        :param file_url:
        :param watcher:
        :param output_path: the downloaded file output path. Leave None for the current directory and the same file name
        :param cwd: current working directory. Leave None if does not matter.
        :return: success / failure
        """
        pass

    @abstractmethod
    def is_multithreaded(self) -> bool:
        pass

    @abstractmethod
    def get_default_client_name(self) -> str:
        """
        :return: retrieve current downloader client name
        """
        pass
