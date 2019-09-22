import logging
import time
from multiprocessing import cpu_count
from typing import List

from bauh.api.abstract.download import FileDownloader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.commons.system import run_cmd, new_subprocess, ProcessHandler, SystemProcess


class AdaptableFileDownloader(FileDownloader):

    def __init__(self, logger: logging.Logger, multithread_enabled: bool):
        self.download_threads = cpu_count() * 2
        self.logger = logger
        self.multithread_enabled = multithread_enabled

    def is_axel_available(self) -> bool:
        return bool(run_cmd('which axel'))

    def _get_download_command(self, url: str, output_path: str) -> List:
        if self.is_multithreaded():
            cmd = ['axel', '-k', '-n', str(self.download_threads), url]

            if output_path:
                cmd.append('-o')
                cmd.append(output_path)

            return cmd

        cmd = ['wget', url]

        if output_path:
            cmd.append('-O')
            cmd.append(output_path)

        return cmd

    def download(self, file_url: str, watcher: ProcessWatcher, output_path: str, cwd: str):
        handler = ProcessHandler(watcher)
        cmd = self._get_download_command(file_url, output_path)
        self.logger.info('Downloading {}'.format(file_url))
        watcher.print("[{}] downloading {}{}".format(cmd[0], file_url, " as {}".format(output_path) if output_path else ''))

        ti = time.time()
        res = handler.handle(SystemProcess(new_subprocess(cmd=cmd, cwd=cwd if cwd else '.')))
        tf = time.time()
        self.logger.info(file_url.split('/')[-1] + ' download took {0:.2f} minutes'.format((tf - ti) / 60))
        return res

    def is_multithreaded(self) -> bool:
        return self.multithread_enabled and self.is_axel_available()

