import os
from threading import Lock
from typing import List

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QPixmap, QIcon, QColor, QCursor
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt5.QtWidgets import QTableWidget, QTableView, QMenu, QAction, QTableWidgetItem, QToolButton, QWidget, \
    QHeaderView, QLabel

from fpakman.core import resource
from fpakman.core.model import ApplicationStatus
from fpakman.util.cache import Cache
from fpakman.view.qt import dialog
from fpakman.view.qt.view_model import ApplicationView, ApplicationViewStatus


class UpdateToggleButton(QToolButton):

    def __init__(self, app_view: ApplicationView, root: QWidget, locale_keys: dict, checked: bool = True):
        super(UpdateToggleButton, self).__init__()
        self.app_view = app_view
        self.root = root
        self.setCheckable(True)
        self.clicked.connect(self.change_state)
        self.icon_on = QIcon(resource.get_path('img/toggle_on.svg'))
        self.icon_off = QIcon(resource.get_path('img/toggle_off.svg'))
        self.setIcon(self.icon_on)
        self.setStyleSheet('border: 0px;')
        self.setToolTip(locale_keys['manage_window.apps_table.upgrade_toggle.tooltip'])

        if not checked:
            self.click()

    def change_state(self, not_checked: bool):
        self.app_view.update_checked = not not_checked
        self.setIcon(self.icon_on if not not_checked else self.icon_off)
        self.root.change_update_state()


