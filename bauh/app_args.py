import argparse
import logging
import os
from argparse import Namespace

from bauh import __app_name__, __version__


def read() -> Namespace:
    parser = argparse.ArgumentParser(prog=__app_name__, description="GUI for Linux package management")
    parser.add_argument('-v', '--version', action='version', version='%(prog)s {}'.format(__version__))
    parser.add_argument('-e', '--cache-exp', action="store",
                        default=int(os.getenv('BAUH_CACHE_EXPIRATION', 60 * 60)), type=int,
                        help='default memory caches expiration time in SECONDS. Default: %(default)s')
    parser.add_argument('-ie', '--icon-exp', action="store", default=int(os.getenv('BAUH_ICON_EXPIRATION', 60 * 5)),
                        type=int, help='cached icons expiration time in SECONDS. Default: %(default)s')
    parser.add_argument('-l', '--locale', action="store", default=os.getenv('BAUH_LOCALE'), help='Locale key. e.g: en, es, pt, ...')
    parser.add_argument('-i', '--check-interval', action="store", default=int(os.getenv('BAUH_CHECK_INTERVAL', 60)),
                        type=int, help='Updates check interval in SECONDS. Default: %(default)s')
    parser.add_argument('-n', '--system-notifications', action="store", choices=[0, 1],
                        default=os.getenv('BAUH_SYSTEM_NOTIFICATIONS', 1), type=int,
                        help='Enables / disables system notifications. Default: %(default)s')
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
    parser.add_argument('-md', '--max-displayed', action="store", default=os.getenv('BAUH_MAX_DISPLAYED', 50), type=int, help='Maximum number of displayed packages in the management panel table. Default: %(default)s')
    parser.add_argument('--logs', action="store", default=int(os.getenv('BAUH_LOGS', 0)), choices=[0, 1], type=int, help='If the application logs should be displayed. Default: %(default)s')
    parser.add_argument('--show-panel', action="store_true", help='Shows the management panel after the app icon is attached to the tray.')
    parser.add_argument('-dmt', '--download-mthread', action="store", default=os.getenv('BAUH_DOWNLOAD_MULTITHREAD', 1), choices=[0, 1], type=int, help='If installation files should be downloaded using multi-threads (only possible if aria2c is installed). Not all gems support this feature. Check README.md. Default: %(default)s')
    parser.add_argument('--clean', action="store_true", help='Removes all configuration and cache files')
    return parser.parse_args()
    
    
def validate(args: Namespace, logger: logging.Logger):

    if args.cache_exp < 0:
        logger.info("'cache-exp' set to '{}': cache will not expire.".format(args.cache_exp))

    if args.icon_exp < 0:
        logger.info("'icon-exp' set to '{}': cache will not expire.".format(args.cache_exp))

    if args.locale and not args.locale.strip():
        logger.info("'locale' set as '{}'. You must provide a valid one. Aborting...".format(args.locale))
        exit(1)

    if args.check_interval <= 0:
        logger.info("'check-interval' set as '{}'. It must be >= 0. Aborting...".format(args.check_interval))
        exit(1)

    if args.system_notifications == 0:
        logger.info('system notifications are disabled')

    if args.download_icons == 0:
        logger.info("'download-icons' is disabled")

    if args.check_packaging_once == 1:
        logger.info("'check-packaging-once' is enabled")

    if args.sugs == 0:
        logger.info("suggestions are disabled")

    if args.logs == 1:
        logger.info("Logs are enabled")

    if args.download_mthread == 1:
        logger.info("Multi-threaded downloads enabled")

    return args
