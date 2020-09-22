from string import ascii_lowercase, ascii_uppercase
from typing import Iterable

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QDialog, QLineEdit, QVBoxLayout, QPushButton, QToolBar, QApplication, QWidget, QHBoxLayout


class VirtualKeyboard(QDialog):

    def __init__(self, input_text: QLineEdit):
        super(VirtualKeyboard, self).__init__(flags=Qt.CustomizeWindowHint | Qt.FramelessWindowHint)
        self.setLayout(QVBoxLayout())
        self.input_text = input_text

        self.lower_container = self._gen_ascii_buttons(ascii_lowercase)
        self.layout().addWidget(self.lower_container)

        self.upper_container = self._gen_ascii_buttons(ascii_uppercase)
        self.layout().addWidget(self.upper_container)
        self.upper_container.hide()

        self.bt_change_case = QPushButton("^ABC")
        self.bt_change_case.clicked.connect(self._change_case)
        self.lower_toolbar = QToolBar()
        self.lower_toolbar.addWidget(self.bt_change_case)
        self.layout().addWidget(self.lower_toolbar)

        screen_size = QApplication.primaryScreen().size()
        self.setFixedSize(screen_size.width(), screen_size.height() / 2)
        self.move(0, screen_size.height() / 2)

    def _gen_ascii_buttons(self, symbols: Iterable[str]) -> QWidget:
        container = QWidget()
        container.setLayout(QVBoxLayout())

        row = None
        for idx, s in enumerate(symbols):
            if not row or (idx + 1) % 11 == 0:
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

    def _map_button(self, symbol: str) -> QPushButton:
        bt = QPushButton(symbol)
        bt.setFixedSize(50, 50)

        def hit_symbol():
            self.input_text.setText(self.input_text.text() + symbol)

        bt.clicked.connect(hit_symbol)
        return bt

    def close(self) -> bool:
        QTest.keyPress(self.input_text, Qt.Key_Enter, Qt.NoModifier)
        super(VirtualKeyboard, self).close()
