import logging
import os
import re
import time
import traceback
from math import floor
from threading import Thread
from typing import Iterable, List

from bauh.api.abstract.download import FileDownloader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.http import HttpClient
from bauh.commons.html import bold
from bauh.commons.system import run_cmd, ProcessHandler, SimpleProcess, get_human_size_str
from bauh.view.util.translation import I18n

RE_HAS_EXTENSION = re.compile(r'.+\.\w+$')


class AdaptableFileDownloader(FileDownloader):

    def __init__(self, logger: logging.Logger, multithread_enabled: bool, i18n: I18n, http_client: HttpClient, multithread_client: str):
        self.logger = logger
        self.multithread_enabled = multithread_enabled
        self.i18n = i18n
        self.http_client = http_client
        self.supported_multithread_clients = ['aria2', 'axel']
        self.multithread_client = multithread_client

    @staticmethod
    def is_aria2c_available() -> bool:
        return bool(run_cmd('which aria2c', print_error=False))

    @staticmethod
    def is_axel_available() -> bool:
        return bool(run_cmd('which axel', print_error=False))

    @staticmethod
    def is_wget_available() -> bool:
        return bool(run_cmd('which wget', print_error=False))

    def _get_aria2c_process(self, url: str, output_path: str, cwd: str, root_password: str, threads: int) -> SimpleProcess:
        cmd = ['aria2c', url,
               '--no-conf',
               '-x', '16',
               '--enable-color=false',
               '--stderr=true',
               '--summary-interval=0',
               '--disable-ipv6',
               '-k', '1M',
               '--allow-overwrite=true',
               '-c',
               '-t', '5',
               '--max-file-not-found=3',
               '--file-allocation=none',
               '--console-log-level=error']

        if threads > 1:
            cmd.append('-s')
            cmd.append(str(threads))

        if output_path:
            output_split = output_path.split('/')
            cmd.append('-d')
            cmd.append('/'.join(output_split[:-1]))
            cmd.append('-o')
            cmd.append(output_split[-1])

        return SimpleProcess(cmd=cmd, root_password=root_password, cwd=cwd)

    def _get_axel_process(self, url: str, output_path: str, cwd: str, root_password: str, threads: int) -> SimpleProcess:
        cmd = ['axel', url, '-n', str(threads), '-4', '-c', '-T', '5']

        if output_path:
            cmd.append('--output={}'.format(output_path))

        return SimpleProcess(cmd=cmd, cwd=cwd, root_password=root_password)

    def _get_wget_process(self, url: str, output_path: str, cwd: str, root_password: str) -> SimpleProcess:
        cmd = ['wget', url, '-c', '--retry-connrefused', '-t', '10', '--no-config', '-nc']

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

    def _get_appropriate_threads_number(self, max_threads: int, known_size: int) -> int:
        if max_threads and max_threads > 0:
            threads = max_threads
        elif known_size:
            threads = 16 if known_size >= 16000000 else floor(known_size / 1000000)

            if threads <= 0:
                threads = 1
        else:
            threads = 16

        return threads

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

            client = self.get_available_multithreaded_tool()
            if client:
                threads = self._get_appropriate_threads_number(max_threads, known_size)

                if client == 'aria2':
                    ti = time.time()
                    process = self._get_aria2c_process(file_url, output_path, final_cwd, root_password, threads)
                    downloader = 'aria2'
                else:
                    ti = time.time()
                    process = self._get_axel_process(file_url, output_path, final_cwd, root_password, threads)
                    downloader = 'axel'
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
        return bool(self.get_available_multithreaded_tool())

    def get_available_multithreaded_tool(self) -> str:
        if self.multithread_enabled:
            if self.multithread_client is None or self.multithread_client not in self.supported_multithread_clients:
                for client in self.supported_multithread_clients:
                    if self.is_multithreaded_client_available(client):
                        return client
            else:
                possible_clients = {*self.supported_multithread_clients}

                if self.is_multithreaded_client_available(self.multithread_client):
                    return self.multithread_client
                else:
                    possible_clients.remove(self.multithread_client)

                    for client in possible_clients:
                        if self.is_multithreaded_client_available(client):
                            return client

    def can_work(self) -> bool:
        return self.is_wget_available() or self.is_multithreaded()

    def get_supported_multithreaded_clients(self) -> Iterable[str]:
        return self.supported_multithread_clients

    def is_multithreaded_client_available(self, name: str) -> bool:
        if name == 'aria2':
            return self.is_aria2c_available()
        elif name == 'axel':
            return self.is_axel_available()
        else:
            return False

    def list_available_multithreaded_clients(self) -> List[str]:
        return [c for c in self.supported_multithread_clients if self.is_multithreaded_client_available(c)]
