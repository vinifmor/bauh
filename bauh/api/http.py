import logging
import time
import traceback

import requests
import yaml

from bauh.commons import system


class HttpClient:

    def __init__(self, logger: logging.Logger, max_attempts: int = 2, timeout: int = 30, sleep: float = 0.5):
        self.max_attempts = max_attempts
        self.session = requests.Session()
        self.timeout = timeout
        self.sleep = sleep
        self.logger = logger

    def get(self, url: str, params: dict = None, headers: dict = None, allow_redirects: bool = True, ignore_ssl: bool = False, single_call: bool = False, session: bool = True) -> requests.Response:
        cur_attempts = 1

        while cur_attempts <= self.max_attempts:
            cur_attempts += 1

            try:
                args = {'timeout': self.timeout, 'allow_redirects': allow_redirects}

                if params:
                    args['params'] = params

                if headers:
                    args['headers'] = headers

                if ignore_ssl:
                    args['verify'] = False

                if session:
                    res = self.session.get(url, **args)
                else:
                    res = requests.get(url, **args)

                if res.status_code == 200:
                    return res

                if single_call:
                    return

                if self.sleep > 0:
                    time.sleep(self.sleep)
            except Exception as e:
                if isinstance(e, requests.exceptions.ConnectionError):
                    self.logger.error('Internet seems to be off')
                    raise

                self.logger.error("Could not retrieve data from '{}'".format(url))
                traceback.print_exc()
                continue

            self.logger.warning("Could not retrieve data from '{}'".format(url))

    def get_json(self, url: str, params: dict = None, headers: dict = None, allow_redirects: bool = True, session: bool = True):
        res = self.get(url, params=params, headers=headers, allow_redirects=allow_redirects, session=session)
        return res.json() if res else None

    def get_yaml(self, url: str, params: dict = None, headers: dict = None, allow_redirects: bool = True, session: bool = True):
        res = self.get(url, params=params, headers=headers, allow_redirects=allow_redirects, session=session)
        return yaml.safe_load(res.text) if res else None

    def get_content_length_in_bytes(self, url: str, session: bool = True) -> int:
        params = {'url': url, 'allow_redirects': True, 'stream': True}
        if session:
            res = self.session.get(**params)
        else:
            res = requests.get(**params)

        if res.status_code == 200:
            size = res.headers.get('Content-Length')

            if size:
                try:
                    return int(size)
                except:
                    pass

    def get_content_length(self, url: str, session: bool = True) -> str:
        size = self.get_content_length_in_bytes(url, session)

        if size:
            return system.get_human_size_str(size)

    def exists(self, url: str, session: bool = True, timeout: int = 5) -> bool:
        params = {'url': url, 'allow_redirects': True, 'verify': False, 'timeout': timeout}
        if session:
            res = self.session.head(**params)
        else:
            res = self.session.get(**params)

        return res.status_code in (200, 403)
        return False
