import logging
import os
import time
import traceback

from bauh.api.abstract.download import FileDownloader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.http import HttpClient
from bauh.commons.html import bold
from bauh.commons.system import run_cmd, new_subprocess, ProcessHandler, SystemProcess, SimpleProcess
from bauh.view.util.translation import I18n


class AdaptableFileDownloader(FileDownloader):

    def __init__(self, logger: logging.Logger, multithread_enabled: bool, i18n: I18n, http_client: HttpClient):
        self.logger = logger
        self.multithread_enabled = multithread_enabled
        self.i18n = i18n
        self.http_client = http_client

    def is_aria2c_available(self) -> bool:
        return bool(run_cmd('which aria2c'))

    def _get_aria2c_process(self, url: str, output_path: str, cwd: str) -> SystemProcess:
        cmd = ['aria2c', url,
               '--no-conf',
               '--max-connection-per-server=16',
               '--split=16',
               '--enable-color=false',
               '--stderr=true',
               '--summary-interval=0',
               '--disable-ipv6',
               '--min-split-size=1M',
               '--allow-overwrite=true',
               '--continue=true',
               '--timeout=5',
               '--max-file-not-found=3',
               '--remote-time=true']

        if output_path:
            output_split = output_path.split('/')
            cmd.append('--dir=' + '/'.join(output_split[:-1]))
            cmd.append('--out=' + output_split[-1])

        return SystemProcess(new_subprocess(cmd=cmd, cwd=cwd),
                             skip_stdout=True,
                             check_error_output=False,
                             success_phrases=['download completed'],
                             output_delay=0.001)

    def _get_wget_process(self, url: str, output_path: str, cwd: str) -> SimpleProcess:
        cmd = ['wget', url, '--continue', '--retry-connrefused', '--tries=10', '--no-config']

        if output_path:
            cmd.append('-O')
            cmd.append(output_path)

        return SimpleProcess(cmd=cmd, cwd=cwd)

    def _rm_bad_file(self, file_name: str, output_path: str, cwd):
        to_delete = output_path if output_path else '{}/{}'.format(cwd, file_name)

        if to_delete and os.path.exists(to_delete):
            self.logger.info('Removing downloaded file {}'.format(to_delete))
            os.remove(to_delete)

    def download(self, file_url: str, watcher: ProcessWatcher, output_path: str = None, cwd: str = None) -> bool:
        self.logger.info('Downloading {}'.format(file_url))
        handler = ProcessHandler(watcher)
        file_name = file_url.split('/')[-1]

        final_cwd = cwd if cwd else '.'

        success = False
        ti = time.time()
        try:
            if output_path and os.path.exists(output_path):
                self.logger.info('Removing old file found before downloading: {}'.format(output_path))
                os.remove(output_path)
                self.logger.info("Old file {} removed".format(output_path))

            if self.is_multithreaded():
                ti = time.time()
                process = self._get_aria2c_process(file_url, output_path, final_cwd)
                downloader = 'aria2c'
            else:
                ti = time.time()
                process = self._get_wget_process(file_url, output_path, final_cwd)
                downloader = 'wget'

            file_size = self.http_client.get_content_length(file_url)
            msg = bold('[{}] ').format(downloader) + self.i18n['downloading'] + ' ' + bold(file_url.split('/')[-1]) + (' ( {} )'.format(file_size) if file_size else '')

            if watcher:
                watcher.change_substatus(msg)

            if isinstance(process, SimpleProcess):
                success = handler.handle_simple(process)
            else:
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

    def get_default_client_name(self) -> str:
        return 'aria2c' if self. is_multithreaded() else 'wget'

