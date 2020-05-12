import re
from datetime import datetime

from bauh.api.abstract.model import PackageStatus
from bauh.api.http import HttpClient
from bauh.gems.arch.model import ArchPackage
from bauh.view.util.translation import I18n

URL_PKG_DOWNLOAD = 'https://aur.archlinux.org/{}'
RE_LETTERS = re.compile(r'\.([a-zA-Z]+)-\d+$')
RE_VERSION_SPLIT = re.compile(r'[a-zA-Z]+|\d+|[\.\-_@#]+')

BAUH_PACKAGES = {'bauh', 'bauh-staging'}
RE_SFX = ('r', 're', 'release')
GA_SFX = ('ga', 'ge')
RC_SFX = ('rc',)
BETA_SFX = ('b', 'beta')
AL_SFX = ('alpha', 'alfa')
DEV_SFX = ('dev', 'devel', 'development')

V_SUFFIX_MAP = {s: {'c': sfxs[0], 'p': idx} for idx, sfxs in enumerate([RE_SFX, GA_SFX, RC_SFX, BETA_SFX, AL_SFX, DEV_SFX]) for s in sfxs}


class ArchDataMapper:

    def __init__(self, http_client: HttpClient, i18n: I18n):
        self.http_client = http_client
        self.i18n = i18n

    def fill_api_data(self, pkg: ArchPackage, package: dict, fill_version: bool = True):

        version = package.get('Version')

        if version:
            version = version.split(':')
            version = version[0] if len(version) == 1 else version[1]

        pkg.id = package.get('ID')
        pkg.name = package.get('Name')

        if fill_version:
            pkg.version = version

        pkg.latest_version = version
        pkg.description = package.get('Description')

        pkg.package_base = package.get('PackageBase')
        pkg.popularity = package.get('Popularity')
        pkg.votes = package.get('NumVotes')
        pkg.maintainer = package.get('Maintainer')
        pkg.url_download = URL_PKG_DOWNLOAD.format(package['URLPath']) if package.get('URLPath') else None
        pkg.first_submitted = datetime.fromtimestamp(package['FirstSubmitted']) if package.get('FirstSubmitted') else None
        pkg.last_modified = datetime.fromtimestamp(package['LastModified']) if package.get('LastModified') else None
        pkg.update = self.check_update(pkg.version, pkg.latest_version, check_suffix=pkg.name in BAUH_PACKAGES)

    @staticmethod
    def check_update(version: str, latest_version: str, check_suffix: bool = False) -> bool:
        if version and latest_version:

            if check_suffix:
                current_sfx = RE_LETTERS.findall(version)
                latest_sf = RE_LETTERS.findall(latest_version)

                if latest_sf and current_sfx:
                    current_sfx = current_sfx[0]
                    latest_sf = latest_sf[0]

                    current_sfx_data = V_SUFFIX_MAP.get(current_sfx.lower())
                    latest_sfx_data = V_SUFFIX_MAP.get(latest_sf.lower())

                    if current_sfx_data and latest_sfx_data:
                        nversion = version.split(current_sfx)[0]
                        nlatest = latest_version.split(latest_sf)[0]

                        if nversion == nlatest:
                            if current_sfx_data['c'] != latest_sfx_data['c']:
                                return latest_sfx_data['p'] < current_sfx_data['p']
                            else:
                                return ''.join(latest_version.split(latest_sf)) > ''.join(version.split(current_sfx))

                        return nlatest > nversion

            latest_split = RE_VERSION_SPLIT.findall(latest_version)
            current_split = RE_VERSION_SPLIT.findall(version)

            for idx in range(len(latest_split)):
                if idx < len(current_split):
                    latest_part = latest_split[idx]
                    current_part = current_split[idx]

                    if latest_part != current_part:

                        try:
                            dif = int(latest_part) - int(current_part)

                            if dif > 0:
                                return True
                            elif dif < 0:
                                return False
                            else:
                                continue

                        except ValueError:
                            if latest_part.isdigit():
                                return True
                            elif current_part.isdigit():
                                return False
                            else:
                                return latest_part > current_part
        return False

    def fill_package_build(self, pkg: ArchPackage):
        res = self.http_client.get(pkg.get_pkg_build_url())

        if res and res.status_code == 200 and res.text:
            pkg.pkgbuild = res.text

    def map_api_data(self, apidata: dict, installed: dict, categories: dict) -> ArchPackage:
        data = installed.get(apidata.get('Name')) if installed else None
        app = ArchPackage(name=apidata.get('Name'), installed=bool(data), repository='aur', i18n=self.i18n)
        app.status = PackageStatus.LOADING_DATA

        if categories:
            app.categories = categories.get(app.name)

        if data:
            app.version = data.get('version')
            app.description = data.get('description')

        self.fill_api_data(app, apidata, fill_version=not data)

        return app
