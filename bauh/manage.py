import logging
from argparse import Namespace
from typing import Tuple

from PyQt5.QtWidgets import QApplication, QWidget

from bauh import ROOT_DIR, __app_name__, __version__
from bauh.api import user
from bauh.api.abstract.context import ApplicationContext
from bauh.api.http import HttpClient
from bauh.commons.internet import InternetChecker
from bauh.context import generate_i18n, DEFAULT_I18N_KEY, new_qt_application
from bauh.view.core import gems
from bauh.view.core.controller import GenericSoftwareManager
from bauh.view.core.downloader import AdaptableFileDownloader
from bauh.view.core.suggestions import read_suggestions_mapping
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

    downloader = AdaptableFileDownloader(logger=logger, multithread_enabled=app_config['download']['multithreaded'],
                                         multithread_client=app_config['download']['multithreaded_client'],
                                         i18n=i18n, http_client=http_client,
                                         check_ssl=app_config['download']['check_ssl'])

    context = ApplicationContext(i18n=i18n,
                                 http_client=http_client,
                                 download_icons=bool(app_config['download']['icons']),
                                 app_root_dir=ROOT_DIR,
                                 cache_factory=cache_factory,
                                 disk_loader_factory=DefaultDiskCacheLoaderFactory(logger),
                                 logger=logger,
                                 distro=util.get_distro(),
                                 file_downloader=downloader,
                                 app_name=__app_name__,
                                 app_version=__version__,
                                 internet_checker=InternetChecker(offline=app_args.offline),
                                 suggestions_mapping=read_suggestions_mapping(),
                                 root_user=user.is_root())

    managers = gems.load_managers(context=context, locale=i18n.current_key, config=app_config,
                                  default_locale=DEFAULT_I18N_KEY, logger=logger)

    if app_args.reset:
        util.clean_app_files(managers)
        exit(0)

    force_suggestions = bool(app_args.suggestions)
    manager = GenericSoftwareManager(managers, context=context, config=app_config, force_suggestions=force_suggestions)

    app = new_qt_application(app_config=app_config, logger=logger, quit_on_last_closed=True)

    screen_size = app.primaryScreen().size()
    context.screen_width, context.screen_height = screen_size.width(), screen_size.height()
    logger.info(f"Screen: {screen_size.width()} x {screen_size.height()} "
                f"(DPI: {int(app.primaryScreen().logicalDotsPerInch())})")

    if app_args.settings:  # only settings window
        manager.cache_available_managers()
        return app, SettingsWindow(manager=manager, i18n=i18n, window=None)
    else:
        manage_window = ManageWindow(i18n=i18n,
                                     manager=manager,
                                     icon_cache=icon_cache,
                                     config=app_config,
                                     context=context,
                                     http_client=http_client,
                                     icon=util.get_default_icon()[1],
                                     force_suggestions=force_suggestions,
                                     logger=logger)

        prepare = PreparePanel(context=context,
                               manager=manager,
                               i18n=i18n,
                               manage_window=manage_window,
                               app_config=app_config,
                               force_suggestions=force_suggestions)
        cache_cleaner.start()

        return app, prepare
