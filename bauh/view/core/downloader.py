import os
import re
import shutil
import time
import traceback
from io import StringIO, BytesIO
from logging import Logger
from math import floor
from pathlib import Path
from threading import Thread
from typing import Optional, Tuple

from bauh.api.abstract.download import FileDownloader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.http import HttpClient
from bauh.commons.html import bold
from bauh.commons.system import ProcessHandler, SimpleProcess
from bauh.commons.view_utils import get_human_size_str
from bauh.view.util.translation import I18n

RE_HAS_EXTENSION = re.compile(r'.+\.\w+$')


class SelfFileDownloader(FileDownloader):

    def __init__(self, logger: Logger, i18n: I18n, http_client: HttpClient,
                 check_ssl: bool):
        self._logger = logger
        self._i18n = i18n
        self._client = http_client
        self._ssl = check_ssl

    def is_multithreaded(self) -> bool:
        return False

    def can_work(self) -> bool:
        return True

    def get_supported_multithreaded_clients(self) -> Tuple[str, ...]:
        return tuple()

    def is_multithreaded_client_available(self, name: str) -> bool:
        return False

    def list_available_multithreaded_clients(self) -> Tuple[str, ...]:
        return tuple()

    def get_supported_clients(self) -> Tuple[str, ...]:
        return tuple()

    def download(self, file_url: str, watcher: Optional[ProcessWatcher], output_path: str, cwd: str,
                 root_password: Optional[str] = None, substatus_prefix: str = None, display_file_size: bool = True,
                 max_threads: int = None, known_size: int = None) -> bool:
        try:
            res = self._client.get(url=file_url, ignore_ssl=not self._ssl, stream=True)
        except Exception:
            return False

        try:
            content_length = int(res.headers.get("content-length", 0))
        except Exception:
            content_length = 0
            self._logger.warning(f"Could not retrieve the content-length for file '{file_url}'")

        file_name = file_url.split("/")[-1]
        msg = StringIO()
        msg.write(f"{substatus_prefix} " if substatus_prefix else "")
        msg.write(f"{self._i18n['downloading']} {bold(file_name)}")
        base_msg = msg.getvalue()

        byte_stream = BytesIO()
        total_downloaded = 0
        known_size = content_length and content_length > 0
        total_size_str = get_human_size_str(content_length) if known_size > 0 else "?"

        try:
            for data in res.iter_content(chunk_size=1024):
                byte_stream.write(data)
                total_downloaded += len(data)
                perc = f"({(total_downloaded / content_length) * 100:.2f}%) " if known_size > 0 else ""
                watcher.change_substatus(f"{perc}{base_msg} ({get_human_size_str(total_downloaded)} / {total_size_str})")
        except Exception:
            self._logger.error(f"Unexpected exception while downloading file from '{file_url}'")
            traceback.print_exc()
            return False

        self._logger.info(f"Writing downloaded file content to disk: {output_path}")

        try:
            with open(output_path, "wb+") as f:
                f.write(byte_stream.getvalue())
        except Exception:
            self._logger.error(f"Unexpected exception when saving downloaded content to disk: {output_path}")
            traceback.print_exc()
            return False

        return True


