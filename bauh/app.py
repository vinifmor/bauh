import faulthandler
import locale
import os
import sys
import traceback

import urllib3
from PyQt6.QtCore import QCoreApplication, Qt

from bauh import __app_name__, app_args
from bauh.view.core.config import CoreConfigManager
from bauh.view.util import logs


def main(tray: bool = False):
    if not os.getenv('PYTHONUNBUFFERED'):
        os.environ['PYTHONUNBUFFERED'] = '1'

    if not os.getenv('XDG_RUNTIME_DIR'):
        os.environ['XDG_RUNTIME_DIR'] = f'/run/user/{os.getuid()}'

    faulthandler.enable()
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    args = app_args.read()

    logger = logs.new_logger(__app_name__, bool(args.logs))

    try:
        locale.setlocale(locale.LC_NUMERIC, '')
    except Exception:
        logger.error("Could not set locale 'LC_NUMBERIC' to '' to display localized numbers")
        traceback.print_exc()

    if args.offline:
        logger.warning("offline mode activated")

    app_config = CoreConfigManager().get_config()

    if bool(app_config['ui']['auto_scale']):
        os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1'
        logger.info("Auto screen scale factor activated")

    try:
        scale_factor = float(app_config['ui']['scale_factor'])
        os.environ['QT_SCALE_FACTOR'] = str(scale_factor)
        logger.info("Scale factor set to {}".format(scale_factor))
    except Exception:
        traceback.print_exc()

    if bool(args.suggestions):
        logger.info("Forcing loading software suggestions after the initialization process")

    if tray or bool(args.tray):
        from bauh.tray import new_tray_icon
        app, widget = new_tray_icon(app_config, logger)
    else:
        from bauh.manage import new_manage_panel
        app, widget = new_manage_panel(args, app_config, logger)

    widget.show()
    sys.exit(app.exec())


def tray():
    main(tray=True)


if __name__ == '__main__':
    main()
