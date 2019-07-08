from threading import Lock
from typing import List

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QPixmap, QIcon, QColor, QCursor
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt5.QtWidgets import QTableWidget, QTableView, QMenu, QAction, QTableWidgetItem, QToolButton, QWidget, \
    QHeaderView, QLabel

from fpakman.core import resource
from fpakman.core.model import FlatpakApplication, ApplicationStatus
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
        self.app_view.updated_checked = not not_checked
        self.setIcon(self.icon_on if not not_checked else self.icon_off)
        self.root.change_update_state()


class AppsTable(QTableWidget):

    def __init__(self, parent: QWidget, icon_cache: Cache):
        super(AppsTable, self).__init__()
        self.setParent(parent)
        self.window = parent
        self.column_names = [parent.locale_keys[key].capitalize() for key in ['flatpak.info.name',
                                                                              'flatpak.info.version',
                                                                              'manage_window.columns.latest_version',
                                                                              'flatpak.info.branch',
                                                                              'flatpak.info.description',
                                                                              'flatpak.info.origin',
                                                                              'manage_window.columns.installed',
                                                                              'manage_window.columns.update']]
        self.setColumnCount(len(self.column_names))
        self.setFocusPolicy(Qt.NoFocus)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QTableView.SelectRows)
        self.setHorizontalHeaderLabels(self.column_names)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.icon_flathub = QIcon(resource.get_path('img/flathub.svg'))

        self.network_man = QNetworkAccessManager()
        self.network_man.finished.connect(self._load_icon)

        self.icon_cache = icon_cache
        self.lock_async_data = Lock()

    def contextMenuEvent(self, QContextMenuEvent):  # selected row right click event

        app = self.get_selected_app()

        menu_row = QMenu()

        if app.model.installed:
            action_info = QAction(self.window.locale_keys["manage_window.apps_table.row.actions.info"])
            action_info.setIcon(QIcon(resource.get_path('img/info.svg')))
            action_info.triggered.connect(self._get_app_info)
            menu_row.addAction(action_info)

            action_history = QAction(self.window.locale_keys["manage_window.apps_table.row.actions.history"])
            action_history.setIcon(QIcon(resource.get_path('img/history.svg')))
            action_history.triggered.connect(self._get_app_history)
            menu_row.addAction(action_history)

            action_uninstall = QAction(self.window.locale_keys["manage_window.apps_table.row.actions.uninstall"])
            action_uninstall.setIcon(QIcon(resource.get_path('img/uninstall.svg')))
            action_uninstall.triggered.connect(self._uninstall_app)
            menu_row.addAction(action_uninstall)

            if isinstance(app.model, FlatpakApplication) and not app.model.runtime:  # not available for runtimes
                action_downgrade = QAction(self.window.locale_keys["manage_window.apps_table.row.actions.downgrade"])
                action_downgrade.triggered.connect(self._downgrade_app)
                action_downgrade.setIcon(QIcon(resource.get_path('img/downgrade.svg')))
                menu_row.addAction(action_downgrade)
        else:
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
                    self.item(idx, 2).setText(app_v.model.base_data.latest_version)
                    self._set_col_description(self.item(idx, 4), app_v)

            visible, ready = 0, 0

            for app_v in self.window.apps:
                if app_v.visible:
                    visible += 1

                if app_v.status == ApplicationViewStatus.READY:
                    ready += 1

            if ready == visible:
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

    def _load_icon(self, http_response):
        icon_url = http_response.url().toString()

        if not self.icon_cache.get(icon_url):
            pixmap = QPixmap()
            pixmap.loadFromData(http_response.readAll())
            icon = QIcon(pixmap)
            self.icon_cache.add(icon_url, icon)

            for idx, app in enumerate(self.window.apps):
                if app.model.base_data.icon_url == icon_url:
                    self.item(idx, 0).setIcon(icon)
                    break

    def update_apps(self, app_views: List[ApplicationView]):
        self.setEnabled(True)
        self.setRowCount(len(app_views) if app_views else 0)

        if app_views:
            for idx, app_v in enumerate(app_views):

                col_name = QTableWidgetItem()
                col_name.setText(app_v.model.base_data.name)
                col_name.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

                if not app_v.model.base_data.icon_url:
                    col_name.setIcon(self.icon_flathub)
                else:
                    cached_icon = self.icon_cache.get(app_v.model.base_data.icon_url)

                    if cached_icon:
                        col_name.setIcon(cached_icon)
                    else:
                        col_name.setIcon(self.icon_flathub)

                self.setItem(idx, 0, col_name)

                col_version = QTableWidgetItem()
                col_version.setText(app_v.model.base_data.version)
                col_version.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.setItem(idx, 1, col_version)

                col_release = QTableWidgetItem()
                col_release.setText(app_v.get_async_attr('latest_version'))
                col_release.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.setItem(idx, 2, col_release)

                if app_v.model.base_data.version and app_v.model.base_data.latest_version and app_v.model.base_data.version < app_v.model.base_data.latest_version:
                    col_release.setForeground(QColor('orange'))

                col_branch = QTableWidgetItem()
                col_branch.setText(app_v.model.branch if isinstance(app_v.model, FlatpakApplication) else '')
                col_branch.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.setItem(idx, 3, col_branch)

                col_description = QTableWidgetItem()
                col_description.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self._set_col_description(col_description, app_v)

                self.setItem(idx, 4, col_description)

                col_origin = QTableWidgetItem()
                col_origin.setText(app_v.model.origin if isinstance(app_v.model, FlatpakApplication) else '')
                col_origin.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.setItem(idx, 5, col_origin)

                col_installed = QLabel()
                col_installed.setPixmap((QPixmap(resource.get_path('img/{}.svg'.format('checked' if app_v.model.installed else 'red_cross')))))
                col_installed.setAlignment(Qt.AlignCenter)

                self.setCellWidget(idx, 6, col_installed)

                col_update = UpdateToggleButton(app_v, self.window, self.window.locale_keys, app_v.model.update) if app_v.model.update else None
                self.setCellWidget(idx, 7, col_update)

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
