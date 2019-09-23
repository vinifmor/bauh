import logging
import os
import time
import traceback
from multiprocessing import cpu_count

from bauh.api.abstract.download import FileDownloader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.commons.system import run_cmd, new_subprocess, ProcessHandler, SystemProcess


class AdaptableFileDownloader(FileDownloader):

    def __init__(self, logger: logging.Logger, multithread_enabled: bool):
        self.logger = logger
        self.multithread_enabled = multithread_enabled

        if multithread_enabled:
            try:
                self.download_threads = int(cpu_count() * 2)
            except:
                self.download_threads = 4

            self.download_threads = 16 if self.download_threads > 16 else self.download_threads
        else:
            self.download_threads = 1

    def is_axel_available(self) -> bool:
        return bool(run_cmd('which axel'))

    def is_aria2c_available(self) -> bool:
        return bool(run_cmd('which aria2c'))

    def _get_aria2c_process(self, url: str, output_path: str, cwd: str) -> SystemProcess:
        cmd = ['aria2c', '-x{}'.format(self.download_threads), url,
               '--enable-color=false',
               '--stderr=true',
               '--summary-interval=0',
               '--disable-ipv6',
               '--min-split-size=1M']

        if output_path:
            output_split = output_path.split('/')
            cmd.append('-d=' + '/'.join(output_split[:-1]))
            cmd.append('-o=' + output_split[-1])

        return SystemProcess(new_subprocess(cmd=cmd, cwd=cwd),
                             skip_stdout=True,
                             check_error_output=False,
                             success_phrase='download completed')

    def _get_axel_cmd(self, url: str, output_path: str, cwd: str) -> SystemProcess:
        cmd = ['axel', '-k', '-n', str(self.download_threads), url]

        if output_path:
            cmd.append('-o')
            cmd.append(output_path)

        return SystemProcess(new_subprocess(cmd, cwd=cwd))

    def _get_wget_process(self, url: str, output_path: str, cwd: str) -> SystemProcess:
        cmd = ['wget', url]

        if output_path:
            cmd.append('-O')
            cmd.append(output_path)

        return SystemProcess(new_subprocess(cmd, cwd=cwd))

    def _rm_bad_file(self, file_name: str, output_path: str, cwd):
        to_delete = output_path if output_path else '{}/{}'.format(cwd, file_name)

        if to_delete and os.path.exists(to_delete):
            self.logger.info('Removing downloaded file {}'.format(to_delete))
            os.remove(to_delete)

    def download(self, file_url: str, watcher: ProcessWatcher, output_path: str, cwd: str) -> bool:
        self.logger.info('Downloading {}'.format(file_url))
        handler = ProcessHandler(watcher)
        file_name = file_url.split('/')[-1]

        final_cwd = cwd if cwd else '.'

        success = False
        ti = time.time()
        try:
            if self.is_multithreaded():
                ti = time.time()
                process = self._get_aria2c_process(file_url, output_path, final_cwd)
                # process = self._get_axel_cmd(file_url, output_path, final_cwd)
            else:
                ti = time.time()
                process = self._get_wget_process(file_url, output_path, final_cwd)

            success = handler.handle(process)
        except:
            traceback.print_exc()
            self._rm_bad_file(file_name, output_path, final_cwd)

        tf = time.time()
        self.logger.info(file_name + ' download took {0:.2f} minutes'.format((tf - ti) / 60))

        if not success:
            self.logger.error("Could not download '{}'".format(file_name))
            self._rm_bad_file(file_name, output_path, final_cwd)

        return success

    def is_multithreaded(self) -> bool:
        return self.multithread_enabled and self.is_aria2c_available()

