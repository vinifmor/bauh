import argparse
import os
import sys

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication
from colorama import Fore

from fpakman import __version__, __app_name__
from fpakman.core import resource
from fpakman.core.disk import DiskCacheLoaderFactory
from fpakman.core.structure import prepare_folder_structure
from fpakman.util import util
from fpakman.core.controller import FlatpakManager, GenericApplicationManager
from fpakman.util.cache import Cache
from fpakman.util.memory import CacheCleaner
from fpakman.view.qt.systray import TrayIcon


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
parser.add_argument('-n', '--update-notification', action="store", default=os.getenv('FPAKMAN_UPDATE_NOTIFICATION', 1), type=int, help='Enables / disables system notifications for new updates. Default: %(default)s')
parser.add_argument('-dc', '--disk-cache', action="store", default=os.getenv('FPAKMAN_DISK_CACHE', 1), type=int, help='Enables / disables disk cache. When disk cache is enabled, the installed applications data are loaded faster. Default: %(default)s')
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

if args.update_notification == 0:
    log_msg('updates notifications are disabled', Fore.YELLOW)

locale_keys = util.get_locale_keys(args.locale)

prepare_folder_structure(disk_cache=args.disk_cache)

caches = []
flatpak_api_cache = Cache(expiration_time=args.cache_exp)
caches.append(flatpak_api_cache)

icon_cache = Cache(expiration_time=args.icon_exp)
caches.append(icon_cache)

app = QApplication(sys.argv)
app.setWindowIcon(QIcon(resource.get_path('img/logo.svg')))

disk_loader_factory = DiskCacheLoaderFactory(disk_cache=args.disk_cache, flatpak_api_cache=flatpak_api_cache)
manager = GenericApplicationManager([FlatpakManager(flatpak_api_cache, disk_cache=args.disk_cache)], disk_loader_factory=disk_loader_factory)


trayIcon = TrayIcon(locale_keys=locale_keys,
                    manager=manager,
                    check_interval=args.check_interval,
                    icon_cache=icon_cache,
                    disk_cache=args.disk_cache,
                    update_notification=bool(args.update_notification))
trayIcon.show()

CacheCleaner(caches).start()

sys.exit(app.exec_())
