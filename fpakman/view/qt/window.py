import operator
from functools import reduce
from threading import Lock
from typing import List

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl, QEvent
from PyQt5.QtGui import QIcon, QColor, QPixmap, QWindowStateChangeEvent
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QApplication, QTableWidget, \
    QTableWidgetItem, QTableView, QCheckBox, QHeaderView, QToolButton, QToolBar, \
    QSizePolicy, QLabel, QMessageBox

from fpakman.core import __version__
from fpakman.core import resource
from fpakman.core.controller import FlatpakController


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
        self.root.change_update_state()


class ManageWindow(QWidget):

    __BASE_HEIGHT__ = 400

    def __init__(self, locale_keys: dict, controller: FlatpakController, tray_icon = None):
        super(ManageWindow, self).__init__()
        self.locale_keys = locale_keys
        self.column_names = [locale_keys['manage_window.columns.name'],
                             locale_keys['manage_window.columns.version'],
                             locale_keys['manage_window.columns.latest_version'],
                             locale_keys['manage_window.columns.branch'],
                             locale_keys['manage_window.columns.arch'],
                             locale_keys['manage_window.columns.ref'],
                             locale_keys['manage_window.columns.origin'],
                             locale_keys['manage_window.columns.update']]
        self.controller = controller
        self.icon_cache = {}
        self.tray_icon = tray_icon
        self.thread_lock = Lock()
        self.working = False  # restrict the number of threaded actions
        self.apps = []
        self.label_flatpak = None

        self.network_man = QNetworkAccessManager()
        self.network_man.finished.connect(self._load_icon)

        self.icon_flathub = QIcon(resource.get_path('img/flathub_45.svg'))
        self._check_flatpak_installed()
        self.resize(ManageWindow.__BASE_HEIGHT__, ManageWindow.__BASE_HEIGHT__)
        self.setWindowTitle('fpakman ({})'.format(__version__))
        self.setWindowIcon(self.icon_flathub)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.checkbox_only_apps = QCheckBox()
        self.checkbox_only_apps.setText(self.locale_keys['manage_window.checkbox.only_apps'])
        self.checkbox_only_apps.setChecked(True)
        self.checkbox_only_apps.stateChanged.connect(self.filter_only_apps)

        toolbar = QToolBar()
        toolbar.addWidget(self.checkbox_only_apps)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        toolbar.addWidget(spacer)

        self.label_status = QLabel()
        self.label_status.setText('')
        toolbar.addWidget(self.label_status)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        toolbar.addWidget(spacer)

        self.bt_refresh = QToolButton()
        self.bt_refresh.setIcon(QIcon(resource.get_path('img/refresh.svg')))
        self.bt_refresh.clicked.connect(self.refresh)
        toolbar.addWidget(self.bt_refresh)

        self.bt_update = QToolButton()
        self.bt_update.setIcon(QIcon(resource.get_path('img/update_green.svg')))
        self.bt_update.setEnabled(False)
        self.bt_update.clicked.connect(self.update_selected)
        toolbar.addWidget(self.bt_update)

        self.layout.addWidget(toolbar)

        self.table_apps = QTableWidget()
        self.table_apps.setColumnCount(len(self.column_names))
        self.table_apps.setFocusPolicy(Qt.NoFocus)
        self.table_apps.setShowGrid(False)
        self.table_apps.verticalHeader().setVisible(False)
        self.table_apps.setSelectionBehavior(QTableView.SelectRows)
        self.table_apps.setHorizontalHeaderLabels(self.column_names)
        self.table_apps.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._change_table_headers_policy()

        self.layout.addWidget(self.table_apps)

        self.thread_update = UpdateSelectedApps(self.controller)
        self.thread_update.signal.connect(self._finish_update_selected)

        self.thread_refresh = RefreshApps(self.controller)
        self.thread_refresh.signal.connect(self._finish_refresh)

        self.toolbar_bottom = QToolBar()
        self.label_updates = QLabel('')
        self.toolbar_bottom.addWidget(self.label_updates)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.toolbar_bottom.addWidget(spacer)

        self.label_flatpak = QLabel(self._get_flatpak_label())
        self.toolbar_bottom.addWidget(self.label_flatpak)
        self.layout.addWidget(self.toolbar_bottom)

        self.centralize()

    def _change_table_headers_policy(self, policy: QHeaderView = QHeaderView.ResizeToContents):
        header_horizontal = self.table_apps.horizontalHeader()
        for i in range(0, len(self.column_names)):
            header_horizontal.setSectionResizeMode(i, policy)

    def changeEvent(self, e: QEvent):

        if isinstance(e, QWindowStateChangeEvent):
            self._change_table_headers_policy(QHeaderView.Stretch if self.isMaximized() else QHeaderView.ResizeToContents)

    def closeEvent(self, event):

        if self.tray_icon:
            event.ignore()
            self.hide()

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
            error_msg.setWindowTitle(self.locale_keys['popup.flatpak_not_installed.title'])
            error_msg.setText(self.locale_keys['popup.flatpak_not_installed.msg'] + '...')
            error_msg.setWindowIcon(self.icon_flathub)
            error_msg.exec_()
            exit(1)

        if self.label_flatpak:
            self.label_flatpak.setText(self._get_flatpak_label())

    def _get_flatpak_label(self):
        return 'flatpak: ' + self.controller.get_version()

    def _acquire_lock(self):

        self.thread_lock.acquire()

        if not self.working:
            self.working = True

        self.thread_lock.release()
        return self.working

    def _release_lock(self):

        self.thread_lock.acquire()

        if self.working:
            self.working = False

        self.thread_lock.release()

    def refresh(self):

        if self._acquire_lock():
            self._check_flatpak_installed()
            self._begin_action(self.locale_keys['manage_window.status.refreshing'] + '...')
            self.thread_refresh.start()

    def _finish_refresh(self):

        self.update_apps(self.thread_refresh.apps)
        self.finish_action()
        self._release_lock()

    def filter_only_apps(self, only_apps: int):

        if self.apps:
            show_only_apps = True if only_apps == 2 else False

            for idx, app in enumerate(self.apps):
                hidden = show_only_apps and app['model']['runtime']
                self.table_apps.setRowHidden(idx, hidden)
                app['visible'] = not hidden

            self.change_update_state()
            self._change_table_headers_policy(QHeaderView.Stretch)
            self._change_table_headers_policy()
            self.resize_and_center()

    def change_update_state(self):

        enable_bt_update = False

        updates = len([app for app in self.apps if app['model']['update']])

        if updates > 0:
            self.label_updates.setText('{}: {}'.format(self.locale_keys['manage_window.label.updates'], updates))
        else:
            self.label_updates.setText('')

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

    def update_apps(self, apps: List[dict]):
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

                col_release = QTableWidgetItem()
                col_release.setText(app['latest_version'])
                col_release.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.table_apps.setItem(idx, 2, col_release)

                if app['update']:
                    col_release.setForeground(QColor('orange'))

                col_branch = QTableWidgetItem()
                col_branch.setText(app['branch'])
                col_branch.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.table_apps.setItem(idx, 3, col_branch)

                col_arch = QTableWidgetItem()
                col_arch.setText(app['arch'])
                col_arch.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.table_apps.setItem(idx, 4, col_arch)

                col_package = QTableWidgetItem()
                col_package.setText(app['ref'])
                col_package.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.table_apps.setItem(idx, 5, col_package)

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

        self.change_update_state()
        self.filter_only_apps(2 if self.checkbox_only_apps.isChecked() else 0)
        self.resize_and_center()

    def resize_and_center(self):
        new_width = reduce(operator.add, [self.table_apps.columnWidth(i) for i in range(len(self.column_names))]) * 1.05
        self.resize(new_width, self.height())
        self.centralize()

    def update_selected(self):

        if self._acquire_lock():
            if self.apps:
                to_update = [pak['model']['ref'] for pak in self.apps if pak['visible'] and pak['update_checked']]

                if to_update:
                    self._begin_action(self.locale_keys['manage_window.status.updating'] + '...')
                    self.thread_update.refs_to_update = to_update
                    self.thread_update.start()

    def _finish_update_selected(self):
        self.update_apps(self.thread_update.updated_apps)
        self.finish_action()

        if self.tray_icon and self.thread_update.updated_apps:
            self.tray_icon.notify_updates(len([app for app in self.thread_update.updated_apps if app['update']]))

        self._release_lock()

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

class UpdateSelectedApps(QThread):

    signal = pyqtSignal()

    def __init__(self, controller: FlatpakController):
        super(UpdateSelectedApps, self).__init__()
        self.controller = controller
        self.refs_to_update = []
        self.updated_apps = None

    def run(self):
        self.updated_apps = self.controller.update(self.refs_to_update)
        self.signal.emit()


class RefreshApps(QThread):

    signal = pyqtSignal()

    def __init__(self, controller: FlatpakController):
        super(RefreshApps, self).__init__()
        self.controller = controller
        self.apps = None

    def run(self):
        self.apps = self.controller.refresh()
        self.signal.emit()
