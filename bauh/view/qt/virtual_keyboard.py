from string import ascii_lowercase, ascii_uppercase
from typing import Iterable, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QDialog, QLineEdit, QVBoxLayout, QPushButton, QToolBar, QApplication, QWidget, QHBoxLayout

from bauh.view.qt.components import new_spacer
from bauh.view.util.translation import I18n

SYMBOLS = ('@', '-', '_', '=', '#', '$', '%', '&', '*', '(', ')', '+', '-', ':', ',', ';', '?', '!', '/', '\\', "'", '"')


class VirtualKeyboard(QDialog):

    def __init__(self, i18n: I18n, input_text: Optional[QLineEdit] = None):
        super(VirtualKeyboard, self).__init__(flags=Qt.CustomizeWindowHint | Qt.FramelessWindowHint)
        screen_size = QApplication.primaryScreen().size()

        self.input_text = input_text
        self.i18n = i18n
        self.setLayout(QVBoxLayout())

        self.upper_bar = QToolBar()

        self.bt_change_case = QPushButton()
        self.bt_change_case.clicked.connect(self._change_case)
        self.upper_bar.addWidget(self.bt_change_case)

        self.bt_symbols = QPushButton('@#$%')
        self.bt_symbols.clicked.connect(self._display_symbols)
        self.upper_bar.addWidget(self.bt_symbols)

        self.layout().addWidget(self.upper_bar)

        self.container_numbers = self._gen_range_buttons([*range(0, 10)])
        self.layout().addWidget(self.container_numbers)

        self.container_symbols = self._gen_range_buttons(SYMBOLS)
        self.layout().addWidget(self.container_symbols)
        self.container_symbols.hide()

        self.lower_container = self._gen_range_buttons(ascii_lowercase)
        self.layout().addWidget(self.lower_container)

        self.upper_container = self._gen_range_buttons(ascii_uppercase)
        self.layout().addWidget(self.upper_container)

        self.lower_bar = QToolBar()
        self.lower_bar.addWidget(new_spacer())

        self.bt_space = QPushButton(self.i18n['vkeyboard.bt_space'])
        self.bt_space.clicked.connect(self._add_space)
        self.bt_space.setMinimumWidth(int(screen_size.width() / 2.5))
        self.lower_bar.addWidget(self.bt_space)
        self.lower_bar.addWidget(new_spacer())

        self.bt_erase = QPushButton(self.i18n['vkeyboard.bt_erase'])
        self.bt_erase.clicked.connect(self._return_and_remove_character)
        self.lower_bar.addWidget(self.bt_erase)

        self.bt_done = QPushButton(self.i18n['vkeyboard.bt_done'])
        self.bt_done.clicked.connect(self._enter_and_close)
        self.lower_bar.addWidget(self.bt_done)
        self.layout().addWidget(self.lower_bar)

        screen_size = QApplication.primaryScreen().size()
        self.setFixedSize(screen_size.width(), int(screen_size.height() / 2.05))
        self.move(0, screen_size.height() / 1.95)

        self._change_case()

    def _add_space(self):
        if self.input_text:
            self.input_text.setText(self.input_text.text() + ' ')

    def _return_and_remove_character(self):
        if self.input_text:
            self.input_text.setText(self.input_text.text()[0:-1])

    def _gen_range_buttons(self, symbols: Iterable) -> QWidget:
        container = QWidget()
        container.setLayout(QVBoxLayout())

        row = None
        for idx, s in enumerate(symbols):
            if not row or (idx + 1) % 16 == 0:
                row = QWidget()
                row.setLayout(QHBoxLayout())
                container.layout().addWidget(row)

            row.layout().addWidget(self._map_button(s))

        return container

    def _change_case(self):
        if self.lower_container.isVisible():
            self.lower_container.hide()
            self.upper_container.show()
            self.bt_change_case.setText('abc')
        else:
            self.upper_container.hide()
            self.lower_container.show()
            self.bt_change_case.setText('^ABC')

    def _display_symbols(self):
        if self.container_numbers.isVisible():
            self.container_numbers.hide()
            self.container_symbols.show()
        else:
            self.container_symbols.hide()
            self.container_numbers.show()

    def _enter_and_close(self):
        if self.input_text:
            QTest.keyPress(self.input_text, Qt.Key_Enter, Qt.NoModifier)

        self.close()

    def _map_button(self, symbol: object) -> QPushButton:
        bt = QPushButton(str(symbol))
        bt.setFixedSize(50, 50)

        def hit_symbol():
            if self.input_text:
                self.input_text.setText(self.input_text.text() + str(symbol))

        bt.clicked.connect(hit_symbol)
        return bt
