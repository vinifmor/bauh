from abc import ABC, abstractmethod

from bauh.api.abstract.handler import ProcessWatcher


class FileDownloader(ABC):

    @abstractmethod
    def download(self, file_url: str, watcher: ProcessWatcher, output_path: str, cwd: str, root_password: str = None, substatus_prefix: str = None, display_file_size: bool = True, max_threads: int = None, known_size: int = None) -> bool:
        """
        :param file_url:
        :param watcher:
        :param output_path: the downloaded file output path. Leave None for the current directory and the same file name
        :param cwd: current working directory. Leave None if does not matter.
        :param root_password: (if the output directory is protected)
        :param substatus_prefix: custom substatus prefix ('prefix downloading xpto')
        :param display_file_size: if the file size should be displayed on the substatus
        :param max_threads: maximum number of threads (only available for multi-threaded download)
        :param known_size: known file size
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
