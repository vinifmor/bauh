import os
from threading import Lock
from typing import List

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QPixmap, QIcon, QCursor
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt5.QtWidgets import QTableWidget, QTableView, QMenu, QAction, QTableWidgetItem, QToolButton, QWidget, \
    QHeaderView, QLabel, QHBoxLayout, QPushButton, QToolBar
from bauh_api.abstract.cache import MemoryCache
from bauh_api.abstract.model import PackageStatus
from bauh_api.util.html import strip_html

from bauh.core import resource
from bauh.view.qt import dialog
from bauh.view.qt.view_model import PackageView, PackageViewStatus

INSTALL_BT_STYLE = 'background: {back}; color: white; font-size: 10px; font-weight: bold'


class IconButton(QWidget):

    def __init__(self, icon_path: str, action, background: str = None, align: int = Qt.AlignCenter, tooltip: str = None):
        super(IconButton, self).__init__()
        self.bt = QToolButton()
        self.bt.setIcon(QIcon(icon_path))
        self.bt.clicked.connect(action)

        if background:
            self.bt.setStyleSheet('QToolButton { color: white; background: ' + background + '}')

        if tooltip:
            self.bt.setToolTip(tooltip)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(align)
        layout.addWidget(self.bt)
        self.setLayout(layout)


class UpdateToggleButton(QWidget):

    def __init__(self, app_view: PackageView, root: QWidget, i18n: dict, checked: bool = True, clickable: bool = True):
        super(UpdateToggleButton, self).__init__()

        self.app_view = app_view
        self.root = root

        layout = QHBoxLayout()
        layout.setContentsMargins(2, 2, 2, 0)
        layout.setAlignment(Qt.AlignCenter)
        self.setLayout(layout)

        self.bt = QToolButton()
        self.bt.setCheckable(clickable)

        if clickable:
            self.bt.clicked.connect(self.change_state)

        self.bt.setIcon(QIcon(resource.get_path('img/app_update.svg')))
        self.bt.setStyleSheet('QToolButton { background: #20A435 } ' +
                              ('QToolButton:checked { background: gray }' if clickable else ''))
        layout.addWidget(self.bt)

        self.setToolTip(i18n['manage_window.apps_table.upgrade_toggle.tooltip'])

        if not checked:
            self.bt.click()

    def change_state(self, not_checked: bool):
        self.app_view.update_checked = not not_checked
        self.root.update_bt_upgrade()


