import re
from datetime import datetime

from bauh.api.abstract.model import PackageStatus
from bauh.api.http import HttpClient
from bauh.gems.arch.model import ArchPackage

URL_PKG_DOWNLOAD = 'https://aur.archlinux.org/{}'
RE_LETTERS = re.compile(r'\.([a-zA-Z]+)-\d+$')
RE_ANY_LETTER = re.compile(r'[a-zA-Z]')
RE_VERSION_DELS = re.compile(r'[.:#@\-_]')

RE_SFX = ('r', 're', 'release')
GA_SFX = ('ga', 'ge')
RC_SFX = ('rc',)
BETA_SFX = ('b', 'beta')
AL_SFX = ('alpha', 'alfa')
DEV_SFX = ('dev', 'devel', 'development')

V_SUFFIX_MAP = {s: {'c': sfxs[0], 'p': idx} for idx, sfxs in enumerate([RE_SFX, GA_SFX, RC_SFX, BETA_SFX, AL_SFX, DEV_SFX]) for s in sfxs}


class ArchDataMapper:

    def __init__(self, http_client: HttpClient):
        self.http_client = http_client

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
        pkg.update = self.check_update(pkg.version, pkg.latest_version)

    @staticmethod
    def check_update(version: str, latest_version: str) -> bool:
        if version and latest_version:
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

            latest_split = RE_VERSION_DELS.split(latest_version)
            version_split = RE_VERSION_DELS.split(version)

            for idx in range(len(latest_split)):
                if idx < len(version_split):
                    latest_part = latest_split[idx]
                    version_part = version_split[idx]

                    if latest_part != version_part:
                        if RE_ANY_LETTER.findall(latest_part) or RE_ANY_LETTER.findall(version_part):
                            return latest_part > version_part
                        else:
                            dif = int(latest_part) - int(version_part)

                            if dif > 0:
                                return True
                            elif dif < 0:
                                return False
                            else:
                                continue
        return False

    def fill_package_build(self, pkg: ArchPackage):
        res = self.http_client.get(pkg.get_pkg_build_url())

        if res and res.status_code == 200 and res.text:
            pkg.pkgbuild = res.text

    def map_api_data(self, apidata: dict, installed: dict) -> ArchPackage:
        data = installed.get(apidata.get('Name'))
        app = ArchPackage(name=apidata.get('Name'), installed=bool(data), mirror='aur')
        app.status = PackageStatus.LOADING_DATA

        if data:
            app.version = data.get('version')
            app.description = data.get('description')

        self.fill_api_data(app, apidata, fill_version=not data)
        return app
