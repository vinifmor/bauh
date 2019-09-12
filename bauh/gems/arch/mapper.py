from datetime import datetime

from bauh.api.abstract.model import PackageStatus
from bauh.api.http import HttpClient
from bauh.gems.arch.model import ArchPackage

URL_PKG_DOWNLOAD = 'https://aur.archlinux.org/{}'


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
        pkg.update = pkg.version and pkg.latest_version and pkg.latest_version > pkg.version

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
