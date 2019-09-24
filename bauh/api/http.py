import logging
import time
import traceback

import requests


class HttpClient:

    def __init__(self, logger: logging.Logger, max_attempts: int = 2, timeout: int = 30, sleep: float = 0.5):
        self.max_attempts = max_attempts
        self.session = requests.Session()
        self.timeout = timeout
        self.sleep = sleep
        self.logger = logger

    def get(self, url: str):
        cur_attempts = 1

        while cur_attempts <= self.max_attempts:
            cur_attempts += 1

            try:
                res = self.session.get(url, timeout=self.timeout)

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

    def get_json(self, url: str):
        res = self.get(url)
        return res.json() if res else None

    def get_content_length(self, url: str) -> int:
        """
        :param url:
        :return:
        """
        res = self.session.head(url)

        if res.status_code == 200:
            return res.headers['content-length']
