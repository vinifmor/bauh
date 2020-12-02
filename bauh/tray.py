from logging import Logger
from typing import Tuple

from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QApplication

from bauh.context import new_qt_application
from bauh.view.qt.systray import TrayIcon


def new_tray_icon(app_config: dict, logger: Logger) -> Tuple[QApplication, QObject]:
    app = new_qt_application(app_config=app_config, logger=logger, quit_on_last_closed=True)
    tray_icon = TrayIcon(screen_size=app.primaryScreen().size(), config=app_config, logger=logger)
    tray_icon.show()

    return app, tray_icon
