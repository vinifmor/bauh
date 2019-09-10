import os
from threading import Thread
from typing import Set

import requests
from bauh_api.exception import NoInternetException
from bauh_api.http import HttpClient
import logging

URL_RELEASES = 'https://api.github.com/repos/vinifmor/{}/releases'
URL_REQUIREMENTS = 'https://github.com/vinifmor/{name}/blob/{version}/requirements.txt'


class GitHubClient:

    def __init__(self, logger: logging.Logger):
        session = requests.session()

        if os.getenv('GITHUB_TOKEN'):
            session.headers['Authorization'] = 'token {}'.format(os.getenv('GITHUB_TOKEN'))

        self.http_client = HttpClient(session, logger)
        self.logger = logger

    def _add_version(self, name: str, components: dict):
        res = self.http_client.get_json(URL_RELEASES.format(name))

        if res:
            components[name] = res[0]['tag_name']

    def list_components(self, names: Set[str]) -> dict:
        try:
            components = {}
            threads = []

            for name in names:
                t = Thread(target=self._add_version, args=(name, components))
                t.start()
                threads.append(t)

            for t in threads:
                t.join()

            return components
        except requests.ConnectionError:
            raise NoInternetException()

    def get_requirements(self, name: str, version: str) -> str:
        res = self.http_client.get(URL_REQUIREMENTS.format(name=name, version=version))

        if res:
            return res.text
        else:
            self.logger.warning("Could not retrieve the requirements file for '{}' ({})".format(name, version))
