import operator
from functools import reduce

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView
from bauh.api.abstract.cache import MemoryCache
from bauh.api.abstract.model import PackageHistory


class HistoryDialog(QDialog):

    def __init__(self, history: PackageHistory, icon_cache: MemoryCache, locale_keys: dict):
        super(HistoryDialog, self).__init__()

        self.setWindowTitle('{} - {} ({})'.format(locale_keys['popup.history.title'], history.pkg.name, history.pkg.get_type()))

        layout = QVBoxLayout()
        self.setLayout(layout)

        table_history = QTableWidget()
        table_history.setFocusPolicy(Qt.NoFocus)
        table_history.setShowGrid(False)
        table_history.verticalHeader().setVisible(False)
        table_history.setAlternatingRowColors(True)

        table_history.setColumnCount(len(history.history[0]))
        table_history.setRowCount(len(history.history))
        table_history.setHorizontalHeaderLabels([locale_keys.get(history.pkg.get_type() + '.history.' + key, key).capitalize() for key in sorted(history.history[0].keys())])

        for row, commit in enumerate(history.history):

            current_status = history.pkg_status_idx == row

            for col, key in enumerate(sorted(commit.keys())):
                item = QTableWidgetItem()
                item.setText(str(commit[key]))
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

                if current_status:
                    item.setBackground(QColor('#ffbf00' if row != 0 else '#32CD32'))
                    tip = '{}. {}.'.format(locale_keys['popup.history.selected.tooltip'], locale_keys['version.{}'.format('updated'if row == 0 else 'outdated')].capitalize())

                    item.setToolTip(tip)

                table_history.setItem(row, col, item)

        layout.addWidget(table_history)

        header_horizontal = table_history.horizontalHeader()
        for i in range(0, table_history.columnCount()):
            header_horizontal.setSectionResizeMode(i, QHeaderView.Stretch)

        new_width = reduce(operator.add, [table_history.columnWidth(i) for i in range(table_history.columnCount())])
        self.resize(new_width, table_history.height())

        icon_data = icon_cache.get(history.pkg.icon_url)

        if icon_data and icon_data.get('icon'):
            self.setWindowIcon(icon_data.get('icon'))
