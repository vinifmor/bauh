import os
import sys
from logging import Logger
from typing import Tuple

from PyQt5.QtCore import QCoreApplication
from PyQt5.QtWidgets import QApplication

from bauh import __app_name__, __version__
from bauh.stylesheet import process_theme, read_default_themes, read_user_themes, read_theme_metada
from bauh.view.util import util, translation
from bauh.view.util.translation import I18n

DEFAULT_I18N_KEY = 'en'
PROPERTY_HARDCODED_STYLESHEET = 'hcqss'


def new_qt_application(app_config: dict, logger: Logger, quit_on_last_closed: bool = False, name: str = None) -> QApplication:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(quit_on_last_closed)  # otherwise windows opened through the tray icon kill the application when closed
    app.setApplicationName(name if name else __app_name__)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(util.get_default_icon()[1])

    if app_config['ui']['qt_style']:
        app.setStyle(str(app_config['ui']['qt_style']))
    else:
        app.setStyle('fusion')

    app.setProperty('qt_style', app.style().objectName().lower())

    theme_key = app_config['ui']['theme'].strip() if app_config['ui']['theme'] else None
    set_theme(theme_key=theme_key, app=app, logger=logger)

    if not app_config['ui']['system_theme']:
        app.setPalette(app.style().standardPalette())

    return app


def _gen_i18n_data(app_config: dict, locale_dir: str) -> Tuple[str, dict, str, dict]:
    i18n_key, current_i18n = translation.get_locale_keys(app_config['locale'], locale_dir=locale_dir)
    default_i18n = translation.get_locale_keys(DEFAULT_I18N_KEY, locale_dir=locale_dir)[1] if i18n_key != DEFAULT_I18N_KEY else {}
    return i18n_key, current_i18n, DEFAULT_I18N_KEY, default_i18n


def generate_i18n(app_config: dict, locale_dir: str) -> I18n:
    return I18n(*_gen_i18n_data(app_config, locale_dir))


def update_i18n(app_config, locale_dir: str, i18n: I18n) -> I18n:
    cur_key, cur_dict, def_key, def_dict = _gen_i18n_data(app_config, locale_dir)

    if i18n.current_key == cur_key:
        i18n.current.update(cur_dict)

    i18n.default.update(def_dict)
    return i18n


def set_theme(theme_key: str, app: QCoreApplication, logger: Logger):
    if not theme_key:
        logger.warning("config: no theme defined")
    else:
        available_themes = {}
        default_themes = read_default_themes()
        available_themes.update(default_themes)

        theme_file = None

        if '/' in theme_key:
            if os.path.isfile(theme_key):
                user_sheets = read_user_themes()

                if user_sheets:
                    available_themes.update(user_sheets)

                    if theme_key in user_sheets:
                        theme_file = theme_key
        else:
            theme_file = default_themes.get(theme_key)

        if theme_file:
            with open(theme_file) as f:
                theme_str = f.read()

            if not theme_str:
                logger.warning("theme file '{}' has no content".format(theme_file))
            else:
                base_metadata = read_theme_metada(key=theme_key, file_path=theme_file)

                if base_metadata.abstract:
                    logger.warning("theme file '{}' is abstract (abstract = true) and cannot be loaded".format(theme_file))
                else:
                    processed = process_theme(file_path=theme_file,
                                              metadata=base_metadata,
                                              theme_str=theme_str,
                                              available_themes=available_themes)

                    if processed:
                        app.setStyleSheet(processed[0])
                        logger.info("theme file '{}' loaded".format(theme_file))
                    else:
                        logger.warning("theme file '{}' could not be interpreted and processed".format(theme_file))
