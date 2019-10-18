import logging
import time
import traceback

import requests

SIZE_MULTIPLIERS = ((0.001, 'Kb'), (0.000001, 'Mb'), (0.000000001, 'Gb'), (0.000000000001, 'Tb'))


class HttpClient:

    def __init__(self, logger: logging.Logger, max_attempts: int = 2, timeout: int = 30, sleep: float = 0.5):
        self.max_attempts = max_attempts
        self.session = requests.Session()
        self.timeout = timeout
        self.sleep = sleep
        self.logger = logger

    def get(self, url: str, params: dict = None, headers: dict = None, allow_redirects: bool = True):
        cur_attempts = 1

        while cur_attempts <= self.max_attempts:
            cur_attempts += 1

            try:
                args = {'timeout': self.timeout, 'allow_redirects': allow_redirects}

                if params:
                    args['params'] = params

                if headers:
                    args['headers'] = headers

                res = self.session.get(url, **args)

                if res.status_code == 200:
                    return res

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

    def get_json(self, url: str, params: dict = None, headers: dict = None, allow_redirects: bool = True):
        res = self.get(url, params=params, headers=headers, allow_redirects=allow_redirects)
        return res.json() if res else None

    def get_content_length(self, url: str) -> str:
        """
        :param url:
        :return:
        """
        res = self.session.get(url, allow_redirects=True, stream=True)

        if res.status_code == 200:
            size = res.headers.get('Content-Length')

            if size is not None:
                size = int(size)
                for m in SIZE_MULTIPLIERS:
                    size_str = str(size * m[0])

                    if len(size_str.split('.')[0]) < 4:
                        return '{0:.2f}'.format(float(size_str)) + ' ' +  m[1]
                return str(size)
