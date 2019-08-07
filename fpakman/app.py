import sys

import requests
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication
from fpakman_api.util.cache import Cache
from fpakman_api.util.disk import DiskCacheLoaderFactory

from fpakman import __version__, __app_name__, app_args
from fpakman.core import resource, extensions
from fpakman.core.controller import GenericApplicationManager
from fpakman.util import util
from fpakman.util.memory import CacheCleaner
from fpakman.view.qt.systray import TrayIcon
from fpakman.view.qt.window import ManageWindow

args = app_args.read()

locale_keys = util.get_locale_keys(args.locale)
http_session = requests.Session()
caches, cache_map = [], {}

managers = extensions.load_managers(caches=caches,
                                    cache_map=cache_map,
                                    locale_keys=locale_keys,
                                    http_session=http_session,
                                    app_args=args)

icon_cache = Cache(expiration_time=args.icon_exp)
caches.append(icon_cache)

disk_loader_factory = DiskCacheLoaderFactory(disk_cache=args.disk_cache, cache_map=cache_map)

manager = GenericApplicationManager(managers, disk_loader_factory=disk_loader_factory, app_args=args)
manager.prepare()

app = QApplication(sys.argv)
app.setApplicationName(__app_name__)
app.setApplicationVersion(__version__)
app.setWindowIcon(QIcon(resource.get_path('img/logo.svg')))

manage_window = ManageWindow(locale_keys=locale_keys,
                             manager=manager,
                             icon_cache=icon_cache,
                             disk_cache=args.disk_cache,
                             download_icons=bool(args.download_icons),
                             screen_size=app.primaryScreen().size(),
                             suggestions=args.sugs)

if args.tray:
    trayIcon = TrayIcon(locale_keys=locale_keys,
                        manager=manager,
                        manage_window=manage_window,
                        check_interval=args.check_interval,
                        update_notification=bool(args.update_notification))
    manage_window.tray_icon = trayIcon
    trayIcon.show()
else:
    manage_window.refresh_apps()
    manage_window.show()

CacheCleaner(caches).start()
sys.exit(app.exec_())
