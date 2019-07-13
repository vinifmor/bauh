import traceback
from io import StringIO
from threading import Thread
from typing import List

import requests
from colorama import Fore

from fpakman.core.constants import FLATHUB_API_URL, FLATHUB_URL
from fpakman.core.controller import ApplicationManager
from fpakman.core.model import FlatpakApplication, ApplicationStatus
from fpakman.util.cache import Cache


class FlatpakAsyncDataLoader(Thread):

    def __init__(self, manager: ApplicationManager, http_session, api_cache: Cache, attempts: int = 3, apps: List[FlatpakApplication] = []):
        super(FlatpakAsyncDataLoader, self).__init__(daemon=True)
        self.apps = apps
        self.http_session = http_session
        self.attempts = attempts
        self.api_cache = api_cache
        self.id_ = '{}#{}'.format(self.__class__.__name__, id(self))
        self.stop = False
        self.to_persist = {}  # stores all data loaded by the instance
        self.manager = manager

    def log_msg(self, msg: str, color: int = None):
        final_msg = StringIO()

        if color:
            final_msg.write(str(color))

        final_msg.write('[{}] '.format(self.id_))

        final_msg.write(msg)

        if color:
            final_msg.write(Fore.RESET)

        final_msg.seek(0)

        print(final_msg.read())

    def run(self):
        while True:
            if self.apps:
                app = self.apps[0]
                app.status = ApplicationStatus.LOADING_DATA

                for _ in range(0, self.attempts):
                    try:
                        res = self.http_session.get('{}/apps/{}'.format(FLATHUB_API_URL, app.base_data.id), timeout=30)

                        if res.status_code == 200 and res.text:
                            data = res.json()

                            if not app.base_data.version:
                                app.base_data.version = data.get('version')

                            if not app.base_data.name:
                                app.base_data.name = data.get('name')

                            app.base_data.description = data.get('description', data.get('summary', None))
                            app.base_data.icon_url = data.get('iconMobileUrl', None)
                            app.base_data.latest_version = data.get('currentReleaseVersion', app.base_data.version)

                            if not app.base_data.version and app.base_data.latest_version:
                                app.base_data.version = app.base_data.latest_version

                            if app.base_data.icon_url and app.base_data.icon_url.startswith('/'):
                                app.base_data.icon_url = FLATHUB_URL + app.base_data.icon_url

                            loaded_data = app.get_data_to_cache()

                            self.api_cache.add(app.base_data.id, loaded_data)
                            app.status = ApplicationStatus.READY

                            if app.supports_disk_cache():
                                self.to_persist[app.base_data.id] = app

                            break
                        else:
                            self.log_msg("Could not retrieve app data for id '{}'. Server response: {}. Body: {}".format(app.base_data.id, res.status_code, res.content.decode()), Fore.RED)
                    except:
                        self.log_msg("Could not retrieve app data for id '{}'".format(app.base_data.id), Fore.YELLOW)
                        traceback.print_exc()

                if self.apps:
                    del self.apps[0]

            elif self.stop:
                self.cache_to_disk()
                break  # stop working

    def add(self, app: FlatpakApplication):
        self.apps.append(app)

    def current_load(self):
        return len(self.apps)

    def cache_to_disk(self):

        if self.to_persist:
            for app in self.to_persist.values():
                self.manager.cache_to_disk(app=app, icon_bytes=None, only_icon=False)

            self.to_persist = {}


class FlatpakAsyncDataLoaderManager:

    def __init__(self, manager: ApplicationManager, api_cache: Cache, worker_load: int = 1, workers: List[FlatpakAsyncDataLoader] = []):
        self.worker_load = worker_load
        self.current_workers = workers
        self.http_session = requests.Session()
        self.api_cache = api_cache
        self.manager = manager

    def load(self, app: FlatpakApplication):

            available_workers = [w for w in self.current_workers if w.current_load() < self.worker_load]

            if available_workers:
                worker = available_workers[0]
            else:  # new worker
                worker = FlatpakAsyncDataLoader(http_session=self.http_session,
                                                api_cache=self.api_cache,
                                                manager=self.manager)
                worker.start()
                self.current_workers.append(worker)

            worker.add(app)

    def stop_current_workers(self):

        for w in self.current_workers:
            w.stop = True

        self.current_workers = []
