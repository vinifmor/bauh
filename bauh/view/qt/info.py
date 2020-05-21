from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QIcon, QCursor
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QGroupBox, \
    QLineEdit, QLabel, QGridLayout, QPushButton, QPlainTextEdit, QToolBar, QScrollArea, QFrame, QWidget

from bauh.api.abstract.cache import MemoryCache
from bauh.view.qt.components import new_spacer
from bauh.view.util.translation import I18n

IGNORED_ATTRS = {'name', '__app__'}


class InfoDialog(QDialog):

    def __init__(self, app: dict, icon_cache: MemoryCache, i18n: I18n, screen_size: QSize):
        super(InfoDialog, self).__init__(flags=Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self.setWindowTitle(str(app['__app__']))
        self.screen_size = screen_size
        self.i18n = i18n
        layout = QVBoxLayout()
        self.setLayout(layout)

        scroll = QScrollArea(self)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        comps_container = QWidget()
        comps_container.setLayout(QVBoxLayout())
        scroll.setWidget(comps_container)

        # shows complete field string
        self.text_field = QPlainTextEdit()
        self.text_field.setReadOnly(True)
        comps_container.layout().addWidget(self.text_field)
        self.text_field.hide()

        self.gbox_info = QGroupBox()
        self.gbox_info.setLayout(QGridLayout())

        comps_container.layout().addWidget(self.gbox_info)

        # THERE ARE CRASHES WITH SOME RARE ICONS ( like insomnia ). IT CAN BE A QT BUG. IN THE MEANTIME, ONLY THE TYPE ICON WILL BE RENDERED
        #
        # icon_data = icon_cache.get(app['__app__'].model.icon_url)
        #
        # if icon_data and icon_data.get('icon'):
        #     self.setWindowIcon(icon_data.get('icon'))
        self.setWindowIcon(QIcon(app['__app__'].model.get_type_icon_path()))

        for idx, attr in enumerate(sorted(app.keys())):
            if attr not in IGNORED_ATTRS and app[attr]:
                i18n_key = app['__app__'].model.gem_name + '.info.' + attr.lower()

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

                self.gbox_info.layout().addWidget(label, idx, 0)
                self.gbox_info.layout().addWidget(text, idx, 1)
                self._gen_show_button(idx, show_val)

        layout.addWidget(scroll)

        lower_bar = QToolBar()
        bt_back = QPushButton(self.i18n['back'].capitalize())
        bt_back.setVisible(False)
        bt_back.setCursor(QCursor(Qt.PointingHandCursor))
        bt_back.clicked.connect(self.back_to_info)

        self.ref_bt_back = lower_bar.addWidget(bt_back)
        lower_bar.addWidget(new_spacer())

        bt_close = QPushButton(self.i18n['close'].capitalize())
        bt_close.setCursor(QCursor(Qt.PointingHandCursor))
        bt_close.clicked.connect(lambda: self.close())

        lower_bar.addWidget(bt_close)
        layout.addWidget(lower_bar)
        self.setMinimumWidth(self.gbox_info.sizeHint().width() * 1.2)
        self.setMaximumHeight(screen_size.height() * 0.8)
        self.adjustSize()

    def _gen_show_button(self, idx: int, val):

        def show_full_field():
            self.gbox_info.hide()
            self.ref_bt_back.setVisible(True)
            self.text_field.show()
            self.text_field.setPlainText(val)

        bt_full_field = QPushButton(self.i18n['show'].capitalize())
        bt_full_field.setCursor(QCursor(Qt.PointingHandCursor))
        bt_full_field.clicked.connect(show_full_field)
        self.gbox_info.layout().addWidget(bt_full_field, idx, 2)

    def back_to_info(self):
        self.text_field.setPlainText("")
        self.text_field.hide()
        self.gbox_info.show()
        self.ref_bt_back.setVisible(False)
