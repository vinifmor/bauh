import os
import re
import shutil
import time
import traceback
from collections import defaultdict
from io import StringIO, BytesIO
from logging import Logger
from math import floor
from pathlib import Path
from threading import Thread
from typing import Optional, Tuple, Dict

from requests import Response

from bauh.api.abstract.download import FileDownloader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.http import HttpClient
from bauh.commons.html import bold
from bauh.commons.system import ProcessHandler, SimpleProcess
from bauh.commons.view_utils import get_human_size_str
from bauh.view.util.translation import I18n

RE_HAS_EXTENSION = re.compile(r'.+\.\w+$')


class MultithreadedFileDownload:

    def __init__(self, file_url: str, file_length: int, output_path: str,
                 threads: int, download_msg: str, http_client: HttpClient, logger: Logger):
        self._file_url = file_url
        self._file_length = file_length
        self._output_path = output_path
        self._download_msg = download_msg
        self._threads = threads
        self._logger = logger
        self._client = http_client
        self._failed = False
        self._parts: Dict[int, BytesIO] = dict()
        self._total_downloaded: Dict[int, int] = defaultdict(lambda: 0)
        self._chunk_size = 1024

    def _download_part(self, id_: int, file_url: str, start_byte: int, end_byte: int):
        headers = {"Range": f"bytes={start_byte}-{end_byte}"}
        try:
            self._logger.info(f"Starting to download part {id_} of {file_url} "
                              f"(start_byte={start_byte}, end_byte={end_byte}")
            res = self._client.get(url=file_url, headers=headers, stream=True)

            if res.status_code != 206:
                self._logger.warning(f"The server did not accept partial download of file ({file_url}) [thread={id_})")
                self._failed = True
                return

            byte_stream = BytesIO()
            for chunk in res.iter_content(chunk_size=self._chunk_size):
                if self._failed:
                    # if another thread failed, stops immediately
                    self._logger.warning(f"Interrupting file part {id_} download ({file_url})")
                    return

                if chunk:
                    byte_stream.write(chunk)
                    self._total_downloaded[id_] += len(chunk)

            self._logger.info(f"Download succeeded for file part {id_} ({file_url})")
            self._parts[id_] = byte_stream
        except Exception:
            self._logger.error(f"Unexpected exception when downloading file part '{id_}' from '{file_url}'")
            traceback.print_exc()
            self._failed = True

    def start(self, watcher: Optional[ProcessWatcher] = None) -> bool:
        # TODO calculate the number of threads based on the chunk size and content length
        part_size = int(self._file_length / self._threads)
        ranges = [(i * part_size, (i + 1) * part_size - 1) for i in range(self._threads - 1)]
        ranges.append(((self._threads - 1) * part_size, self._file_length - 1))

        threads = []
        self._logger.info(f'Downloading {self._file_url} with {self._threads} threads')
        for idx, (start_byte, end_byte) in enumerate(ranges):
            t = Thread(target=self._download_part, daemon=True, kwargs={"id_": idx, "file_url": self._file_url,
                                                                        "start_byte": start_byte, "end_byte": end_byte})
            t.start()
            threads.append(t)

        total_size_str = get_human_size_str(self._file_length)
        total_downloaded = 0  # stores the latest download sum (only required in case the watcher is defined)
        while not self._failed:
            threads_finished = 0
            for t in threads:
                if not t.is_alive():
                    threads_finished += 1

            if watcher:
                current_total = sum(tuple(self._total_downloaded.values()))

                if current_total != total_downloaded:
                    total_downloaded = current_total

                    perc = f"({(total_downloaded / self._file_length) * 100:.2f}%) "
                    watcher.change_substatus(f"{perc}{self._download_msg} "
                                             f"({get_human_size_str(total_downloaded)} / {total_size_str})")

            if threads_finished == len(threads):
                break

        if self._failed:
            # wait for all threads to finish in case one failed
            for t in threads:
                t.join()

            return False

        try:
            with open(self._output_path, "wb+") as f:
                for _, part in sorted(self._parts.items()):
                    f.write(part.getvalue())
        except Exception:
            self._logger.error(f"Unexpected exception when saving downloaded content to disk: {self._output_path}")
            traceback.print_exc()
            return False

        return True


class SelfFileDownloader(FileDownloader):

    def __init__(self, logger: Logger, i18n: I18n, http_client: HttpClient,
                 check_ssl: bool, multithread: bool = False):
        self._logger = logger
        self._i18n = i18n
        self._client = http_client
        self._ssl = check_ssl
        self._multithread = multithread

    def is_multithreaded(self) -> bool:
        return True

    def can_work(self) -> bool:
        return True

    def get_supported_multithreaded_clients(self) -> Tuple[str, ...]:
        return tuple()

    def is_multithreaded_client_available(self, name: str) -> bool:
        return True

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

            if self._multithread:
                self._logger.warning(f"Multi-threaded download will not be possible for file '{file_url}'")

        file_name = file_url.split("/")[-1]
        msg = StringIO()
        msg.write(f"{substatus_prefix} " if substatus_prefix else "")
        msg.write(f"{self._i18n['downloading']} {bold(file_name)}")
        download_msg = msg.getvalue()

        server_supports_multithread = res.headers.get("accept-ranges") == "bytes"
        multithread = self._multithread and server_supports_multithread

        if self._multithread and not server_supports_multithread:
            self._logger.warning(f"It will not be possible to download file {file_url} using threads: "
                                 f"the server does not support it")

        if not content_length or not multithread:
            return self._download_single_thread(file_url=file_url, output_path=output_path, res=res,
                                                base_msg=download_msg, watcher=watcher, content_length=content_length)

        num_threads = max_threads if isinstance(max_threads, int) and max_threads > 0 else 10
        multithread_download = MultithreadedFileDownload(file_url=file_url, file_length=content_length,
                                                         output_path=output_path, download_msg=download_msg,
                                                         http_client=self._client, logger=self._logger,
                                                         threads=num_threads)
        return multithread_download.start(watcher=watcher)

    def _download_single_thread(self, file_url: str, output_path: str,
                                res: Response, base_msg: str,  watcher: ProcessWatcher,
                                content_length: Optional[int] = None) -> bool:
        byte_stream = BytesIO()
        total_downloaded = 0
        known_size = content_length and content_length > 0
        total_size_str = get_human_size_str(content_length) if known_size > 0 else "?"

        self._logger.info(f'Downloading {file_url}')
        try:
            for data in res.iter_content(chunk_size=1024):
                byte_stream.write(data)
                total_downloaded += len(data)
                perc = f"({(total_downloaded / content_length) * 100:.2f}%) " if known_size > 0 else ""
                watcher.change_substatus(f"{perc}{base_msg} "
                                         f"({get_human_size_str(total_downloaded)} / {total_size_str})")
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
                                                   check_ssl=check_ssl,
                                                   multithread=multithread_enabled)

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
                        self.logger.error(f"Could not make download directory '{output_dir}' ({file_url})")
                        watcher.print(self.i18n['error.mkdir'].format(dir=output_dir))
                        return False

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
