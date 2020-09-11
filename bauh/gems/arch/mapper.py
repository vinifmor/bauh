import os
import traceback
from datetime import datetime

from colorama import Fore
from pkg_resources import parse_version

from bauh.api.abstract.model import PackageStatus
from bauh.api.http import HttpClient
from bauh.gems.arch.model import ArchPackage
from bauh.view.util.translation import I18n

URL_PKG_DOWNLOAD = 'https://aur.archlinux.org/{}'


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
        pkg.update = self.check_update(pkg.version, pkg.latest_version)

    @staticmethod
    def check_update(version: str, latest_version: str) -> bool:
        if version and latest_version:
            try:
                ver_epoch, latest_epoch = version.split(':'), latest_version.split(':')

                if len(ver_epoch) > 1 and len(latest_epoch) > 1:
                    parsed_ver_epoch, parsed_latest_epoch = parse_version(ver_epoch[0]), parse_version(latest_epoch[0])

                    if parsed_ver_epoch == parsed_latest_epoch:
                        return parse_version(''.join(ver_epoch[1:])) < parse_version(''.join(latest_epoch[1:]))
                    else:
                        return parsed_ver_epoch < parsed_latest_epoch
                elif len(ver_epoch) > 1 and len(latest_epoch) == 1:
                    return False
                elif len(ver_epoch) == 1 and len(latest_epoch) > 1:
                    return True
                else:
                    return parse_version(version) < parse_version(latest_version)
            except:
                print('{}Version: {}. Latest version: {}{}'.format(Fore.RED, version, latest_version, Fore.RESET))
                traceback.print_exc()
                return False

        return False

    def fill_package_build(self, pkg: ArchPackage):
        cached_pkgbuild = pkg.get_cached_pkgbuild_path()
        if os.path.exists(cached_pkgbuild):
            with open(cached_pkgbuild) as f:
                pkg.pkgbuild = f.read()
        else:
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
