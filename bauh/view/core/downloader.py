import logging
import os
import re
import time
import traceback
from math import floor
from threading import Thread

from bauh.api.abstract.download import FileDownloader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.http import HttpClient
from bauh.commons.html import bold
from bauh.commons.system import run_cmd, ProcessHandler, SimpleProcess, get_human_size_str
from bauh.view.util.translation import I18n

RE_HAS_EXTENSION = re.compile(r'.+\.\w+$')


class AdaptableFileDownloader(FileDownloader):

    def __init__(self, logger: logging.Logger, multithread_enabled: bool, i18n: I18n, http_client: HttpClient):
        self.logger = logger
        self.multithread_enabled = multithread_enabled
        self.i18n = i18n
        self.http_client = http_client

    def is_aria2c_available(self) -> bool:
        return bool(run_cmd('which aria2c', print_error=False))

    def _get_aria2c_process(self, url: str, output_path: str, cwd: str, root_password: str, max_threads: int, known_size: int) -> SimpleProcess:

        if max_threads and max_threads > 0:
            threads = max_threads
        elif known_size:
            threads = 16 if known_size >= 16000000 else floor(known_size / 1000000)

            if threads <= 0:
                threads = 1
        else:
            threads = 16

        cmd = ['aria2c', url,
               '--no-conf',
               '--max-connection-per-server={}'.format(threads),
               '--enable-color=false',
               '--stderr=true',
               '--summary-interval=0',
               '--disable-ipv6',
               '--min-split-size=1M',
               '--allow-overwrite=true',
               '--continue=true',
               '--timeout=5',
               '--max-file-not-found=3',
               '--file-allocation=falloc',
               '--remote-time=true']

        if threads > 1:
            cmd.append('--split={}'.format(threads))

        if output_path:
            output_split = output_path.split('/')
            cmd.append('--dir=' + '/'.join(output_split[:-1]))
            cmd.append('--out=' + output_split[-1])

        return SimpleProcess(cmd=cmd, root_password=root_password, cwd=cwd)

    def _get_wget_process(self, url: str, output_path: str, cwd: str, root_password: str) -> SimpleProcess:
        cmd = ['wget', url, '--continue', '--retry-connrefused', '--tries=10', '--no-config']

        if output_path:
            cmd.append('-O')
            cmd.append(output_path)

        return SimpleProcess(cmd=cmd, cwd=cwd, root_password=root_password)

    def _rm_bad_file(self, file_name: str, output_path: str, cwd, handler: ProcessHandler, root_password: str):
        to_delete = output_path if output_path else '{}/{}'.format(cwd, file_name)

        if to_delete and os.path.exists(to_delete):
            self.logger.info('Removing downloaded file {}'.format(to_delete))
            success, _ = handler.handle_simple(SimpleProcess(['rm', '-rf',to_delete], root_password=root_password))
            return success

    def _display_file_size(self, file_url: str, base_substatus, watcher: ProcessWatcher):
        try:
            size = self.http_client.get_content_length(file_url)

            if size:
                watcher.change_substatus(base_substatus + ' ( {} )'.format(size))
        except:
            pass

    def download(self, file_url: str, watcher: ProcessWatcher, output_path: str = None, cwd: str = None, root_password: str = None, substatus_prefix: str = None, display_file_size: bool = True, max_threads: int = None, known_size: int = None) -> bool:
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
                process = self._get_aria2c_process(file_url, output_path, final_cwd, root_password, max_threads, known_size)
                downloader = 'aria2'
            else:
                ti = time.time()
                process = self._get_wget_process(file_url, output_path, final_cwd, root_password)
                downloader = 'wget'

            name = file_url.split('/')[-1]

            if output_path and not RE_HAS_EXTENSION.match(name) and RE_HAS_EXTENSION.match(output_path):
                name = output_path.split('/')[-1]

            if substatus_prefix:
                msg = substatus_prefix + ' '
            else:
                msg = ''

            msg += bold('[{}] ').format(downloader) + self.i18n['downloading'] + ' ' + bold(name)

            if watcher:
                watcher.change_substatus(msg)

                if display_file_size:
                    if known_size:
                        watcher.change_substatus(msg + ' ( {} )'.format(get_human_size_str(known_size)))
                    else:
                        Thread(target=self._display_file_size, args=(file_url, msg, watcher)).start()

            success, _ = handler.handle_simple(process)
        except:
            traceback.print_exc()
            self._rm_bad_file(file_name, output_path, final_cwd, handler, root_password)

        tf = time.time()
        self.logger.info(file_name + ' download took {0:.2f} minutes'.format((tf - ti) / 60))

        if not success:
            self.logger.error("Could not download '{}'".format(file_name))
            self._rm_bad_file(file_name, output_path, final_cwd, handler, root_password)

        return success

    def is_multithreaded(self) -> bool:
        return self.multithread_enabled and self.is_aria2c_available()

    def get_default_client_name(self) -> str:
        return 'aria2c' if self. is_multithreaded() else 'wget'
