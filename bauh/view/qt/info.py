import shutil
import subprocess
from collections.abc import Iterable
from subprocess import Popen
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QCursor
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QGroupBox, \
    QLineEdit, QLabel, QGridLayout, QPushButton, QPlainTextEdit, QScrollArea, QFrame, QWidget, QSizePolicy, \
    QHBoxLayout

from bauh.api.abstract.cache import MemoryCache
from bauh.commons.regex import RE_URL
from bauh.view.qt.components import new_spacer
from bauh.view.qt.qt_utils import get_current_screen_geometry
from bauh.view.util.translation import I18n

IGNORED_ATTRS = {'name', '__app__'}


class InfoDialog(QDialog):

    def __init__(self, pkg_info: dict, icon_cache: MemoryCache, i18n: I18n, can_open_url: bool):
        super(InfoDialog, self).__init__()
        self.setWindowTitle(str(pkg_info['__app__']))
        self.i18n = i18n
        self._can_open_url = can_open_url
        layout = QVBoxLayout()
        self.setLayout(layout)

        scroll = QScrollArea(self)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        comps_container = QWidget()
        comps_container.setObjectName('root_container')
        comps_container.setLayout(QVBoxLayout())
        scroll.setWidget(comps_container)

        # shows complete field string
        self.text_field = QPlainTextEdit()
        self.text_field.setObjectName('full_field')
        self.text_field.setReadOnly(True)
        comps_container.layout().addWidget(self.text_field)
        self.text_field.hide()

        self.gbox_info = QGroupBox()
        self.gbox_info.setObjectName('fields')
        self.gbox_info.setLayout(QGridLayout())

        comps_container.layout().addWidget(self.gbox_info)

        # THERE ARE CRASHES WITH SOME RARE ICONS ( like insomnia ). IT CAN BE A QT BUG. IN THE MEANTIME, ONLY THE TYPE ICON WILL BE RENDERED
        #
        # icon_data = icon_cache.get(app['__app__'].model.icon_url)
        #
        # if icon_data and icon_data.get('icon'):
        #     self.setWindowIcon(icon_data.get('icon'))
        self.setWindowIcon(QIcon(pkg_info['__app__'].model.get_type_icon_path()))

        for idx, attr in enumerate(sorted(pkg_info.keys())):
            if attr not in IGNORED_ATTRS and pkg_info[attr] is not None:
                i18n_key = pkg_info['__app__'].model.gem_name + '.info.' + attr.lower()
                val = pkg_info[attr]

                if not isinstance(val, str) and isinstance(pkg_info[attr], Iterable):
                    val = ' '.join([str(e).strip() for e in pkg_info[attr] if e])
                    show_val = '\n'.join(['* ' + str(e).strip() for e in pkg_info[attr] if e])
                else:
                    val = str(pkg_info[attr]).strip()
                    show_val = val

                i18n_val = i18n.get(f"{i18n_key}.{val.lower()}")

                if i18n_val:
                    val = i18n_val
                    show_val = val

                text = QLineEdit()
                text.setObjectName('field_value')
                text.setToolTip(show_val)
                text.setText(val)
                text.setCursorPosition(0)
                text.setReadOnly(True)

                label = QLabel(i18n.get(i18n_key, i18n.get(attr.lower(), attr)).capitalize())
                label.setObjectName('field_name')

                self.gbox_info.layout().addWidget(label, idx, 0)
                self.gbox_info.layout().addWidget(text, idx, 1)

                self._gen_show_button(idx=idx, val=show_val)

        layout.addWidget(scroll)

        lower_container = QWidget()
        lower_container.setObjectName('lower_container')
        lower_container.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        lower_container.setLayout(QHBoxLayout())

        self.bt_back = QPushButton('< {}'.format(self.i18n['back'].capitalize()))
        self.bt_back.setObjectName('back')
        self.bt_back.setVisible(False)
        self.bt_back.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.bt_back.clicked.connect(self.back_to_info)

        lower_container.layout().addWidget(self.bt_back)
        lower_container.layout().addWidget(new_spacer())

        self.bt_close = QPushButton(self.i18n['close'].capitalize())
        self.bt_close.setObjectName('close')
        self.bt_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.bt_close.clicked.connect(self.close)

        lower_container.layout().addWidget(self.bt_close)
        layout.addWidget(lower_container)
        self.setMinimumWidth(int(self.gbox_info.sizeHint().width() * 1.2))

        screen_height = get_current_screen_geometry().height()
        self.setMaximumHeight(int(screen_height * 0.8))
        self.adjustSize()

    @staticmethod
    def open_url(url: str):
        Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)

    def _show_full_field_val(self, val: str):
        self.gbox_info.hide()
        self.bt_back.setVisible(True)
        self.text_field.show()
        self.text_field.setPlainText(val)

    def _gen_show_button(self, idx: int, val: str):

        is_url = self._can_open_url and bool(RE_URL.match(val)) if val else False

        if is_url:
            bt_label = self.i18n["manage_window.info.open_url"]

            def _show_field():
                self.open_url(val)
        else:
            bt_label = self.i18n["show"].capitalize()

            def _show_field():
                self._show_full_field_val(val)

        bt_full_field = QPushButton(bt_label)
        bt_full_field.setObjectName("show")
        bt_full_field.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        bt_full_field.clicked.connect(_show_field)
        self.gbox_info.layout().addWidget(bt_full_field, idx, 2)

    def back_to_info(self):
        self.text_field.setPlainText("")
        self.text_field.hide()
        self.gbox_info.show()
        self.bt_back.setVisible(False)
