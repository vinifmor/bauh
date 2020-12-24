import logging
from argparse import Namespace
from typing import Tuple

from PyQt5.QtWidgets import QApplication, QWidget

from bauh import ROOT_DIR, __app_name__
from bauh.api.abstract.context import ApplicationContext
from bauh.api.http import HttpClient
from bauh.commons.internet import InternetChecker
from bauh.context import generate_i18n, DEFAULT_I18N_KEY, new_qt_application
from bauh.view.core import gems
from bauh.view.core.controller import GenericSoftwareManager
from bauh.view.core.downloader import AdaptableFileDownloader
from bauh.view.qt.prepare import PreparePanel
from bauh.view.qt.settings import SettingsWindow
from bauh.view.qt.window import ManageWindow
from bauh.view.util import resource, util
from bauh.view.util.cache import CacheCleaner, DefaultMemoryCacheFactory
from bauh.view.util.disk import DefaultDiskCacheLoaderFactory


def new_manage_panel(app_args: Namespace, app_config: dict, logger: logging.Logger) -> Tuple[QApplication, QWidget]:
    i18n = generate_i18n(app_config, resource.get_path('locale'))

    cache_cleaner = CacheCleaner()

    cache_factory = DefaultMemoryCacheFactory(expiration_time=int(app_config['memory_cache']['data_expiration']), cleaner=cache_cleaner)
    icon_cache = cache_factory.new(int(app_config['memory_cache']['icon_expiration']))

    http_client = HttpClient(logger)

    context = ApplicationContext(i18n=i18n,
                                 http_client=http_client,
                                 download_icons=bool(app_config['download']['icons']),
                                 app_root_dir=ROOT_DIR,
                                 cache_factory=cache_factory,
                                 disk_loader_factory=DefaultDiskCacheLoaderFactory(logger),
                                 logger=logger,
                                 distro=util.get_distro(),
                                 file_downloader=AdaptableFileDownloader(logger, bool(app_config['download']['multithreaded']),
                                                                         i18n, http_client, app_config['download']['multithreaded_client']),
                                 app_name=__app_name__,
                                 internet_checker=InternetChecker(offline=app_args.offline))

    managers = gems.load_managers(context=context, locale=i18n.current_key, config=app_config, default_locale=DEFAULT_I18N_KEY)

    if app_args.reset:
        util.clean_app_files(managers)
        exit(0)

    manager = GenericSoftwareManager(managers, context=context, config=app_config)

    app = new_qt_application(app_config=app_config, logger=logger, quit_on_last_closed=True)

    if app_args.settings:  # only settings window
        manager.cache_available_managers()
        return app, SettingsWindow(manager=manager, i18n=i18n, screen_size=app.primaryScreen().size(), window=None)
    else:
        manage_window = ManageWindow(i18n=i18n,
                                     manager=manager,
                                     icon_cache=icon_cache,
                                     screen_size=app.primaryScreen().size(),
                                     config=app_config,
                                     context=context,
                                     http_client=http_client,
                                     icon=util.get_default_icon()[1],
                                     logger=logger)

        prepare = PreparePanel(screen_size=app.primaryScreen().size(),
                               context=context,
                               manager=manager,
                               i18n=i18n,
                               manage_window=manage_window,
                               app_config=app_config)
        cache_cleaner.start()

        return app, prepare
