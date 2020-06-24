import faulthandler
import os
import sys
import traceback

import urllib3
from PyQt5.QtCore import QCoreApplication, Qt

from bauh import __app_name__, app_args
from bauh.view.core import config
from bauh.view.util import logs


def main(tray: bool = False):
    if not os.getenv('PYTHONUNBUFFERED'):
        os.environ['PYTHONUNBUFFERED'] = '1'

    faulthandler.enable()
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    args = app_args.read()

    logger = logs.new_logger(__app_name__, bool(args.logs))

    app_config = config.read_config(update_file=True)

    if bool(app_config['ui']['auto_scale']):
        os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1'
        logger.info("Auto screen scale factor activated")

    try:
        scale_factor = float(app_config['ui']['scale_factor'])
        os.environ['QT_SCALE_FACTOR'] = str(scale_factor)
        logger.info("Scale factor set to {}".format(scale_factor))
    except:
        traceback.print_exc()

    if bool(app_config['ui']['hdpi']):
        logger.info("HDPI settings activated")
        QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
        QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)

    if tray or bool(args.tray):
        from bauh.tray import new_tray_icon
        app, widget = new_tray_icon(app_config, logger)
    else:
        from bauh.manage import new_manage_panel
        app, widget = new_manage_panel(args, app_config, logger)

    widget.show()
    sys.exit(app.exec_())


def tray():
    main(tray=True)


if __name__ == '__main__':
    main()
