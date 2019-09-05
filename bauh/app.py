import sys

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication
from bauh_api.abstract.controller import ApplicationContext
from bauh_api.util.http import HttpClient

from bauh import __version__, __app_name__, app_args, ROOT_DIR
from bauh.core import resource, extensions
from bauh.core.controller import GenericSoftwareManager
from bauh.util import util, logs
from bauh.util.cache import DefaultMemoryCacheFactory, CacheCleaner
from bauh.util.disk import DefaultDiskCacheLoaderFactory
from bauh.view.qt.systray import TrayIcon
from bauh.view.qt.window import ManageWindow

args = app_args.read()
logger = logs.new_logger(__app_name__, bool(args.logs))
app_args.validate(args, logger)

i18n = util.get_locale_keys(args.locale)

cache_cleaner = CacheCleaner()
cache_factory = DefaultMemoryCacheFactory(expiration_time=args.cache_exp, cleaner=cache_cleaner)
icon_cache = cache_factory.new(args.icon_exp)

context = ApplicationContext(i18n=i18n,
                             http_client=HttpClient(),
                             disk_cache=args.disk_cache,
                             download_icons=args.download_icons,
                             app_root_dir=ROOT_DIR,
                             cache_factory=cache_factory,
                             disk_loader_factory=DefaultDiskCacheLoaderFactory(disk_cache_enabled=args.disk_cache),
                             logger=logger)

managers = extensions.load_managers(context=context, locale=args.locale)


manager = GenericSoftwareManager(managers, context=context, app_args=args)
manager.prepare()

app = QApplication(sys.argv)
app.setApplicationName(__app_name__)
app.setApplicationVersion(__version__)
app.setWindowIcon(QIcon(resource.get_path('img/logo.svg')))

manage_window = ManageWindow(i18n=i18n,
                             manager=manager,
                             icon_cache=icon_cache,
                             disk_cache=args.disk_cache,
                             download_icons=bool(args.download_icons),
                             screen_size=app.primaryScreen().size(),
                             suggestions=args.sugs,
                             display_limit=args.max_displayed)

if args.tray:
    trayIcon = TrayIcon(locale_keys=i18n,
                        manager=manager,
                        manage_window=manage_window,
                        check_interval=args.check_interval,
                        update_notification=bool(args.update_notification))
    manage_window.tray_icon = trayIcon
    trayIcon.show()
else:
    manage_window.refresh_apps()
    manage_window.show()

cache_cleaner.start()
sys.exit(app.exec_())
