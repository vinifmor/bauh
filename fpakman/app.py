import argparse
import os
import sys

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication
from colorama import Fore

from fpakman import __version__
from fpakman.core import resource
from fpakman.core import util
from fpakman.core.controller import FlatpakManager
from fpakman.view.qt.systray import TrayIcon

app_name = 'fpakman'


def log_msg(msg: str, color: int = None):

    if color is None:
        print('[{}] {}'.format(app_name, msg))
    else:
        print('{}[{}] {}{}'.format(color, app_name, msg, Fore.RESET))


parser = argparse.ArgumentParser(prog=app_name, description="GUI for Flatpak applications management")
parser.add_argument('-v', '--version', action='version', version='%(prog)s {}'.format(__version__))
parser.add_argument('-e', '--cache-exp', action="store", default=int(os.getenv('FPAKMAN_CACHE_EXPIRATION', 60 * 60)), type=int, help='cached application expiration time in SECONDS. Default: %(default)s')
parser.add_argument('-l', '--locale', action="store", default=os.getenv('FPAKMAN_LOCALE', 'en'), help='Translation key. Default: %(default)s')
parser.add_argument('-i', '--check-interval', action="store", default=int(os.getenv('FPAKMAN_CHECK_INTERVAL', 60)), type=int, help='Updates check interval in SECONDS. Default: %(default)s')
parser.add_argument('-n', '--update-notification', action="store", default=os.getenv('FPAKMAN_UPDATE_NOTIFICATION', 1), type=int, help='Enable/disable system notifications for new updates. Default: %(default)s')
args = parser.parse_args()

if args.cache_exp <= 0:
    log_msg("'cache-exp' set to '{}': cache will not expire.".format(args.cache_exp), Fore.YELLOW)

if not args.locale.strip():
    log_msg("'locale' set as '{}'. You must provide a valid one. Aborting...".format(args.locale), Fore.RED)
    exit(1)

if args.check_interval <= 0:
    log_msg("'check-interval' set as '{}'. It must be >= 0. Aborting...".format(args.check_interval), Fore.RED)
    exit(1)

if args.update_notification == 0:
    log_msg('updates notifications are disabled', Fore.YELLOW)

locale_keys = util.get_locale_keys(args.locale)

app = QApplication(sys.argv)
app.setWindowIcon(QIcon(resource.get_path('img/logo.svg')))

manager = FlatpakManager(cache_expire=args.cache_exp)

trayIcon = TrayIcon(locale_keys=locale_keys,
                    manager=manager,
                    check_interval=args.check_interval,
                    update_notification=bool(args.update_notification))
trayIcon.load_database()
trayIcon.show()

sys.exit(app.exec_())
