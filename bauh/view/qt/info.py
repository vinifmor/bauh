from PyQt5.QtCore import QSize
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QGroupBox, \
    QLineEdit, QLabel, QGridLayout, QPushButton, QPlainTextEdit, QToolBar
from bauh.api.abstract.cache import MemoryCache

IGNORED_ATTRS = {'name', '__app__'}


class InfoDialog(QDialog):

    def __init__(self, app: dict, icon_cache: MemoryCache, locale_keys: dict, screen_size: QSize()):
        super(InfoDialog, self).__init__()
        self.setWindowTitle(str(app['__app__']))
        self.screen_size = screen_size
        self.i18n = locale_keys
        layout = QVBoxLayout()
        self.setLayout(layout)
        self.full_vals = []

        self.toolbar_field = QToolBar()
        self.bt_back = QPushButton(locale_keys['back'].capitalize())
        self.bt_back.clicked.connect(self.back_to_info)
        self.toolbar_field.addWidget(self.bt_back)
        self.layout().addWidget(self.toolbar_field)
        self.toolbar_field.hide()

        # shows complete field string
        self.text_field = QPlainTextEdit()
        self.layout().addWidget(self.text_field)
        self.text_field.hide()

        self.gbox_info = QGroupBox()
        self.gbox_info.setMaximumHeight(self.screen_size.height() - self.screen_size.height() * 0.1)
        self.gbox_info_layout = QGridLayout()
        self.gbox_info.setLayout(self.gbox_info_layout)

        layout.addWidget(self.gbox_info)

        icon_data = icon_cache.get(app['__app__'].model.icon_url)

        if icon_data and icon_data.get('icon'):
            self.setWindowIcon(icon_data.get('icon'))
        else:
            self.setWindowIcon(QIcon(app['__app__'].model.get_type_icon_path()))

        for idx, attr in enumerate(sorted(app.keys())):
            if attr not in IGNORED_ATTRS and app[attr]:
                i18n_key = app['__app__'].model.get_type() + '.info.' + attr.lower()

                if isinstance(app[attr], list):
                    val = '\n'.join(['* ' + str(e.strip()) for e in app[attr] if e])
                else:
                    val = str(app[attr]).strip()

                i18n_val = locale_keys.get('{}.{}'.format(i18n_key, val.lower()))

                if i18n_val:
                    val = i18n_val

                text = QLineEdit()
                text.setToolTip(val)
                text.setText(val)
                text.setCursorPosition(0)
                text.setStyleSheet("width: 400px")
                text.setReadOnly(True)

                label = QLabel("{}: ".format(locale_keys.get(i18n_key, attr)).capitalize())
                label.setStyleSheet("font-weight: bold")

                self.gbox_info_layout.addWidget(label, idx, 0)
                self.gbox_info_layout.addWidget(text, idx, 1)
                self._gen_show_button(idx, val)

        self.adjustSize()

    def _gen_show_button(self, idx: int, val):

        def show_full_field():
            self.gbox_info.hide()
            self.toolbar_field.show()
            self.text_field.show()
            self.text_field.setPlainText(val)

        bt_full_field = QPushButton(self.i18n['show'].capitalize())
        bt_full_field.clicked.connect(show_full_field)
        self.gbox_info_layout.addWidget(bt_full_field, idx, 2)

    def back_to_info(self):
        self.text_field.setPlainText("")
        self.text_field.hide()
        self.toolbar_field.hide()
        self.gbox_info.show()
