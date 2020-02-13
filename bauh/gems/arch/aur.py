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
RE_SPLIT_DEP = re.compile(r'[<>]?=')

KNOWN_LIST_FIELDS = ('validpgpkeys',
                     'checkdepends',
                     'checkdepends_x86_64',
                     'checkdepends_i686',
                     'depends',
                     'depends_x86_64',
                     'depends_i686',
                     'optdepends',
                     'optdepends_x86_64',
                     'optdepends_i686',
                     'sha512sums',
                     'sha512sums_x86_64',
                     'source',
                     'source_x86_64',
                     'source_i686',
                     'makedepends',
                     'makedepends_x86_64',
                     'makedepends_i686')


def map_pkgbuild(pkgbuild: str) -> dict:
    return {attr: val.replace('"', '').replace("'", '').replace('(', '').replace(')', '') for attr, val in re.findall(r'\n(\w+)=(.+)', pkgbuild)}


def map_srcinfo(string: str, fields: Set[str] = None) -> dict:
    info = {}

    if fields:
        field_re = re.compile(r'({})\s+=\s+(.+)\n'.format('|'.join(fields)))
    else:
        field_re = RE_SRCINFO_KEYS

    for match in field_re.finditer(string):
        field = RE_SPLIT_DEP.split(match.group(0))
        key = field[0].strip()
        val = field[1].strip()

        if key not in info:
            info[key] = [val] if key in KNOWN_LIST_FIELDS else val
        else:
            if not isinstance(info[key], list):
                info[key] = [info[key]]

            info[key].append(val)

    return info


class AURClient:

    def __init__(self, http_client: HttpClient, logger: logging.Logger, x86_64: bool):
        self.http_client = http_client
        self.logger = logger
        self.x86_64 = x86_64

    def search(self, words: str) -> dict:
        return self.http_client.get_json(URL_SEARCH + words)

    def get_info(self, names: Set[str]) -> List[dict]:
        res = self.http_client.get_json(URL_INFO + self._map_names_as_queries(names))
        return res['results'] if res and res.get('results') else []

    def get_src_info(self, name: str) -> dict:
        res = self.http_client.get(URL_SRC_INFO + urllib.parse.quote(name))

        if res and res.text:
            return map_srcinfo(res.text)

        self.logger.warning('No .SRCINFO found for {}'.format(name))
        self.logger.info('Checking if {} is based on another package'.format(name))
        # if was not found, it may be based on another package.
        infos = self.get_info({name})

        if infos:
            info = infos[0]

            info_name = info.get('Name')
            info_base = info.get('PackageBase')
            if info_name and info_base and info_name != info_base:
                self.logger.info('{p} is based on {b}. Retrieving {b} .SRCINFO'.format(p=info_name, b=info_base))
                return self.get_src_info(info_base)

    def extract_required_dependencies(self, srcinfo: dict) -> Set[str]:
        deps = set()
        for attr in ('makedepends',
                     'makedepends_{}'.format('x86_64' if self.x86_64 else 'i686'),
                     'depends',
                     'depends_{}'.format('x86_64' if self.x86_64 else 'i686'),
                     'checkdepends',
                     'checkdepends_{}'.format('x86_64' if self.x86_64 else 'i686')):
            if srcinfo.get(attr):
                deps.update([pacman.RE_DEP_OPERATORS.split(dep)[0] for dep in srcinfo[attr]])

        return deps

    def get_required_dependencies(self, name: str) -> Set[str]:
        info = self.get_src_info(name)

        if not info:
            raise PackageNotFoundException(name)

        return self.extract_required_dependencies(info)

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
