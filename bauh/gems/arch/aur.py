import re
from typing import Set, List

from bauh.api.http import HttpClient

URL_INFO = 'https://aur.archlinux.org/rpc/?v=5&type=info&'
URL_SEARCH = 'https://aur.archlinux.org/rpc/?v=5&type=search&arg='


def map_pkgbuild(pkgbuild: str) -> dict:
    return {attr: val.replace('"', '').replace("'", '').replace('(', '').replace(')', '') for attr, val in re.findall(r'\n(\w+)=(.+)', pkgbuild)}


class AURClient:

    def __init__(self, http_client: HttpClient):
        self.http_client = http_client
        self.names_index = set()

    def search(self, words: str) -> dict:
        return self.http_client.get_json(URL_SEARCH + words)

    def get_info(self, names: Set[str]) -> List[dict]:
        res = self.http_client.get_json(URL_INFO + self._map_names_as_queries(names))
        return res['results'] if res and res.get('results') else []

    def _map_names_as_queries(self, names) -> str:
        return '&'.join(['arg[{}]={}'.format(i, n) for i, n in enumerate(names)])
