import logging
import os
import traceback
from typing import Optional

from colorama import Fore
from packaging.version import parse as parse_version

from bauh.api.abstract.model import PackageStatus
from bauh.api.http import HttpClient
from bauh.gems.arch.model import ArchPackage
from bauh.view.util.translation import I18n

URL_PKG_DOWNLOAD = 'https://aur.archlinux.org/{}'


class AURDataMapper:

    def __init__(self, http_client: HttpClient, i18n: I18n, logger: logging.Logger):
        self.http_client = http_client
        self.i18n = i18n
        self.logger = logger

    def fill_last_modified(self, pkg: ArchPackage, api_data: dict):
        last_modified = api_data.get('LastModified')
        if last_modified is not None and isinstance(last_modified, int):
            pkg.last_modified = last_modified
            self.logger.info("'last_modified' field ({}) set to package '{}'".format(last_modified, pkg.name))
        else:
            self.logger.warning("Could not set the 'last_modified' field ({}) to package '{}'".format(last_modified, pkg.name))

    def fill_api_data(self, pkg: ArchPackage, api_data: dict, fill_version: bool = True):
        pkg.id = api_data.get('ID')

        if not pkg.name:
            pkg.name = api_data.get('Name')

        if not pkg.description:
            pkg.description = api_data.get('Description')

        pkg.package_base = api_data.get('PackageBase')
        pkg.popularity = api_data.get('Popularity')
        pkg.votes = api_data.get('NumVotes')
        pkg.maintainer = api_data.get('Maintainer')
        pkg.url_download = URL_PKG_DOWNLOAD.format(api_data['URLPath']) if api_data.get('URLPath') else None

        if api_data['FirstSubmitted'] and isinstance(api_data['FirstSubmitted'], int):
            pkg.first_submitted = api_data['FirstSubmitted']

        if not pkg.installed:
            self.fill_last_modified(pkg=pkg, api_data=api_data)

        version = api_data.get('Version')

        if version:
            version = version.split(':')
            version = version[0] if len(version) == 1 else version[1]

        if fill_version:
            pkg.version = version

        pkg.latest_version = version

    @staticmethod
    def check_version_update(version: str, latest_version: str) -> bool:
        if version and latest_version and version != latest_version:
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
        if pkg.installed and os.path.exists(cached_pkgbuild):
            with open(cached_pkgbuild) as f:
                pkg.pkgbuild = f.read()
        else:
            res = self.http_client.get(pkg.get_pkg_build_url())

            if res and res.status_code == 200 and res.text:
                pkg.pkgbuild = res.text

    def map_api_data(self, apidata: dict, pkgs_installed: Optional[dict], categories: dict) -> ArchPackage:
        data = pkgs_installed.get(apidata.get('Name')) if pkgs_installed else None
        app = ArchPackage(name=apidata.get('Name'), installed=bool(data), repository='aur', i18n=self.i18n)
        app.status = PackageStatus.LOADING_DATA

        if categories:
            app.categories = categories.get(app.name)

        if data:
            app.version = data.get('version')
            app.description = data.get('description')

        self.fill_api_data(app, apidata, fill_version=not data)
        return app

    def check_update(self, pkg: ArchPackage, last_modified: Optional[int]) -> bool:
        valid_last_modified = last_modified is not None and isinstance(last_modified, int)

        if not valid_last_modified:
            self.logger.warning("'last_modified' timestamp informed for package '{}' is invalid: {}".format(pkg.name, valid_last_modified))

        pkg_last_modified_ts = pkg.last_modified if pkg.last_modified is not None else pkg.install_date

        if pkg.last_modified is None:
            self.logger.warning("AUR package '{}' has no 'last_modified' field set.".format(pkg.name))

            if pkg.install_date is None:
                self.logger.warning("AUR package '{}' has no 'install_date' field set".format(pkg.name))
                self.logger.warning("Update checking for AUR package '{}' will only consider version strings".format(pkg.name))
            else:
                self.logger.warning("AUR package {} 'install_date' field will be used for update checking".format(pkg.name))

        if pkg_last_modified_ts is not None and valid_last_modified and pkg_last_modified_ts < last_modified:
            return True
        else:
            return self.check_version_update(pkg.version, pkg.latest_version)
