import operator
from functools import reduce

from PyQt5 import QtCore
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest

from core import resource, __version__
from typing import List

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt5.QtGui import QIcon, QColor, QPixmap
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QApplication, QTableWidget, \
    QTableWidgetItem, QTableView, QCheckBox, QHeaderView, QToolButton, QToolBar, \
    QSizePolicy, QLabel, QMessageBox

from core.controller import FlatpakController


class UpdateToggleButton(QToolButton):

    def __init__(self, model: dict, root: QWidget, checked: bool = True):
        super(UpdateToggleButton, self).__init__()
        self.model = model
        self.root = root
        self.setCheckable(True)
        self.clicked.connect(self.change_state)
        self.icon_on = QIcon(resource.get_path('img/toggle_on.svg'))
        self.icon_off = QIcon(resource.get_path('img/toggle_off.svg'))
        self.setIcon(self.icon_on)
        self.setStyleSheet('border: 0px;')

        if not checked:
            self.click()

    def change_state(self, not_checked: bool):
        self.model['update_checked'] = not not_checked
        self.setIcon(self.icon_on if not not_checked else self.icon_off)
        self.root.change_update_button_state()


class MainWindow(QWidget):

    __COLUMNS__ = ['Package', 'Version', 'Branch', 'Arch', 'Ref', 'Latest Release', 'Origin', 'Update ?']
    __BASE_HEIGHT__ = 400

    def __init__(self, controller: FlatpakController):
        super(MainWindow, self).__init__()
        self.controller = controller
        self.icon_cache = {}

        self.network_man = QNetworkAccessManager()
        self.network_man.finished.connect(self._load_icon)

        self.icon_flathub = QIcon(resource.get_path('img/flathub_logo.svg'))
        self._check_flatpak_installed()
        self.resize(MainWindow.__BASE_HEIGHT__, MainWindow.__BASE_HEIGHT__)
        self.setWindowTitle('flatman ({})'.format(__version__))
        self.setWindowIcon(self.icon_flathub)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.checkbox_only_apps = QCheckBox()
        self.checkbox_only_apps.setText('Only apps')
        self.checkbox_only_apps.setChecked(True)
        self.checkbox_only_apps.stateChanged.connect(self.filter_only_apps)

        toolbar = QToolBar()
        toolbar.addWidget(self.checkbox_only_apps)

        spacer_1 = QWidget()
        spacer_1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        toolbar.addWidget(spacer_1)

        self.label_status = QLabel()
        self.label_status.setText('')
        toolbar.addWidget(self.label_status)

        spacer_2 = QWidget()
        spacer_2.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        toolbar.addWidget(spacer_2)

        self.bt_refresh = QToolButton()
        self.bt_refresh.setIcon(QIcon(resource.get_path('img/refresh_orange.svg')))
        self.bt_refresh.clicked.connect(lambda: self.refresh(threaded=True))
        toolbar.addWidget(self.bt_refresh)

        self.bt_update = QToolButton()
        self.bt_update.setIcon(QIcon(resource.get_path('img/update_green.svg')))
        self.bt_update.setEnabled(False)
        self.bt_update.clicked.connect(self.update_selected)
        toolbar.addWidget(self.bt_update)

        self.layout.addWidget(toolbar)

        self.table_apps = QTableWidget()
        self.table_apps.setColumnCount(len(MainWindow.__COLUMNS__))
        self.table_apps.setFocusPolicy(Qt.NoFocus)
        self.table_apps.setShowGrid(False)
        self.table_apps.verticalHeader().setVisible(False)
        self.table_apps.setSelectionBehavior(QTableView.SelectRows)
        self.table_apps.setHorizontalHeaderLabels(MainWindow.__COLUMNS__)
        self.table_apps.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        header_horizontal = self.table_apps.horizontalHeader()
        for i in range(0, len(MainWindow.__COLUMNS__)):
            header_horizontal.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        self.layout.addWidget(self.table_apps)

        self.apps = []
        self.centralize()

        self.update_thread = UpdateSelectedPackages(self.controller)
        self.update_thread.signal.connect(self._finish_update_selected)

        self.refresh_thread = RefreshPackages(self.controller)
        self.refresh_thread.signal.connect(self._finish_refresh)

        self.layout.addWidget(QLabel('flatpak: ' + self.controller.get_version()), alignment=Qt.AlignRight)

    def _load_icon(self, http_response):
        icon_url = http_response.url().toString()
        pixmap = QPixmap()
        pixmap.loadFromData(http_response.readAll())
        icon = QIcon(pixmap)
        self.icon_cache[icon_url] = icon

        for idx, app in enumerate(self.apps):
            if app['model']['icon'] == icon_url:
                self.table_apps.item(idx, 0).setIcon(icon)
                self.resize_and_center()
                break

    def _check_flatpak_installed(self):

        if not self.controller.check_installed():
            error_msg = QMessageBox()
            error_msg.setIcon(QMessageBox.Critical)
            error_msg.setText('flatpak seems not to be installed. Exiting...')
            error_msg.setWindowTitle('Error')
            error_msg.setWindowIcon(self.icon_flathub)
            error_msg.exec_()
            exit(1)

    def refresh(self, threaded: bool = False):

        self._check_flatpak_installed()

        self._begin_action('Refreshing...')

        if threaded:
            self.refresh_thread.start()
        else:
            apps = self.controller.refresh()
            self.update_packages(apps)
            self.finish_action()

    def _finish_refresh(self):
        self.update_packages(self.refresh_thread.apps)
        self.finish_action()

    def filter_only_apps(self, only_apps: int):

        if self.apps:
            show_only_apps = True if only_apps == 2 else False

            for idx, app in enumerate(self.apps):
                hidden = show_only_apps and app['model']['runtime']
                self.table_apps.setRowHidden(idx, hidden)
                app['visible'] = not hidden

            self.change_update_button_state()

    def change_update_button_state(self):

        enable_bt_update = False

        for app in self.apps:
            if app['visible'] and app['update_checked']:
                enable_bt_update = True
                break

        self.bt_update.setEnabled(enable_bt_update)

    def centralize(self):
        geo = self.frameGeometry()
        screen = QApplication.desktop().screenNumber(QApplication.desktop().cursor().pos())
        center_point = QApplication.desktop().screenGeometry(screen).center()
        geo.moveCenter(center_point)
        self.move(geo.topLeft())

    def update_packages(self, apps: List[dict]):
        self._check_flatpak_installed()

        self.table_apps.setEnabled(True)
        self.apps = []

        self.table_apps.setRowCount(len(apps) if apps else 0)

        if apps:
            for idx, app in enumerate(apps):

                col_name = QTableWidgetItem()
                col_name.setText(app['name'])
                col_name.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

                if not app['icon']:
                    col_name.setIcon(self.icon_flathub)
                else:
                    cached_icon = self.icon_cache.get(app['icon'])

                    if cached_icon:
                        col_name.setIcon(cached_icon)
                    else:
                        col_name.setIcon(self.icon_flathub)
                        self.network_man.get(QNetworkRequest(QUrl(app['icon'])))

                self.table_apps.setItem(idx, 0, col_name)

                col_version = QTableWidgetItem()
                col_version.setText(app['version'])
                col_version.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.table_apps.setItem(idx, 1, col_version)

                col_branch = QTableWidgetItem()
                col_branch.setText(app['branch'])
                col_branch.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.table_apps.setItem(idx, 2, col_branch)

                col_arch = QTableWidgetItem()
                col_arch.setText(app['arch'])
                col_arch.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.table_apps.setItem(idx, 3, col_arch)

                col_package = QTableWidgetItem()
                col_package.setText(app['ref'])
                col_package.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.table_apps.setItem(idx, 4, col_package)

                col_release = QTableWidgetItem()
                col_release.setText(app['latest_release'])
                col_release.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.table_apps.setItem(idx, 5, col_release)

                if app['update']:
                    col_release.setForeground(QColor('yellow'))

                col_origin = QTableWidgetItem()
                col_origin.setText(app['origin'])
                col_origin.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.table_apps.setItem(idx, 6, col_origin)

                app_model = {'model': app,
                             'update_checked': app['update'],
                             'visible': not app['runtime'] or not self.checkbox_only_apps.isChecked()}

                col_update = UpdateToggleButton(app_model, self, app['update']) if app['update'] else None
                self.table_apps.setCellWidget(idx, 7, col_update)

                self.apps.append(app_model)

        self.change_update_button_state()
        self.filter_only_apps(2 if self.checkbox_only_apps.isChecked() else 0)
        self.resize_and_center()

    def resize_and_center(self):
        new_width = reduce(operator.add, [self.table_apps.columnWidth(i) for i in range(len(MainWindow.__COLUMNS__))]) * 1.05
        self.resize(new_width, self.height())
        self.centralize()

    def update_selected(self):
        if self.apps:
            to_update = [pak['model']['ref'] for pak in self.apps if pak['visible'] and pak['update_checked']]

            if to_update:
                self._begin_action('Updating...')
                self.update_thread.refs_to_update = to_update
                self.update_thread.start()

    def _finish_update_selected(self):
        self.update_packages(self.update_thread.updated_apps)
        self.finish_action()

    def _begin_action(self, action_label: str):
        self.label_status.setText(action_label)
        self.bt_update.setEnabled(False)
        self.bt_refresh.setEnabled(False)
        self.checkbox_only_apps.setEnabled(False)
        self.table_apps.setEnabled(False)

    def finish_action(self):
        self.bt_refresh.setEnabled(True)
        self.checkbox_only_apps.setEnabled(True)
        self.table_apps.setEnabled(True)
        self.label_status.setText('')


# Threaded actions

class UpdateSelectedPackages(QThread):

    signal = pyqtSignal()

    def __init__(self, controller: FlatpakController):
        super(UpdateSelectedPackages, self).__init__()
        self.controller = controller
        self.refs_to_update = []
        self.updated_apps = None

    def run(self):
        self.updated_apps = self.controller.update(self.refs_to_update)
        self.signal.emit()


class RefreshPackages(QThread):

    signal = pyqtSignal()

    def __init__(self, controller: FlatpakController):
        super(RefreshPackages, self).__init__()
        self.controller = controller
        self.apps = None

    def run(self):
        self.apps = self.controller.refresh()
        self.signal.emit()
