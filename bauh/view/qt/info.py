from PyQt5.QtCore import QSize
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QGroupBox, \
    QLineEdit, QLabel, QGridLayout, QPushButton, QPlainTextEdit, QToolBar

from bauh.api.abstract.cache import MemoryCache
from bauh.view.util.translation import I18n

IGNORED_ATTRS = {'name', '__app__'}


class InfoDialog(QDialog):

    def __init__(self, app: dict, icon_cache: MemoryCache, i18n: I18n, screen_size: QSize()):
        super(InfoDialog, self).__init__()
        self.setWindowTitle(str(app['__app__']))
        self.screen_size = screen_size
        self.i18n = i18n
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.toolbar_field = QToolBar()
        self.bt_back = QPushButton(i18n['back'].capitalize())
        self.bt_back.clicked.connect(self.back_to_info)
        self.toolbar_field.addWidget(self.bt_back)
        self.layout().addWidget(self.toolbar_field)
        self.toolbar_field.hide()

        # shows complete field string
        self.text_field = QPlainTextEdit()
        self.text_field.setReadOnly(True)
        self.layout().addWidget(self.text_field)
        self.text_field.hide()

        self.gbox_info = QGroupBox()
        self.gbox_info.setMaximumHeight(self.screen_size.height() - self.screen_size.height() * 0.1)
        self.gbox_info_layout = QGridLayout()
        self.gbox_info.setLayout(self.gbox_info_layout)

        layout.addWidget(self.gbox_info)

        # THERE ARE CRASHES WITH SOME RARE ICONS ( like insomnia ). IT CAN BE A QT BUG. IN THE MEANTIME, ONLY THE TYPE ICON WILL BE RENDERED
        #
        # icon_data = icon_cache.get(app['__app__'].model.icon_url)
        #
        # if icon_data and icon_data.get('icon'):
        #     self.setWindowIcon(icon_data.get('icon'))
        self.setWindowIcon(QIcon(app['__app__'].model.get_type_icon_path()))

        for idx, attr in enumerate(sorted(app.keys())):
            if attr not in IGNORED_ATTRS and app[attr]:
                i18n_key = app['__app__'].model.get_type().lower() + '.info.' + attr.lower()

                if isinstance(app[attr], list):
                    val = ' '.join([str(e).strip() for e in app[attr] if e])
                    show_val = '\n'.join(['* ' + str(e).strip() for e in app[attr] if e])
                else:
                    val = str(app[attr]).strip()
                    show_val = val

                i18n_val = i18n.get('{}.{}'.format(i18n_key, val.lower()))

                if i18n_val:
                    val = i18n_val
                    show_val = val

                text = QLineEdit()
                text.setToolTip(show_val)
                text.setText(val)
                text.setCursorPosition(0)
                text.setStyleSheet("width: 400px")
                text.setReadOnly(True)

                label = QLabel(i18n.get(i18n_key, i18n.get(attr.lower(), attr)).capitalize())
                label.setStyleSheet("font-weight: bold")

                self.gbox_info_layout.addWidget(label, idx, 0)
                self.gbox_info_layout.addWidget(text, idx, 1)
                self._gen_show_button(idx, show_val)

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
