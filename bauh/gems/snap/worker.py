import traceback
from threading import Thread

from bauh.api.abstract.cache import MemoryCache
from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.controller import SoftwareManager
from bauh.api.abstract.model import PackageStatus
from bauh.gems.snap import snap
from bauh.gems.snap.constants import SNAP_API_URL
from bauh.gems.snap.model import SnapApplication


class SnapAsyncDataLoader(Thread):

    def __init__(self, app: SnapApplication, manager: SoftwareManager, api_cache: MemoryCache,
                 context: ApplicationContext):
        super(SnapAsyncDataLoader, self).__init__(daemon=True)
        self.app = app
        self.id_ = '{}#{}'.format(self.__class__.__name__, id(self))
        self.manager = manager
        self.http_client = context.http_client
        self.api_cache = api_cache
        self.persist = False
        self.download_icons = context.download_icons
        self.logger = context.logger

    def run(self):
        if self.app:
            self.app.status = PackageStatus.LOADING_DATA

            try:
                res = self.http_client.session.get('{}/search?q={}'.format(SNAP_API_URL, self.app.name))

                if res:
                    try:
                        snap_list = res.json()['_embedded']['clickindex:package']
                    except:
                        self.logger.warning('Snap API response responded differently from expected for app: {}'.format(self.app.name))
                        return

                    if not snap_list:
                        self.logger.warning("Could not retrieve app data for id '{}'. Server response: {}. Body: {}".format(self.app.id, res.status_code, res.content.decode()))
                    else:
                        snap_data = snap_list[0]

                        api_data = {
                            'confinement': snap_data.get('confinement'),
                            'description': snap_data.get('description'),
                            'icon_url': snap_data.get('icon_url') if self.download_icons else None
                        }

                        self.api_cache.add(self.app.id, api_data)
                        self.app.confinement = api_data['confinement']
                        self.app.icon_url = api_data['icon_url']

                        if not api_data.get('description'):
                            api_data['description'] = snap.get_info(self.app.name, ('description',)).get('description')

                        self.app.description = api_data['description']
                        self.persist = self.app.supports_disk_cache()
                else:
                    self.logger.warning("Could not retrieve app data for id '{}'. Server response: {}. Body: {}".format(self.app.id, res.status_code, res.content.decode()))
            except:
                self.logger.error("Could not retrieve app data for id '{}'".format(self.app.id))
                traceback.print_exc()

            self.app.status = PackageStatus.READY

            if self.persist:
                self.manager.cache_to_disk(pkg=self.app, icon_bytes=None, only_icon=False)
