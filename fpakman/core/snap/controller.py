import os
import shutil
from argparse import Namespace
from datetime import datetime
from typing import Dict, List

from fpakman.core import disk
from fpakman.core.controller import ApplicationManager
from fpakman.core.disk import DiskCacheLoader
from fpakman.core.model import ApplicationData, Application, ApplicationUpdate
from fpakman.core.snap import snap
from fpakman.core.snap.model import SnapApplication
from fpakman.core.snap.worker import SnapAsyncDataLoader
from fpakman.core.system import FpakmanProcess
from fpakman.util.cache import Cache


class SnapManager(ApplicationManager):

    def __init__(self, app_args: Namespace,  api_cache: Cache, disk_cache: bool, http_session, locale_keys: dict):
        super(SnapManager, self).__init__(app_args=app_args, locale_keys=locale_keys)
        self.api_cache = api_cache
        self.http_session = http_session
        self.disk_cache = disk_cache

    def map_json(self, app_json: dict, installed: bool,  disk_loader: DiskCacheLoader) -> SnapApplication:
        app = SnapApplication(publisher=app_json.get('publisher'),
                              rev=app_json.get('rev'),
                              notes=app_json.get('notes'),
                              app_type=app_json.get('type'),
                              base_data=ApplicationData(id=app_json.get('name'),
                                                        name=app_json.get('name'),
                                                        version=app_json.get('version'),
                                                        latest_version=app_json.get('version'),
                                                        description=app_json.get('description')
                                                        ))

        if app.publisher:
            app.publisher = app.publisher.replace('*', '')

        app.installed = installed

        api_data = self.api_cache.get(app_json['name'])
        expired_data = api_data and api_data.get('expires_at') and api_data['expires_at'] <= datetime.utcnow()

        if (not api_data or expired_data) and not app.is_library():
            if disk_loader and app.installed:
                disk_loader.add(app)

            SnapAsyncDataLoader(app=app, api_cache=self.api_cache, manager=self, http_session=self.http_session, download_icons=self.app_args.download_icons).start()
        else:
            app.fill_cached_data(api_data)

        return app

    def search(self, word: str, disk_loader: DiskCacheLoader) -> Dict[str, List[SnapApplication]]:
        installed = self.read_installed(disk_loader)

        res = {'installed': [], 'new': []}

        for app_json in snap.search(word):

            already_installed = None

            if installed:
                already_installed = [i for i in installed if i.base_data.id == app_json.get('name')]
                already_installed = already_installed[0] if already_installed else None

            if already_installed:
                res['installed'].append(already_installed)
            else:
                res['new'].append(self.map_json(app_json, installed=False, disk_loader=disk_loader))

        return res

    def read_installed(self, disk_loader: DiskCacheLoader) -> List[SnapApplication]:
        return [self.map_json(app_json, installed=True, disk_loader=disk_loader) for app_json in snap.read_installed()]

    def downgrade_app(self, app: Application, root_password: str) -> FpakmanProcess:
        return FpakmanProcess(subproc=snap.downgrade_and_stream(app.base_data.name, root_password), wrong_error_phrase=None)

    def clean_cache_for(self, app: SnapApplication):
        self.api_cache.delete(app.base_data.name)

        if app.supports_disk_cache() and os.path.exists(app.get_disk_cache_path()):
            shutil.rmtree(app.get_disk_cache_path())

    def can_downgrade(self):
        return True

    def update_and_stream(self, app: SnapApplication) -> FpakmanProcess:
        pass

    def uninstall_and_stream(self, app: SnapApplication, root_password: str) -> FpakmanProcess:
        return FpakmanProcess(subproc=snap.uninstall_and_stream(app.base_data.name, root_password))

    def get_app_type(self):
        return SnapApplication

    def get_info(self, app: SnapApplication) -> dict:
        info = snap.get_info(app.base_data.name, attrs=('license', 'contact', 'commands', 'snap-id', 'tracking', 'installed'))
        info['description'] = app.base_data.description
        info['publisher'] = app.publisher
        info['revision'] = app.rev
        info['name'] = app.base_data.name

        if info.get('commands'):
            info['commands'] = ' '.join(info['commands'])

        return info

    def get_history(self, app: Application) -> List[dict]:
        return []

    def install_and_stream(self, app: SnapApplication, root_password: str) -> FpakmanProcess:
        return FpakmanProcess(subproc=snap.install_and_stream(app.base_data.name, app.confinement, root_password))

    def is_enabled(self) -> bool:
        return snap.is_installed()

    def cache_to_disk(self, app: Application, icon_bytes: bytes, only_icon: bool):
        if self.disk_cache and app.supports_disk_cache():
            disk.save(app, icon_bytes, only_icon)

    def requires_root(self, action: str, app: SnapApplication):
        return action != 'search'

    def refresh(self, app: SnapApplication, root_password: str) -> FpakmanProcess:
        return FpakmanProcess(subproc=snap.refresh_and_stream(app.base_data.name, root_password))

    def prepare(self):
        pass

    def list_updates(self) -> List[ApplicationUpdate]:
        return []

    def list_warnings(self) -> List[str]:
        if snap.get_snapd_version() == 'unavailable':
            return [self.locale_keys['snap.notification.snapd_unavailable']]

    def list_suggestions(self, limit: int) -> List[SnapApplication]:

        suggestions = []

        if limit != 0:
            for name in ('whatsdesk', 'slack', 'yakyak', 'instagraph', 'pycharm-professional', 'eclipse', 'gimp', 'supertuxkart'):
                res = snap.search(name, exact_name=True)
                if res:
                    suggestions.append(self.map_json(res[0], installed=False, disk_loader=None))

                if len(suggestions) == limit:
                    break

        return suggestions