class AppsTable(QTableWidget):

    def __init__(self, parent: QWidget, icon_cache: Cache, disk_cache: bool):
        super(AppsTable, self).__init__()
        self.setParent(parent)
        self.window = parent
        self.disk_cache = disk_cache
        self.column_names = [parent.locale_keys[key].capitalize() for key in ['name',
                                                                              'version',
                                                                              'latest_version',
                                                                              'flatpak.info.description',
                                                                              'type',
                                                                              'installed',
                                                                              'manage_window.columns.update']]
        self.setColumnCount(len(self.column_names))
        self.setFocusPolicy(Qt.NoFocus)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QTableView.SelectRows)
        self.setHorizontalHeaderLabels(self.column_names)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.icon_flathub = QIcon(resource.get_path('img/flathub.svg'))
        self.icon_logo = QIcon(resource.get_path('img/logo.svg'))

        self.network_man = QNetworkAccessManager()
        self.network_man.finished.connect(self._load_icon_and_cache)

        self.icon_cache = icon_cache
        self.lock_async_data = Lock()

    def contextMenuEvent(self, QContextMenuEvent):  # selected row right click event

        app = self.get_selected_app()

        menu_row = QMenu()

        if app.model.installed:

            if app.model.has_info():
                action_info = QAction(self.window.locale_keys["manage_window.apps_table.row.actions.info"])
                action_info.setIcon(QIcon(resource.get_path('img/info.svg')))
                action_info.triggered.connect(self._get_app_info)
                menu_row.addAction(action_info)

            if app.model.has_history():
                action_history = QAction(self.window.locale_keys["manage_window.apps_table.row.actions.history"])
                action_history.setIcon(QIcon(resource.get_path('img/history.svg')))
                action_history.triggered.connect(self._get_app_history)
                menu_row.addAction(action_history)

            if app.model.can_be_uninstalled():
                action_uninstall = QAction(self.window.locale_keys["manage_window.apps_table.row.actions.uninstall"])
                action_uninstall.setIcon(QIcon(resource.get_path('img/uninstall.svg')))
                action_uninstall.triggered.connect(self._uninstall_app)
                menu_row.addAction(action_uninstall)

            if app.model.can_be_downgraded():
                action_downgrade = QAction(self.window.locale_keys["manage_window.apps_table.row.actions.downgrade"])
                action_downgrade.triggered.connect(self._downgrade_app)
                action_downgrade.setIcon(QIcon(resource.get_path('img/downgrade.svg')))
                menu_row.addAction(action_downgrade)
        else:
            if app.model.can_be_installed():
                action_install = QAction(self.window.locale_keys["manage_window.apps_table.row.actions.install"])
                action_install.setIcon(QIcon(resource.get_path('img/install.svg')))
                action_install.triggered.connect(self._install_app)
                menu_row.addAction(action_install)

        menu_row.adjustSize()
        menu_row.popup(QCursor.pos())
        menu_row.exec_()

    def fill_async_data(self):

        self.lock_async_data.acquire()

        if self.window.apps:

            for idx, app_v in enumerate(self.window.apps):

                if app_v.visible and app_v.status == ApplicationViewStatus.LOADING and app_v.model.status == ApplicationStatus.READY:
                    self.network_man.get(QNetworkRequest(QUrl(app_v.model.base_data.icon_url)))

                    app_name = self.item(idx, 0).text()

                    if not app_name or app_name == '...':
                        self.item(idx, 0).setText(app_v.model.base_data.name)

                    self.cellWidget(idx, 2).setText(app_v.model.base_data.latest_version)
                    self._set_col_description(self.item(idx, 3), app_v)
                    app_v.status = ApplicationViewStatus.READY

            self.window.resize_and_center()

        self.lock_async_data.release()

    def get_selected_app(self) -> ApplicationView:
        return self.window.apps[self.currentRow()]

    def get_selected_app_icon(self) -> QIcon:
        return self.item(self.currentRow(), 0).icon()

    def _uninstall_app(self):
        selected_app = self.get_selected_app()

        if dialog.ask_confirmation(title=self.window.locale_keys['manage_window.apps_table.row.actions.uninstall.popup.title'],
                                   body=self.window.locale_keys['manage_window.apps_table.row.actions.uninstall.popup.body'].format(selected_app.model.base_data.name),
                                   locale_keys=self.window.locale_keys):
            self.window.uninstall_app(selected_app)

    def _downgrade_app(self):
        selected_app = self.get_selected_app()

        if dialog.ask_confirmation(title=self.window.locale_keys['manage_window.apps_table.row.actions.downgrade'],
                                   body=self.window.locale_keys['manage_window.apps_table.row.actions.downgrade.popup.body'].format(selected_app.model.base_data.name),
                                   locale_keys=self.window.locale_keys):
            self.window.downgrade_app(selected_app)

    def _get_app_info(self):
        self.window.get_app_info(self.get_selected_app())

    def _get_app_history(self):
        self.window.get_app_history(self.get_selected_app())

    def _install_app(self):
        self.window.install_app(self.get_selected_app())

    def _load_icon_and_cache(self, http_response):
        icon_url = http_response.url().toString()

        icon_data = self.icon_cache.get(icon_url)
        icon_was_cached = True

        if not icon_data:
            icon_was_cached = False
            pixmap = QPixmap()
            icon_bytes = http_response.readAll()
            pixmap.loadFromData(icon_bytes)
            icon = QIcon(pixmap)
            icon_data = {'icon': icon, 'bytes': icon_bytes}
            self.icon_cache.add(icon_url, icon_data)

        for idx, app in enumerate(self.window.apps):
            if app.model.base_data.icon_url == icon_url:
                col_name = self.item(idx, 0)
                col_name.setIcon(icon_data['icon'])

                if self.disk_cache and app.model.supports_disk_cache():
                    if not icon_was_cached or not os.path.exists(app.model.get_disk_icon_path()):
                        self.window.manager.cache_to_disk(app=app.model, icon_bytes=icon_data['bytes'], only_icon=True)

    def update_apps(self, app_views: List[ApplicationView]):
        self.setEnabled(True)
        self.setRowCount(len(app_views) if app_views else 0)

        if app_views:
            for idx, app_v in enumerate(app_views):
                col_name = self._gen_col_name(app_v)
                self.setItem(idx, 0, col_name)

                col_version = QLabel(app_v.model.base_data.version)
                col_version.setAlignment(Qt.AlignCenter)
                self.setCellWidget(idx, 1, col_version)

                col_release = QLabel(app_v.get_async_attr('latest_version'))
                col_release.setAlignment(Qt.AlignCenter)
                self.setCellWidget(idx, 2, col_release)

                if app_v.model.base_data.version and app_v.model.base_data.latest_version and app_v.model.base_data.version < app_v.model.base_data.latest_version:
                    col_release.setStyleSheet("color: orange")

                col_description = QTableWidgetItem()
                col_description.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self._set_col_description(col_description, app_v)

                self.setItem(idx, 3, col_description)

                col_type = QLabel(app_v.model.get_type())
                col_type.setAlignment(Qt.AlignCenter)
                self.setCellWidget(idx, 4, col_type)

                col_installed = QLabel()
                col_installed.setPixmap((QPixmap(resource.get_path('img/{}.svg'.format('checked' if app_v.model.installed else 'red_cross')))))
                col_installed.setAlignment(Qt.AlignCenter)

                self.setCellWidget(idx, 5, col_installed)

                col_update = UpdateToggleButton(app_v, self.window, self.window.locale_keys, app_v.model.update) if app_v.model.update else None
                self.setCellWidget(idx, 6, col_update)

    def _gen_col_name(self, app_v: ApplicationView):
        col = QTableWidgetItem()
        col.setText(app_v.model.base_data.name if app_v.model.base_data.name else '...')
        col.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

        if self.disk_cache and app_v.model.supports_disk_cache() and os.path.exists(app_v.model.get_disk_icon_path()):
            with open(app_v.model.get_disk_icon_path(), 'rb') as f:
                icon_bytes = f.read()
                pixmap = QPixmap()
                pixmap.loadFromData(icon_bytes)
                icon = QIcon(pixmap)
                self.icon_cache.add_non_existing(app_v.model.base_data.icon_url, {'icon': icon, 'bytes': icon_bytes})
        elif not app_v.model.base_data.icon_url:
            icon = QIcon(app_v.model.get_default_icon_path())
        else:
            icon_data = self.icon_cache.get(app_v.model.base_data.icon_url)
            icon = icon_data['icon'] if icon_data else QIcon(app_v.model.get_default_icon_path())

        col.setIcon(icon)
        return col

    def _set_col_description(self, col: QTableWidgetItem, app_v: ApplicationView):
        desc = app_v.get_async_attr('description', strip_html=True)

        if desc:
            col.setText(desc[0:25] + '...')

        if app_v.model.status == ApplicationStatus.READY:
            col.setToolTip(desc)

    def change_headers_policy(self, policy: QHeaderView = QHeaderView.ResizeToContents):
        header_horizontal = self.horizontalHeader()
        for i in range(self.columnCount()):
                header_horizontal.setSectionResizeMode(i, policy)