class AppsTable(QTableWidget):

    def __init__(self, parent: QWidget, icon_cache: MemoryCache, disk_cache: bool, download_icons: bool):
        super(AppsTable, self).__init__()
        self.setParent(parent)
        self.window = parent
        self.disk_cache = disk_cache
        self.download_icons = download_icons
        self.column_names = ['' for _ in range(7)]
        self.setColumnCount(len(self.column_names))
        self.setFocusPolicy(Qt.NoFocus)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setVisible(False)
        self.setSelectionBehavior(QTableView.SelectRows)
        self.setHorizontalHeaderLabels(self.column_names)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.icon_flathub = QIcon(resource.get_path('img/flathub.svg'))
        self.icon_logo = QIcon(resource.get_path('img/logo.svg'))

        self.network_man = QNetworkAccessManager()
        self.network_man.finished.connect(self._load_icon_and_cache)

        self.icon_cache = icon_cache
        self.lock_async_data = Lock()
        self.setRowHeight(80, 80)
        self.cache_type_icon = {}
        self.i18n = self.window.i18n

    def has_any_settings(self, app_v: PackageView):
        return app_v.model.can_be_refreshed() or \
               app_v.model.has_history() or \
               app_v.model.can_be_downgraded()

    def show_pkg_settings(self, pkgv: PackageView):
        menu_row = QMenu()

        if pkgv.model.installed:
            if pkgv.model.can_be_refreshed():
                action_history = QAction(self.i18n["manage_window.apps_table.row.actions.refresh"])
                action_history.setIcon(QIcon(resource.get_path('img/refresh.svg')))

                def refresh():
                    self.window.refresh(pkgv)

                action_history.triggered.connect(refresh)
                menu_row.addAction(action_history)

            if pkgv.model.has_history():
                action_history = QAction(self.i18n["manage_window.apps_table.row.actions.history"])
                action_history.setIcon(QIcon(resource.get_path('img/history.svg')))

                def show_history():
                    self.window.get_app_history(pkgv)

                action_history.triggered.connect(show_history)
                menu_row.addAction(action_history)

            if pkgv.model.can_be_downgraded():
                action_downgrade = QAction(self.i18n["manage_window.apps_table.row.actions.downgrade"])

                def downgrade():
                    if dialog.ask_confirmation(
                            title=self.i18n['manage_window.apps_table.row.actions.downgrade'],
                            body=self._parag(self.i18n['manage_window.apps_table.row.actions.downgrade.popup.body'].format(self._bold(str(pkgv)))),
                            locale_keys=self.i18n):
                        self.window.downgrade(pkgv)

                action_downgrade.triggered.connect(downgrade)
                action_downgrade.setIcon(QIcon(resource.get_path('img/downgrade.svg')))
                menu_row.addAction(action_downgrade)

        menu_row.adjustSize()
        menu_row.popup(QCursor.pos())
        menu_row.exec_()

    def fill_async_data(self):
        if self.window.pkgs:

            for idx, app_v in enumerate(self.window.pkgs):

                if app_v.status == PackageViewStatus.LOADING and app_v.model.status == PackageStatus.READY:

                    if self.download_icons:
                        self.network_man.get(QNetworkRequest(QUrl(app_v.model.icon_url)))

                    app_name = self.item(idx, 0).text()

                    if not app_name or app_name == '...':
                        self.item(idx, 0).setText(app_v.model.name)

                    self._set_col_version(idx, app_v)
                    self._set_col_description(idx, app_v)
                    self._set_col_settings(idx, app_v)
                    app_v.status = PackageViewStatus.READY

            self.window.resize_and_center()

    def _uninstall_app(self, app_v: PackageView):
        if dialog.ask_confirmation(title=self.i18n['manage_window.apps_table.row.actions.uninstall.popup.title'],
                                   body=self._parag(self.i18n['manage_window.apps_table.row.actions.uninstall.popup.body'].format(self._bold(str(app_v)))),
                                   locale_keys=self.i18n):
            self.window.uninstall_app(app_v)

    def _bold(self, text: str) -> str:
        return '<span style="font-weight: bold">{}</span>'.format(text)

    def _parag(self, text: str) -> str:
        return '<p>{}</p>'.format(text)

    def _install_app(self, pkgv: PackageView):

        if dialog.ask_confirmation(
                title=self.i18n['manage_window.apps_table.row.actions.install.popup.title'],
                body=self._parag(self.i18n['manage_window.apps_table.row.actions.install.popup.body'].format(self._bold(str(pkgv)))),
                locale_keys=self.i18n):

            self.window.install(pkgv)

    def _load_icon_and_cache(self, http_response):
        icon_url = http_response.url().toString()

        icon_data = self.icon_cache.get(icon_url)
        icon_was_cached = True

        if not icon_data:
            icon_bytes = http_response.readAll()

            if not icon_bytes:
                return

            icon_was_cached = False
            pixmap = QPixmap()

            pixmap.loadFromData(icon_bytes)
            icon = QIcon(pixmap)
            icon_data = {'icon': icon, 'bytes': icon_bytes}
            self.icon_cache.add(icon_url, icon_data)

        for idx, app in enumerate(self.window.pkgs):
            if app.model.icon_url == icon_url:
                col_name = self.item(idx, 0)
                col_name.setIcon(icon_data['icon'])

                if self.disk_cache and app.model.supports_disk_cache():
                    if not icon_was_cached or not os.path.exists(app.model.get_disk_icon_path()):
                        self.window.manager.cache_to_disk(app=app.model, icon_bytes=icon_data['bytes'], only_icon=True)

    def update_pkgs(self, pkg_views: List[PackageView], update_check_enabled: bool = True):
        self.setRowCount(len(pkg_views) if pkg_views else 0)
        self.setEnabled(True)

        if pkg_views:
            for idx, pkgv in enumerate(pkg_views):
                self._set_col_name(idx, pkgv)
                self._set_col_version(idx, pkgv)
                self._set_col_description(idx, pkgv)
                self._set_col_type(idx, pkgv)
                self._set_col_installed(idx, pkgv)

                self._set_col_settings(idx, pkgv)

                col_update = None

                if update_check_enabled and pkgv.model.update:
                    col_update = UpdateToggleButton(pkgv, self.window, self.i18n, pkgv.model.update)

                self.setCellWidget(idx, 6, col_update)

    def _gen_row_button(self, text: str, style: str, callback) -> QWidget:
        col = QWidget()
        col_bt = QPushButton()
        col_bt.setText(text)
        col_bt.setStyleSheet('QPushButton { ' + style + '}')
        col_bt.clicked.connect(callback)

        layout = QHBoxLayout()
        layout.setContentsMargins(2, 2, 2, 0)
        layout.setAlignment(Qt.AlignCenter)
        layout.addWidget(col_bt)
        col.setLayout(layout)

        return col

    def _set_col_installed(self, idx: int, pkgv: PackageView):

        if pkgv.model.installed:
            if pkgv.model.can_be_uninstalled():
                def uninstall():
                    self._uninstall_app(pkgv)

                col = self._gen_row_button(self.i18n['uninstall'].capitalize(), INSTALL_BT_STYLE.format(back='#cc0000'), uninstall)
            else:
                col = QLabel()
                col.setPixmap((QPixmap(resource.get_path('img/checked.svg'))))
                col.setAlignment(Qt.AlignCenter)
                col.setToolTip(self.i18n['installed'])
        elif pkgv.model.can_be_installed():
            def install():
                self._install_app(pkgv)
            col = self._gen_row_button(self.i18n['install'].capitalize(), INSTALL_BT_STYLE.format(back='#088A08'), install)
        else:
            col = None

        self.setCellWidget(idx, 4, col)

    def _set_col_type(self, idx: int, app_v: PackageView):

        pixmap = self.cache_type_icon.get(app_v.model.get_type())

        if not pixmap:
            pixmap = QPixmap(app_v.model.get_type_icon_path())
            pixmap = pixmap.scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.cache_type_icon[app_v.model.get_type()] = pixmap

        col_type = QLabel()
        col_type.setPixmap(pixmap)
        col_type.setAlignment(Qt.AlignCenter)
        col_type.setToolTip('{}: {}'.format(self.i18n['type'], app_v.model.get_type()))
        self.setCellWidget(idx, 3, col_type)

    def _set_col_version(self, idx: int, app_v: PackageView):
        label_version = QLabel(app_v.model.version if app_v.model.version else '?')
        label_version.setAlignment(Qt.AlignCenter)

        col_version = QWidget()
        col_version.setLayout(QHBoxLayout())
        col_version.layout().addWidget(label_version)

        if app_v.model.version:
            tooltip = self.i18n['version.installed'] if app_v.model.installed else self.i18n['version']
        else:
            tooltip = self.i18n['version.unknown']

        if app_v.model.update:
            label_version.setStyleSheet("color: #20A435; font-weight: bold")
            tooltip = self.i18n['version.installed_outdated']

        if app_v.model.installed and app_v.model.version and app_v.model.latest_version and app_v.model.version < app_v.model.latest_version:
            tooltip = '{}. {}: {}'.format(tooltip, self.i18n['version.latest'], app_v.model.latest_version)
            label_version.setText(label_version.text() + '  >  {}'.format(app_v.model.latest_version))

        col_version.setToolTip(tooltip)
        self.setCellWidget(idx, 1, col_version)

    def _set_col_name(self, idx: int, app_v: PackageView):
        col = QTableWidgetItem()
        col.setText(app_v.model.name if app_v.model.name else '...')
        col.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        col.setToolTip(self.i18n['app.name'].lower())

        if self.disk_cache and app_v.model.supports_disk_cache() and app_v.model.get_disk_icon_path() and os.path.exists(app_v.model.get_disk_icon_path()):
            with open(app_v.model.get_disk_icon_path(), 'rb') as f:
                icon_bytes = f.read()
                pixmap = QPixmap()
                pixmap.loadFromData(icon_bytes)
                icon = QIcon(pixmap)
                self.icon_cache.add_non_existing(app_v.model.icon_url, {'icon': icon, 'bytes': icon_bytes})

        elif not app_v.model.icon_url:
            icon = QIcon(app_v.model.get_default_icon_path())
        else:
            icon_data = self.icon_cache.get(app_v.model.icon_url)
            icon = icon_data['icon'] if icon_data else QIcon(app_v.model.get_default_icon_path())

        col.setIcon(icon)
        self.setItem(idx, 0, col)

    def _set_col_description(self, idx: int, app_v: PackageView):
        col = QTableWidgetItem()
        col.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

        if app_v.model.description is not None or not app_v.model.is_application() or app_v.model.status == PackageStatus.READY:
            desc = app_v.model.description
        else:
            desc = '...'

        if desc and desc != '...':
            desc = strip_html(desc[0:25]) + '...'

        col.setText(desc)

        if app_v.model.description:
            col.setToolTip(app_v.model.description)

        self.setItem(idx, 2, col)

    def _set_col_settings(self, idx: int, app_v: PackageView):
        tb = QToolBar()

        if app_v.model.can_be_run() and app_v.model.get_command():

            def run():
                self.window.run_app(app_v)

            tb.addWidget(IconButton(icon_path=resource.get_path('img/app_play.png'), action=run, background='#088A08', tooltip=self.i18n['action.run.tooltip']))

        if app_v.model.has_info():

            def get_info():
                self.window.get_app_info(app_v)

            tb.addWidget(IconButton(icon_path=resource.get_path('img/app_info.svg'), action=get_info, background='#2E68D3'))

        def handle_click():
            self.show_pkg_settings(app_v)

        if self.has_any_settings(app_v):
            bt = IconButton(icon_path=resource.get_path('img/app_settings.svg'), action=handle_click, background='#12ABAB')
            tb.addWidget(bt)

        self.setCellWidget(idx, 5, tb)

    def change_headers_policy(self, policy: QHeaderView = QHeaderView.ResizeToContents):
        header_horizontal = self.horizontalHeader()
        for i in range(self.columnCount()):
            header_horizontal.setSectionResizeMode(i, policy)
