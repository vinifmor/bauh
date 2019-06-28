from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QGroupBox, \
    QLineEdit, QLabel, QPlainTextEdit


class InfoDialog(QDialog):

    def __init__(self, app: dict, app_icon: QIcon, locale_keys: dict):
        super(InfoDialog, self).__init__()
        self.setWindowTitle(app['name'])
        self.setWindowIcon(app_icon)
        layout = QVBoxLayout()
        self.setLayout(layout)

        gbox_info_layout = QFormLayout()
        gbox_info = QGroupBox()
        gbox_info.setLayout(gbox_info_layout)
        layout.addWidget(gbox_info)

        for attr in sorted(app.keys()):

            if attr != 'name' and app[attr]:
                if attr == 'description':
                    text = QPlainTextEdit()
                    text.appendHtml(app[attr])
                else:
                    text = QLineEdit()
                    text.setText(app[attr])
                    text.setCursorPosition(0)
                    text.setStyleSheet("width: 400px")

                text.setReadOnly(True)

                label = QLabel("{}: ".format(locale_keys.get('flatpak.info.' + attr, attr)).capitalize())
                label.setStyleSheet("font-weight: bold")

                gbox_info_layout.addRow(label, text)

        self.adjustSize()
