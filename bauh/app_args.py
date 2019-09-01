import argparse
import os
from argparse import Namespace

from colorama import Fore

from bauh import __app_name__, __version__


def log_msg(msg: str, color: int = None):

    if color is None:
        print('[{}] {}'.format(__app_name__, msg))
    else:
        print('{}[{}] {}{}'.format(color, __app_name__, msg, Fore.RESET))


def read() -> Namespace:
    parser = argparse.ArgumentParser(prog=__app_name__, description="GUI for Linux packages management")
    parser.add_argument('-v', '--version', action='version', version='%(prog)s {}'.format(__version__))
    parser.add_argument('-e', '--cache-exp', action="store",
                        default=int(os.getenv('BAUH_CACHE_EXPIRATION', 60 * 60)), type=int,
                        help='default memory caches expiration time in SECONDS. Default: %(default)s')
    parser.add_argument('-ie', '--icon-exp', action="store", default=int(os.getenv('BAUH_ICON_EXPIRATION', 60 * 5)),
                        type=int, help='cached icons expiration time in SECONDS. Default: %(default)s')
    parser.add_argument('-l', '--locale', action="store", default=os.getenv('BAUH_LOCALE', 'en'),
                        help='Translation key. Default: %(default)s')
    parser.add_argument('-i', '--check-interval', action="store", default=int(os.getenv('BAUH_CHECK_INTERVAL', 60)),
                        type=int, help='Updates check interval in SECONDS. Default: %(default)s')
    parser.add_argument('-n', '--update-notification', action="store", choices=[0, 1],
                        default=os.getenv('BAUH_UPDATE_NOTIFICATION', 1), type=int,
                        help='Enables / disables system notifications for new updates. Default: %(default)s')
    parser.add_argument('-dc', '--disk-cache', action="store", choices=[0, 1],
                        default=os.getenv('BAUH_DISK_CACHE', 1), type=int,
                        help='Enables / disables disk cache. When disk cache is enabled, the installed applications data are loaded faster. Default: %(default)s')
    parser.add_argument('-di', '--download-icons', action="store", choices=[0, 1],
                        default=os.getenv('BAUH_DOWNLOAD_ICONS', 1), type=int,
                        help='Enables / disables package icons download. It may improve the application speed, depending of how applications data are retrieved by their extensions.')
    parser.add_argument('-co', '--check-packaging-once', action="store",
                        default=os.getenv('BAUH_CHECK_PACKAGING_ONCE', 0), choices=[0, 1], type=int,
                        help='If the available supported packaging types should be checked ONLY once. It improves the application speed if enabled, but can generate errors if you uninstall any packaging technology while using it, and every time a supported packaging type is installed it will only be available after a restart. Default: %(default)s')
    parser.add_argument('--tray', action="store", default=os.getenv('BAUH_TRAY', 0), choices=[0, 1], type=int,
                        help='If the tray icon and update-check daemon should be created. Default: %(default)s')
    parser.add_argument('--sugs', action="store", default=os.getenv('BAUH_SUGGESTIONS', 1), choices=[0, 1], type=int, help='If app suggestions should be displayed if no application package is installed (runtimes / libraries do not count as apps). Default: %(default)s')
    parser.add_argument('-md', '--max-displayed', action="store", default=os.getenv('BAUH_MAX_DISPLAYED', 100), choices=[0, 1], type=int, help='Maximum number of displayed packages in the management panel table. Default: %(default)s')
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

    if args.download_icons == 0:
        log_msg("'download-icons' is disabled", Fore.YELLOW)

    if args.check_packaging_once == 1:
        log_msg("'check-packaging-once' is enabled", Fore.YELLOW)

    if args.sugs == 0:
        log_msg("suggestions are disabled", Fore.YELLOW)

    return args
