import os
from threading import Thread
from typing import List, Type, Set

from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.controller import SoftwareManager, SearchResult
from bauh.api.abstract.disk import DiskCacheLoader
from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.model import SoftwarePackage, PackageAction, PackageSuggestion, PackageUpdate, PackageHistory
from bauh.gems.web import npm
from bauh.gems.web.environment import NodeUpdater
from bauh.gems.web.model import WebApplication

try:
    from bs4 import BeautifulSoup, SoupStrainer
    BS4_AVAILABLE = True
except:
    BS4_AVAILABLE = False


try:
    import lxml
    LXML_AVAILABLE = True
except:
    LXML_AVAILABLE = False


class WebApplicationManager(SoftwareManager):

    def __init__(self, context: ApplicationContext):
        super(WebApplicationManager, self).__init__(context=context)
        self.http_client = context.http_client
        self.node_updater = NodeUpdater(logger=context.logger, file_downloader=context.file_downloader, i18n=context.i18n)
        self.enabled = True

    def search(self, words: str, disk_loader: DiskCacheLoader, limit: int = -1, is_url: bool = False) -> SearchResult:
        res = SearchResult([], [], 0)

        if is_url:
            url_res = self.http_client.get(words)

            if url_res:
                soup = BeautifulSoup(url_res.text, 'lxml', parse_only=SoupStrainer('head'))

                name_tag = soup.head.find('meta', attrs={'name': 'application-name'})
                name = name_tag.get('content') if name_tag else words.split('.')[0]

                desc_tag = soup.head.find('meta', attrs={'name': 'description'})
                desc = desc_tag.get('content') if desc_tag else words

                icon_tag = soup.head.find('link', attrs={"rel": "icon"})
                icon_url = icon_tag.get('href') if icon_tag else None

                res.new = [WebApplication(url=words, name=name, description=desc, icon_url=icon_url)]
                res.total = 1
        else:
            # TODO
            pass

        return res

    def read_installed(self, disk_loader: DiskCacheLoader, limit: int = -1, only_apps: bool = False, pkg_types: Set[Type[SoftwarePackage]] = None, internet_available: bool = True) -> SearchResult:
        # TODO
        return SearchResult([], [], 0)

    def downgrade(self, pkg: SoftwarePackage, root_password: str, handler: ProcessWatcher) -> bool:
        pass

    def update(self, pkg: SoftwarePackage, root_password: str, watcher: ProcessWatcher) -> bool:
        pass

    def uninstall(self, pkg: SoftwarePackage, root_password: str, watcher: ProcessWatcher) -> bool:
        pass

    def get_managed_types(self) -> Set[Type[SoftwarePackage]]:
        return {WebApplication}

    def get_info(self, pkg: SoftwarePackage) -> dict:
        pass

    def get_history(self, pkg: SoftwarePackage) -> PackageHistory:
        pass

    def install(self, pkg: SoftwarePackage, root_password: str, watcher: ProcessWatcher) -> bool:
        pass

    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

    def can_work(self) -> bool:
        return BS4_AVAILABLE and LXML_AVAILABLE

    def requires_root(self, action: str, pkg: SoftwarePackage):
        return False

    def prepare(self):
        if bool(int(os.getenv('BAUH_WEB_UPDATE_NODE', 1))):
            Thread(daemon=True, target=self.node_updater.update_node).start()

    def list_updates(self, internet_available: bool) -> List[PackageUpdate]:
        pass

    def list_warnings(self, internet_available: bool) -> List[str]:
        pass

    def list_suggestions(self, limit: int) -> List[PackageSuggestion]:
        pass

    def execute_custom_action(self, action: PackageAction, pkg: SoftwarePackage, root_password: str, watcher: ProcessWatcher) -> bool:
        pass

    def is_default_enabled(self) -> bool:
        return True

    def launch(self, pkg: SoftwarePackage):
        pass

    def get_screenshots(self, pkg: SoftwarePackage) -> List[str]:
        pass
