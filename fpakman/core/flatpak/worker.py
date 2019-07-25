import time
import traceback
from threading import Thread

from colorama import Fore

from fpakman.core.controller import ApplicationManager
from fpakman.core.flatpak import flatpak
from fpakman.core.flatpak.constants import FLATHUB_API_URL, FLATHUB_URL
from fpakman.core.flatpak.model import FlatpakApplication
from fpakman.core.model import ApplicationStatus
from fpakman.core.worker import AsyncDataLoader
from fpakman.util.cache import Cache


class FlatpakAsyncDataLoader(AsyncDataLoader):

    def __init__(self, app: FlatpakApplication, manager: ApplicationManager, http_session, api_cache: Cache, attempts: int = 2, timeout: int = 30):
        super(FlatpakAsyncDataLoader, self).__init__(app=app)
        self.manager = manager
        self.http_session = http_session
        self.attempts = attempts
        self.api_cache = api_cache
        self.persist = False
        self.timeout = timeout

    def run(self):
        if self.app:
            self.app.status = ApplicationStatus.LOADING_DATA

            for _ in range(0, self.attempts):
                try:
                    res = self.http_session.get('{}/apps/{}'.format(FLATHUB_API_URL, self.app.base_data.id), timeout=self.timeout)

                    if res.status_code == 200 and res.text:
                        data = res.json()

                        if not self.app.base_data.version:
                            self.app.base_data.version = data.get('version')

                        if not self.app.base_data.name:
                            self.app.base_data.name = data.get('name')

                        self.app.base_data.description = data.get('description', data.get('summary', None))
                        self.app.base_data.icon_url = data.get('iconMobileUrl', None)
                        self.app.base_data.latest_version = data.get('currentReleaseVersion', self.app.base_data.version)

                        if not self.app.base_data.version and self.app.base_data.latest_version:
                            self.app.base_data.version = self.app.base_data.latest_version

                        if self.app.base_data.icon_url and self.app.base_data.icon_url.startswith('/'):
                            self.app.base_data.icon_url = FLATHUB_URL + self.app.base_data.icon_url

                        loaded_data = self.app.get_data_to_cache()

                        self.api_cache.add(self.app.base_data.id, loaded_data)
                        self.app.status = ApplicationStatus.READY
                        self.persist = self.app.supports_disk_cache()
                        break
                    else:
                        self.log_msg("Could not retrieve app data for id '{}'. Server response: {}. Body: {}".format(
                            self.app.base_data.id, res.status_code, res.content.decode()), Fore.RED)
                except:
                    self.log_msg("Could not retrieve app data for id '{}'".format(self.app.base_data.id), Fore.YELLOW)
                    traceback.print_exc()
                    time.sleep(0.5)

            self.app.status = ApplicationStatus.READY

            if self.persist:
                self.manager.cache_to_disk(app=self.app, icon_bytes=None, only_icon=False)

    def clone(self) -> "FlatpakAsyncDataLoader":
        return FlatpakAsyncDataLoader(manager=self.manager,
                                      api_cache=self.api_cache,
                                      attempts=self.attempts,
                                      http_session=self.http_session,
                                      timeout=self.timeout,
                                      app=self.app)


class FlatpakUpdateLoader(Thread):

    def __init__(self, app: dict, http_session, attempts: int = 2, timeout: int = 20):
        super(FlatpakUpdateLoader, self).__init__(daemon=True)
        self.app = app
        self.http_session = http_session
        self.attempts = attempts
        self.timeout = timeout

    def run(self):

        if self.app.get('ref') is None:
            self.app.update(flatpak.get_app_info_fields(self.app['id'], self.app['branch'], fields=['ref'], check_runtime=True))
        else:
            self.app['runtime'] = self.app['ref'].startswith('runtime/')

        if not self.app['runtime']:
            current_attempts = 0

            while current_attempts < self.attempts:

                current_attempts += 1

                try:
                    res = self.http_session.get('{}/apps/{}'.format(FLATHUB_API_URL, self.app['id']), timeout=self.timeout)

                    if res.status_code == 200 and res.text:
                        data = res.json()

                        if data.get('currentReleaseVersion'):
                            self.app['version'] = data['currentReleaseVersion']
                            
                        break
                except:
                    traceback.print_exc()
                    time.sleep(0.5)
