import argparse
import os
import sys
from pathlib import Path

import requests
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication
from colorama import Fore

from fpakman import __version__, __app_name__
from fpakman.core import resource
from fpakman.core.controller import GenericApplicationManager
from fpakman.core.disk import DiskCacheLoaderFactory
from fpakman.core.flatpak.constants import FLATPAK_CACHE_PATH
from fpakman.core.flatpak.controller import FlatpakManager
from fpakman.core.flatpak.model import FlatpakApplication
from fpakman.core.snap.constants import SNAP_CACHE_PATH
from fpakman.core.snap.controller import SnapManager
from fpakman.core.snap.model import SnapApplication
from fpakman.util import util
from fpakman.util.cache import Cache
from fpakman.util.memory import CacheCleaner
from fpakman.view.qt import dialog
from fpakman.view.qt.systray import TrayIcon
from fpakman.view.qt.window import ManageWindow


def log_msg(msg: str, color: int = None):

    if color is None:
        print('[{}] {}'.format(__app_name__, msg))
    else:
        print('{}[{}] {}{}'.format(color, __app_name__, msg, Fore.RESET))


parser = argparse.ArgumentParser(prog=__app_name__, description="GUI for Flatpak applications management")
parser.add_argument('-v', '--version', action='version', version='%(prog)s {}'.format(__version__))
parser.add_argument('-e', '--cache-exp', action="store", default=int(os.getenv('FPAKMAN_CACHE_EXPIRATION', 60 * 60)), type=int, help='cached API data expiration time in SECONDS. Default: %(default)s')
parser.add_argument('-ie', '--icon-exp', action="store", default=int(os.getenv('FPAKMAN_ICON_EXPIRATION', 60 * 5)), type=int, help='cached icons expiration time in SECONDS. Default: %(default)s')
parser.add_argument('-l', '--locale', action="store", default=os.getenv('FPAKMAN_LOCALE', 'en'), help='Translation key. Default: %(default)s')
parser.add_argument('-i', '--check-interval', action="store", default=int(os.getenv('FPAKMAN_CHECK_INTERVAL', 60)), type=int, help='Updates check interval in SECONDS. Default: %(default)s')
parser.add_argument('-n', '--update-notification', action="store", choices=[0, 1], default=os.getenv('FPAKMAN_UPDATE_NOTIFICATION', 1), type=int, help='Enables / disables system notifications for new updates. Default: %(default)s')
parser.add_argument('-dc', '--disk-cache', action="store", choices=[0, 1], default=os.getenv('FPAKMAN_DISK_CACHE', 1), type=int, help='Enables / disables disk cache. When disk cache is enabled, the installed applications data are loaded faster. Default: %(default)s')
parser.add_argument('-di', '--download-icons', action="store", choices=[0, 1], default=os.getenv('FPAKMAN_DOWNLOAD_ICONS', 1), type=int, help='Enables / disables app icons download. It may improve the application speed, depending of how applications data are retrieved by their extensions.')
parser.add_argument('--flatpak', action="store", default=os.getenv('FPAKMAN_FLATPAK', 1), choices=[0, 1], type=int, help='Enables / disables flatpak usage. Default: %(default)s')
parser.add_argument('--snap', action="store", default=os.getenv('FPAKMAN_SNAP', 1), choices=[0, 1], type=int, help='Enables / disables snap usage. Default: %(default)s')
parser.add_argument('-co', '--check-packaging-once', action="store", default=os.getenv('FPAKMAN_CHECK_PACKAGING_ONCE', 0), choices=[0, 1], type=int, help='If the available supported packaging types should be checked ONLY once. It improves the application speed if enabled, but can generate errors if you uninstall any packaging technology while using it, and every time a supported packaging type is installed it will only be available after a restart. Default: %(default)s')
parser.add_argument('--tray', action="store", default=os.getenv('FPAKMAN_TRAY', 1), choices=[0, 1], type=int, help='If the tray icon and update-check daemon should be created. Default: %(default)s')
parser.add_argument('--sugs', action="store", default=os.getenv('FPAKMAN_SUGGESTIONS', 1), choices=[0, 1], type=int, help='If app suggestions should be displayed if no app is installed (runtimes do not count as apps). Default: %(default)s')
args = parser.parse_args()

if args.cache_exp < 0:
    log_msg("'cache-exp' set to '{}': cache will not expire.".format(args.cache_exp), Fore.YELLOW)

if args.icon_exp < 0:
    log_msg("'icon-exp' set to '{}': cache will not expire.".format(args.cache_exp), Fore.YELLOW)

if not args.locale.strip():
    log_msg("'locale' set as '{}'. You must provide a valid one. Aborting...".format(args.locale), Fore.RED)
    exit(1)

if args.check_interval <= 0:
    log_msg("'check-interval' set as '{}'. It must be >= 0. Aborting...".format(args.check_interval), Fore.RED)
    exit(1)

if not args.flatpak:
    log_msg("'flatpak' is disabled.", Fore.YELLOW)

if not args.snap:
    log_msg("'snap' is disabled.", Fore.YELLOW)

if args.update_notification == 0:
    log_msg('updates notifications are disabled', Fore.YELLOW)

if args.download_icons == 0:
    log_msg("'download-icons' is disabled", Fore.YELLOW)

if args.check_packaging_once == 1:
    log_msg("'check-packaging-once' is enabled", Fore.YELLOW)

if args.sugs == 0:
    log_msg("suggestions are disabled", Fore.YELLOW)

locale_keys = util.get_locale_keys(args.locale)

http_session = requests.Session()
caches = []
cache_map = {}
managers = []

if args.flatpak:
    flatpak_api_cache = Cache(expiration_time=args.cache_exp)
    cache_map[FlatpakApplication] = flatpak_api_cache
    managers.append(FlatpakManager(app_args=args, api_cache=flatpak_api_cache, disk_cache=args.disk_cache, http_session=http_session, locale_keys=locale_keys))
    caches.append(flatpak_api_cache)

    if args.disk_cache:
        Path(FLATPAK_CACHE_PATH).mkdir(parents=True, exist_ok=True)

if args.snap:
    snap_api_cache = Cache(expiration_time=args.cache_exp)
    cache_map[SnapApplication] = snap_api_cache
    managers.append(SnapManager(app_args=args, disk_cache=args.disk_cache, api_cache=snap_api_cache, http_session=http_session, locale_keys=locale_keys))
    caches.append(snap_api_cache)

    if args.disk_cache:
        Path(SNAP_CACHE_PATH).mkdir(parents=True, exist_ok=True)

icon_cache = Cache(expiration_time=args.icon_exp)
caches.append(icon_cache)

disk_loader_factory = DiskCacheLoaderFactory(disk_cache=args.disk_cache, cache_map=cache_map)
manager = GenericApplicationManager(managers, disk_loader_factory=disk_loader_factory, app_args=args)
manager.prepare()

app = QApplication(sys.argv)
app.setApplicationName(__app_name__)
app.setApplicationVersion(__version__)
app.setWindowIcon(QIcon(resource.get_path('img/logo.svg')))

screen_size = app.primaryScreen().size()

manage_window = ManageWindow(locale_keys=locale_keys,
                             manager=manager,
                             icon_cache=icon_cache,
                             disk_cache=args.disk_cache,
                             download_icons=bool(args.download_icons),
                             screen_size=screen_size,
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

warnings = manager.list_warnings()

if warnings:
    for warning in warnings:
        dialog.show_warning(title=locale_keys['warning'].capitalize(), body=warning)

CacheCleaner(caches).start()
sys.exit(app.exec_())
