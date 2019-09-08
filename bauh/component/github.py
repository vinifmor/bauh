import os
from threading import Thread
from typing import Set

import requests

URL_RELEASES = 'https://api.github.com/repos/vinifmor/{}/releases'


class GitHubClient:

    def __init__(self):
        self.session = requests.session()

        if os.getenv('GITHUB_TOKEN'):
            self.session.headers['Authorization'] = 'token {}'.format(os.getenv('GITHUB_TOKEN'))

    def _add_version(self, name: str, components: dict):
        res = self.session.get(URL_RELEASES.format(name))

        if res and res.status_code == 200:
            components[name] = res.json()[0]['tag_name']

    def list_components(self, names: Set[str]) -> dict:  # TODO heandle no internet connection
        components = {}
        threads = []

        for name in names:
            t = Thread(target=self._add_version, args=(name, components))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        return components
