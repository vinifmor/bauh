from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QGroupBox, \
    QLineEdit, QLabel

from bauh.util import util
from bauh.util.cache import Cache

IGNORED_ATTRS = {'name', '__app__'}


class InfoDialog(QDialog):

    def __init__(self, app: dict, icon_cache: Cache, locale_keys: dict, screen_size: QSize()):
        super(InfoDialog, self).__init__()
        self.setWindowTitle(app['name'])
        self.screen_size = screen_size
        layout = QVBoxLayout()
        self.setLayout(layout)

        gbox_info = QGroupBox()
        gbox_info.setMaximumHeight(self.screen_size.height() - self.screen_size.height() * 0.1)
        gbox_info_layout = QFormLayout()
        gbox_info.setLayout(gbox_info_layout)

        layout.addWidget(gbox_info)

        icon_data = icon_cache.get(app['__app__'].model.base_data.icon_url)

        if icon_data and icon_data.get('icon'):
            self.setWindowIcon(icon_data.get('icon'))

        for attr in sorted(app.keys()):
            if attr not in IGNORED_ATTRS and app[attr]:
                val = app[attr]
                text = QLineEdit()
                text.setToolTip(val)

                if attr == 'license' and val.strip() == 'unset':
                    val = locale_keys['license.unset']

                if attr == 'description':
                    val = util.strip_html(val)
                    val = val[0:40] + '...'

                text.setText(val)
                text.setCursorPosition(0)
                text.setStyleSheet("width: 400px")
                text.setReadOnly(True)

                label = QLabel("{}: ".format(locale_keys.get(app['__app__'].model.get_type() + '.info.' + attr, attr)).capitalize())
                label.setStyleSheet("font-weight: bold")

                gbox_info_layout.addRow(label, text)

        self.adjustSize()