class AdaptableFileDownloader(FileDownloader):

    def __init__(self, logger: Logger, multithread_enabled: bool, i18n: I18n, http_client: HttpClient,
                 multithread_client: str, check_ssl: bool):
        self.logger = logger
        self.multithread_enabled = multithread_enabled
        self.i18n = i18n
        self.http_client = http_client
        self.supported_multithread_clients = ("aria2", "axel")
        self.multithread_client = multithread_client
        self.check_ssl = check_ssl
        self._self_downloader = SelfFileDownloader(logger=logger,
                                                   i18n=i18n,
                                                   http_client=http_client,
                                                   check_ssl=check_ssl)

    @staticmethod
    def is_aria2c_available() -> bool:
        return bool(shutil.which('aria2c'))

    @staticmethod
    def is_axel_available() -> bool:
        return bool(shutil.which('axel'))

    def _get_aria2c_process(self, url: str, output_path: str, cwd: str, root_password: Optional[str], threads: int) -> SimpleProcess:
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

    def _get_axel_process(self, url: str, output_path: str, cwd: str, root_password: Optional[str], threads: int) -> SimpleProcess:
        cmd = ['axel', url, '-n', str(threads), '-4', '-c', '-T', '5']

        if not self.check_ssl:
            cmd.append('-k')

        if output_path:
            cmd.append(f'--output={output_path}')

        return SimpleProcess(cmd=cmd, cwd=cwd, root_password=root_password)

    def _rm_bad_file(self, file_name: str, output_path: str, cwd, handler: ProcessHandler, root_password: Optional[str]):
        to_delete = output_path if output_path else f'{cwd}/{file_name}'

        if to_delete and os.path.exists(to_delete):
            self.logger.info(f'Removing downloaded file {to_delete}')
            success, _ = handler.handle_simple(SimpleProcess(['rm', '-rf', to_delete], root_password=root_password))
            return success

    def _concat_file_size(self, file_url: str, base_substatus: StringIO, watcher: ProcessWatcher):
        watcher.change_substatus(f'{base_substatus.getvalue()} ( ? Mb )')

        try:
            size = self.http_client.get_content_length(file_url)

            if size:
                base_substatus.write(f' ( {size} )')
                watcher.change_substatus(base_substatus.getvalue())
        except Exception:
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

    def _download_with_threads(self, client: str, file_url: str, output_path: str, cwd: str,
                               max_threads: int, known_size: int, display_file_size: bool, handler: ProcessHandler,
                               root_password: Optional[str] = None, substatus_prefix: Optional[str] = None) \
            -> Tuple[float, bool]:

        threads = self._get_appropriate_threads_number(max_threads, known_size)

        if client == 'aria2':
            start_time = time.time()
            process = self._get_aria2c_process(file_url, output_path, cwd, root_password, threads)
            downloader = 'aria2'
        else:
            start_time = time.time()
            process = self._get_axel_process(file_url, output_path, cwd, root_password, threads)
            downloader = 'axel'

        name = file_url.split('/')[-1]

        if output_path and not RE_HAS_EXTENSION.match(name) and RE_HAS_EXTENSION.match(output_path):
            name = output_path.split('/')[-1]

        if handler.watcher:
            msg = StringIO()
            msg.write(f'{substatus_prefix} ' if substatus_prefix else '')
            msg.write(f"{bold('[{}]'.format(downloader))} {self.i18n['downloading']} {bold(name)}")

            if display_file_size:
                if known_size:
                    msg.write(f' ( {get_human_size_str(known_size)} )')
                    handler.watcher.change_substatus(msg.getvalue())
                else:
                    Thread(target=self._concat_file_size, args=(file_url, msg, handler.watcher), daemon=True).start()
            else:
                msg.write(' ( ? Mb )')
                handler.watcher.change_substatus(msg.getvalue())

        success, _ = handler.handle_simple(process)
        return start_time, success

    def download(self, file_url: str, watcher: ProcessWatcher, output_path: str = None, cwd: str = None, root_password: Optional[str] = None, substatus_prefix: str = None, display_file_size: bool = True, max_threads: int = None, known_size: int = None) -> bool:
        self.logger.info(f'Downloading {file_url}')
        handler = ProcessHandler(watcher)
        file_name = file_url.split('/')[-1]

        final_cwd = cwd if cwd else '.'

        success = False
        start_time = time.time()
        try:
            if output_path:
                if os.path.exists(output_path):
                    self.logger.info(f'Removing old file found before downloading: {output_path}')
                    os.remove(output_path)
                    self.logger.info(f'Old file {output_path} removed')
                else:
                    output_dir = os.path.dirname(output_path)

                    try:
                        Path(output_dir).mkdir(exist_ok=True, parents=True)
                    except OSError:
                        self.logger.error(f"Could not make download directory '{output_dir}'")
                        watcher.print(self.i18n['error.mkdir'].format(dir=output_dir))
                        return False

            threaded_client = self.get_available_multithreaded_tool()
            if threaded_client:
                start_time, success = self._download_with_threads(client=threaded_client, file_url=file_url,
                                                                  output_path=output_path,
                                                                  cwd=final_cwd, max_threads=max_threads,
                                                                  known_size=known_size, handler=handler,
                                                                  display_file_size=display_file_size,
                                                                  root_password=root_password)
            else:
                start_time = time.time()
                success = self._self_downloader.download(file_url=file_url, watcher=watcher, output_path=output_path,
                                                         cwd=cwd, root_password=root_password,
                                                         substatus_prefix=substatus_prefix,
                                                         display_file_size=display_file_size, max_threads=max_threads,
                                                         known_size=known_size)
        except Exception:
            traceback.print_exc()
            self._rm_bad_file(file_name, output_path, final_cwd, handler, root_password)

        final_time = time.time()
        self.logger.info(f'{file_name} download took {(final_time - start_time) / 60:.4f} minutes')

        if not success:
            self.logger.error(f"Could not download '{file_name}'")
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
        return True

    def get_supported_multithreaded_clients(self) -> Tuple[str, ...]:
        return self.supported_multithread_clients

    def is_multithreaded_client_available(self, name: str) -> bool:
        if name == 'aria2':
            return self.is_aria2c_available()
        elif name == 'axel':
            return self.is_axel_available()
        else:
            return False

    def list_available_multithreaded_clients(self) -> Tuple[str, ...]:
        return tuple(c for c in self.supported_multithread_clients if self.is_multithreaded_client_available(c))

    def get_supported_clients(self) -> Tuple[str, ...]:
        return "self", "aria2", "axel"
