from PyQt5.QtWidgets import QComboBox, QApplication, QStyleFactory, QWidget

from bauh.core import config


class StylesComboBox(QComboBox):

    def __init__(self, parent: QWidget, i18n: dict):
        super(StylesComboBox, self).__init__(parent=parent)
        self.app = QApplication.instance()
        self.styles = []

        for idx, style in enumerate(QStyleFactory.keys()):
            self.styles.append(style)
            self.addItem('{}: {}'.format(i18n['style'].capitalize(), style), style)

            if style.lower() == self.app.style().objectName():
                self.setCurrentIndex(idx)

        self.currentIndexChanged.connect(self.change_style)

    def change_style(self, idx: int):
        style = self.styles[idx]
        self.app.setStyle(style)

        user_config = config.read()
        user_config.style = style
        config.save(user_config)
