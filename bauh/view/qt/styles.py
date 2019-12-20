from PyQt5.QtWidgets import QComboBox, QStyleFactory, QWidget, QApplication

from bauh import __app_name__
from bauh.commons.html import bold
from bauh.view.core import config
from bauh.view.util import util
from bauh.view.qt import dialog
from bauh.view.util.translation import I18n


class StylesComboBox(QComboBox):

    def __init__(self, parent: QWidget, i18n: I18n, show_panel_after_restart: bool):
        super(StylesComboBox, self).__init__(parent=parent)
        self.app = QApplication.instance()
        self.styles = []
        self.i18n = i18n
        self.last_index = 0
        self.show_panel_after_restart = show_panel_after_restart

        for idx, style in enumerate(QStyleFactory.keys()):
            self.styles.append(style)
            self.addItem('{}: {}'.format(i18n['style'].capitalize(), style), style)

            if style.lower() == self.app.style().objectName():
                self.setCurrentIndex(idx)
                self.last_index = idx

        self.currentIndexChanged.connect(self.change_style)

    def change_style(self, idx: int):

        if dialog.ask_confirmation(self.i18n['style.change.title'], self.i18n['style.change.question'].format(bold(__app_name__)), self.i18n):
            self.last_index = idx
            style = self.styles[idx]

            user_config = config.read_config()
            user_config['ui']['style'] = style
            config.save(user_config)

            util.restart_app(self.show_panel_after_restart)
        else:
            self.blockSignals(True)
            self.setCurrentIndex(self.last_index)
            self.blockSignals(False)
