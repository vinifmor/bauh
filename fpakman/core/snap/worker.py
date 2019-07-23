import time
import traceback

from bs4 import BeautifulSoup
from colorama import Fore

from fpakman.core.controller import ApplicationManager
from fpakman.core.model import ApplicationStatus
from fpakman.core.snap import snap
from fpakman.core.snap.constants import SNAP_STORE_URL
from fpakman.core.snap.model import SnapApplication
from fpakman.core.worker import AsyncDataLoader
from fpakman.util.cache import Cache


class SnapAsyncDataLoader(AsyncDataLoader):

    def __init__(self, app: SnapApplication, manager: ApplicationManager, http_session, api_cache: Cache, download_icons: bool, attempts: int = 2, timeout: int = 30):
        super(SnapAsyncDataLoader, self).__init__(app=app)
        self.manager = manager
        self.http_session = http_session
        self.attempts = attempts
        self.api_cache = api_cache
        self.timeout = timeout
        self.to_persist = {}  # stores all data loaded by the instance
        self.download_icons = download_icons

    def run(self):
        if self.app:
            self.app.status = ApplicationStatus.LOADING_DATA
            if not self.app.base_data.description:
                self.app.base_data.description = snap.get_info(self.app.base_data.name, ('description',)).get('description')

            for _ in range(0, self.attempts):
                try:
                    res = self.http_session.get('{}/{}'.format(SNAP_STORE_URL, self.app.base_data.name),
                                                timeout=self.timeout)

                    if res.status_code == 200 and res.text:
                        soup = BeautifulSoup(res.text, 'html.parser')
                        input_install_cmd = soup.find("input", {"id": "snap-install"})

                        api_data = {
                            'install_cmd': input_install_cmd.get("value").strip(),
                            'description': self.app.base_data.description
                        }

                        img_icon = None

                        if self.download_icons:
                            img_icon = soup.find('img', {"class": "p-snap-heading__icon"})

                        if img_icon and img_icon.get("src") and 'snapcraft-missing-icon' not in img_icon.get('src'):
                            api_data['icon_url'] = img_icon.get("src")

                        self.api_cache.add(self.app.base_data.id, api_data)
                        self.app.install_cmd = api_data['install_cmd']
                        self.app.base_data.icon_url = api_data.get('icon_url')
                        self.app.status = ApplicationStatus.READY

                        if self.app.supports_disk_cache():
                            self.to_persist[self.app.base_data.id] = self.app

                        break
                    else:
                        self.log_msg("Could not retrieve app data for id '{}'. Server response: {}. Body: {}".format(self.app.base_data.id, res.status_code, res.content.decode()), Fore.RED)
                except:
                    self.log_msg("Could not retrieve app data for id '{}'".format(app.base_data.id), Fore.YELLOW)
                    traceback.print_exc()
                    time.sleep(0.5)

            self.app.status = ApplicationStatus.READY

    def clone(self) -> "SnapAsyncDataLoader":
        return SnapAsyncDataLoader(manager=self.manager,
                                   api_cache=self.api_cache,
                                   attempts=self.attempts,
                                   http_session=self.http_session,
                                   timeout=self.timeout,
                                   app=self.app)

    def cache_to_disk(self):
        if self.to_persist:
            for app in self.to_persist.values():
                self.manager.cache_to_disk(app=app, icon_bytes=None, only_icon=False)

            self.to_persist = {}
