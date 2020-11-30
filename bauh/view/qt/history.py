import operator
from functools import reduce

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QCursor
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTableWidget, QHeaderView, QLabel

from bauh.api.abstract.cache import MemoryCache
from bauh.api.abstract.model import PackageHistory
from bauh.view.qt.view_model import PackageView
from bauh.view.util.translation import I18n


class HistoryDialog(QDialog):

    def __init__(self, history: PackageHistory, icon_cache: MemoryCache, i18n: I18n):
        super(HistoryDialog, self).__init__()
        self.setWindowFlags(Qt.CustomizeWindowHint | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)

        view = PackageView(model=history.pkg, i18n=i18n)

        self.setWindowTitle('{} - {}'.format(i18n['popup.history.title'], view))

        layout = QVBoxLayout()
        self.setLayout(layout)

        table_history = QTableWidget()
        table_history.setFocusPolicy(Qt.NoFocus)
        table_history.setShowGrid(False)
        table_history.verticalHeader().setVisible(False)
        table_history.setAlternatingRowColors(True)

        table_history.setColumnCount(len(history.history[0]))
        table_history.setRowCount(len(history.history))
        table_history.setHorizontalHeaderLabels([i18n.get(history.pkg.get_type().lower() + '.history.' + key, i18n.get(key, key)).capitalize() for key in sorted(history.history[0].keys())])

        for row, data in enumerate(history.history):

            current_status = history.pkg_status_idx == row

            for col, key in enumerate(sorted(data.keys())):
                item = QLabel()
                item.setProperty('even', row % 2 == 0)
                item.setText(' {}'.format(data[key]))

                if current_status:
                    item.setCursor(QCursor(Qt.WhatsThisCursor))
                    item.setProperty('outdated',  str(row != 0).lower())

                    tip = '{}. {}.'.format(i18n['popup.history.selected.tooltip'], i18n['version.{}'.format('updated'if row == 0 else 'outdated')].capitalize())

                    item.setToolTip(tip)

                table_history.setCellWidget(row, col, item)

        layout.addWidget(table_history)

        header_horizontal = table_history.horizontalHeader()
        for i in range(0, table_history.columnCount()):
            header_horizontal.setSectionResizeMode(i, QHeaderView.Stretch)

        new_width = reduce(operator.add, [table_history.columnWidth(i) for i in range(table_history.columnCount())])
        self.resize(new_width, table_history.height())

        # THERE ARE CRASHES WITH SOME RARE ICONS ( like insomnia ). IT CAN BE A QT BUG. IN THE MEANTIME, ONLY THE TYPE ICON WILL BE RENDERED
        #
        # icon_data = icon_cache.get(history.pkg.icon_url)
        # if icon_data and icon_data.get('icon'):
        #     self.setWindowIcon(icon_data.get('icon'))
        self.setWindowIcon(QIcon(history.pkg.get_type_icon_path()))
