import logging
import os
import re
from typing import Set, List

from bauh.api.http import HttpClient
import urllib.parse

from bauh.gems.arch import pacman, AUR_INDEX_FILE
from bauh.gems.arch.exceptions import PackageNotFoundException

URL_INFO = 'https://aur.archlinux.org/rpc/?v=5&type=info&'
URL_SRC_INFO = 'https://aur.archlinux.org/cgit/aur.git/plain/.SRCINFO?h='
URL_SEARCH = 'https://aur.archlinux.org/rpc/?v=5&type=search&arg='

RE_SRCINFO_KEYS = re.compile(r'(\w+)\s+=\s+(.+)\n')

KNOWN_LIST_FIELDS = ('validpgpkeys', 'depends', 'optdepends', 'sha512sums', 'sha512sums_x86_64', 'source', 'source_x86_64')


def map_pkgbuild(pkgbuild: str) -> dict:
    return {attr: val.replace('"', '').replace("'", '').replace('(', '').replace(')', '') for attr, val in re.findall(r'\n(\w+)=(.+)', pkgbuild)}


class AURClient:

    def __init__(self, http_client: HttpClient, logger: logging.Logger):
        self.http_client = http_client
        self.logger = logger

    def search(self, words: str) -> dict:
        return self.http_client.get_json(URL_SEARCH + words)

    def get_info(self, names: Set[str]) -> List[dict]:
        res = self.http_client.get_json(URL_INFO + self._map_names_as_queries(names))
        return res['results'] if res and res.get('results') else []

    def get_src_info(self, name: str) -> dict:
        res = self.http_client.get(URL_SRC_INFO + urllib.parse.quote(name))

        if res and res.text:
            info = {}
            for field in RE_SRCINFO_KEYS.findall(res.text):
                if field[0] not in info:
                    info[field[0]] = [field[1]] if field[0] in KNOWN_LIST_FIELDS else field[1]
                else:
                    if not isinstance(info[field[0]], list):
                        info[field[0]] = [info[field[0]]]

                    info[field[0]].append(field[1])

            return info

    def get_all_dependencies(self, name: str) -> Set[str]:
        deps = set()
        info = self.get_src_info(name)

        if not info:
            raise PackageNotFoundException(name)

        for attr in ('makedepends', 'depends', 'checkdepends'):
            if info.get(attr):
                deps.update([pacman.RE_DEP_OPERATORS.split(dep)[0] for dep in info[attr]])

        return deps

    def _map_names_as_queries(self, names) -> str:
        return '&'.join(['arg[{}]={}'.format(i, urllib.parse.quote(n)) for i, n in enumerate(names)])

    def read_local_index(self) -> dict:
        self.logger.info('Checking if the AUR index file exists')
        if os.path.exists(AUR_INDEX_FILE):
            self.logger.info('Reading AUR index file from {}'.format(AUR_INDEX_FILE))
            index = {}
            with open(AUR_INDEX_FILE) as f:
                for l in f.readlines():
                    if l:
                        lsplit = l.split('=')
                        index[lsplit[0]] = lsplit[1].strip()
            self.logger.info("AUR index file read")
            return index
        self.logger.warning('The AUR index file was not found')
