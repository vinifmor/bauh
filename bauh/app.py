import os
import sys
from threading import Thread

import urllib3
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

from bauh import __version__, __app_name__, app_args, ROOT_DIR
from bauh.api.abstract.controller import ApplicationContext
from bauh.api.http import HttpClient
from bauh.view.core import gems, config
from bauh.view.core.controller import GenericSoftwareManager
from bauh.view.core.downloader import AdaptableFileDownloader
from bauh.view.qt.systray import TrayIcon
from bauh.view.qt.window import ManageWindow
from bauh.view.util import util, logs, resource, translation
from bauh.view.util.cache import DefaultMemoryCacheFactory, CacheCleaner
from bauh.view.util.disk import DefaultDiskCacheLoaderFactory
from bauh.view.util.translation import I18n

DEFAULT_I18N_KEY = 'en'


def main():
    if not os.getenv('PYTHONUNBUFFERED'):
        os.environ['PYTHONUNBUFFERED'] = '1'

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    args = app_args.read()

    logger = logs.new_logger(__app_name__, bool(args.logs))
    app_args.validate(args, logger)

    local_config = config.read_config(update_file=True)
    config.validate(local_config, logger)

    i18n_key, current_i18n = translation.get_locale_keys(local_config.locale)
    default_i18n = translation.get_locale_keys(DEFAULT_I18N_KEY)[1] if i18n_key != DEFAULT_I18N_KEY else {}
    i18n = I18n(i18n_key, current_i18n, DEFAULT_I18N_KEY, default_i18n)

    cache_cleaner = CacheCleaner()
    cache_factory = DefaultMemoryCacheFactory(expiration_time=local_config.cache_exp, cleaner=cache_cleaner)
    icon_cache = cache_factory.new(local_config.icon_exp)

    http_client = HttpClient(logger)

    context = ApplicationContext(i18n=i18n,
                                 http_client=http_client,
                                 disk_cache=local_config.disk_cache,
                                 download_icons=local_config.download_icons,
                                 app_root_dir=ROOT_DIR,
                                 cache_factory=cache_factory,
                                 disk_loader_factory=DefaultDiskCacheLoaderFactory(disk_cache_enabled=local_config.disk_cache, logger=logger),
                                 logger=logger,
                                 distro=util.get_distro(),
                                 file_downloader=AdaptableFileDownloader(logger, local_config.download_mthread,
                                                                         i18n, http_client))

    managers = gems.load_managers(context=context, locale=i18n_key, config=local_config, default_locale=DEFAULT_I18N_KEY)

    if args.reset:
        util.clean_app_files(managers)
        exit(0)

    manager = GenericSoftwareManager(managers, context=context, config=local_config)
    manager.prepare()

    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(resource.get_path('img/logo.svg')))

    if local_config.style:
        app.setStyle(local_config.style)
    else:
        if app.style().objectName().lower() not in {'fusion', 'breeze'}:
            app.setStyle('Fusion')

    manage_window = ManageWindow(i18n=i18n,
                                 manager=manager,
                                 icon_cache=icon_cache,
                                 screen_size=app.primaryScreen().size(),
                                 config=local_config,
                                 context=context,
                                 http_client=http_client,
                                 logger=logger)

    if args.tray:
        tray_icon = TrayIcon(i18n=i18n,
                             manager=manager,
                             manage_window=manage_window,
                             check_interval=local_config.update_check_interval,
                             update_notification=local_config.system_notifications)
        manage_window.set_tray_icon(tray_icon)
        tray_icon.show()

        if args.show_panel:
            tray_icon.show_manage_window()
    else:
        manage_window.refresh_apps()
        manage_window.show()

    cache_cleaner.start()
    Thread(target=config.remove_old_config, args=(logger,), daemon=True).start()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
