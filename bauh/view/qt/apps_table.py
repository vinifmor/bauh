import operator
import os
from functools import reduce
from threading import Lock
from typing import List

from PyQt5.QtCore import Qt, QUrl, QSize
from PyQt5.QtGui import QPixmap, QIcon, QCursor
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PyQt5.QtWidgets import QTableWidget, QTableView, QMenu, QAction, QTableWidgetItem, QToolButton, QWidget, \
    QHeaderView, QLabel, QHBoxLayout, QToolBar, QSizePolicy

from bauh.api.abstract.cache import MemoryCache
from bauh.api.abstract.model import PackageStatus
from bauh.commons.html import strip_html
from bauh.view.qt import dialog
from bauh.view.qt.components import IconButton
from bauh.view.qt.view_model import PackageView
from bauh.view.util import resource
from bauh.view.util.translation import I18n

INSTALL_BT_STYLE = 'background: {back}; color: white; font-size: 10px; font-weight: bold'

NAME_MAX_SIZE = 30
DESC_MAX_SIZE = 40
PUBLISHER_MAX_SIZE = 25


class UpdateToggleButton(QWidget):

    def __init__(self, pkg: PackageView, root: QWidget, i18n: I18n, checked: bool = True, clickable: bool = True):
        super(UpdateToggleButton, self).__init__()
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.app_view = pkg
        self.root = root

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)
        self.setLayout(layout)

        self.bt = QToolButton()
        self.bt.setCheckable(True)
        self.bt.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)

        if clickable:
            self.bt.clicked.connect(self.change_state)

        self.bt.setStyleSheet('QToolButton { background: #20A435 } ' +
                              'QToolButton:checked { background: gray } ' +
                              ('QToolButton:disabled { background: #d69003 }' if not clickable and not checked else ''))

        layout.addWidget(self.bt)

        if not checked:
            self.bt.click()

        if clickable:
            self.bt.setIcon(QIcon(resource.get_path('img/app_update.svg')))
            self.setToolTip('{} {}'.format(i18n['manage_window.apps_table.upgrade_toggle.tooltip'],
                                           i18n['manage_window.apps_table.upgrade_toggle.enabled.tooltip']))
        else:
            if not checked:
                self.bt.setIcon(QIcon(resource.get_path('img/exclamation.svg')))
                self.bt.setEnabled(False)

                tooltip = i18n['{}.update.disabled.tooltip'.format(pkg.model.gem_name)]

                if tooltip:
                    self.setToolTip(tooltip)
                else:
                    self.setToolTip('{} {}'.format(i18n['manage_window.apps_table.upgrade_toggle.tooltip'],
                                                   i18n['manage_window.apps_table.upgrade_toggle.disabled.tooltip']))
            else:
                self.bt.setIcon(QIcon(resource.get_path('img/app_update.svg')))
                self.bt.setCheckable(False)

    def change_state(self, not_checked: bool):
        self.app_view.update_checked = not not_checked
        self.root.update_bt_upgrade()


class AppsTable(QTableWidget):

    COL_NUMBER = 8

    def __init__(self, parent: QWidget, icon_cache: MemoryCache, download_icons: bool):
        super(AppsTable, self).__init__()
        self.setParent(parent)
        self.window = parent
        self.download_icons = download_icons
        self.setColumnCount(self.COL_NUMBER)
        self.setFocusPolicy(Qt.NoFocus)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setVisible(False)
        self.horizontalHeader().setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        self.setSelectionBehavior(QTableView.SelectRows)
        self.setHorizontalHeaderLabels(['' for _ in range(self.columnCount())])
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        self.icon_logo = QIcon(resource.get_path('img/logo.svg'))
        self.pixmap_verified = QIcon(resource.get_path('img/verified.svg')).pixmap(QSize(10, 10))

        self.network_man = QNetworkAccessManager()
        self.network_man.finished.connect(self._load_icon_and_cache)

        self.icon_cache = icon_cache
        self.lock_async_data = Lock()
        self.setRowHeight(80, 80)
        self.cache_type_icon = {}
        self.i18n = self.window.i18n

    def has_any_settings(self, pkg: PackageView):
        return pkg.model.has_history() or \
               pkg.model.can_be_downgraded() or \
               bool(pkg.model.get_custom_supported_actions())

    def show_pkg_settings(self, pkg: PackageView):
        menu_row = QMenu()

        if pkg.model.installed:
            if pkg.model.has_history():
                action_history = QAction(self.i18n["manage_window.apps_table.row.actions.history"])
                action_history.setIcon(QIcon(resource.get_path('img/history.svg')))

                def show_history():
                    self.window.get_app_history(pkg)

                action_history.triggered.connect(show_history)
                menu_row.addAction(action_history)

            if pkg.model.can_be_downgraded():
                action_downgrade = QAction(self.i18n["manage_window.apps_table.row.actions.downgrade"])

                def downgrade():
                    if dialog.ask_confirmation(
                            title=self.i18n['manage_window.apps_table.row.actions.downgrade'],
                            body=self._parag(self.i18n['manage_window.apps_table.row.actions.downgrade.popup.body'].format(self._bold(str(pkg)))),
                            i18n=self.i18n):
                        self.window.downgrade(pkg)

                action_downgrade.triggered.connect(downgrade)
                action_downgrade.setIcon(QIcon(resource.get_path('img/downgrade.svg')))
                menu_row.addAction(action_downgrade)

        if bool(pkg.model.get_custom_supported_actions()):
            for action in pkg.model.get_custom_supported_actions():
                item = QAction(self.i18n[action.i18_label_key])

                if action.icon_path:
                    item.setIcon(QIcon(action.icon_path))

                def custom_action():
                    if dialog.ask_confirmation(
                            title=self.i18n[action.i18_label_key],
                            body=self._parag('{} {} ?'.format(self.i18n[action.i18_label_key], self._bold(str(pkg)))),
                            i18n=self.i18n):
                        self.window.execute_custom_action(pkg, action)

                item.triggered.connect(custom_action)
                menu_row.addAction(item)

        menu_row.adjustSize()
        menu_row.popup(QCursor.pos())
        menu_row.exec_()

    def refresh(self, pkg: PackageView):
        self._update_row(pkg, update_check_enabled=False, change_update_col=False)

    def update_package(self, pkg: PackageView):
        if self.download_icons and pkg.model.icon_url:
            icon_request = QNetworkRequest(QUrl(pkg.model.icon_url))
            icon_request.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
            self.network_man.get(icon_request)

        self._update_row(pkg, change_update_col=False)

    def _uninstall_app(self, app_v: PackageView):
        if dialog.ask_confirmation(title=self.i18n['manage_window.apps_table.row.actions.uninstall.popup.title'],
                                   body=self._parag(self.i18n['manage_window.apps_table.row.actions.uninstall.popup.body'].format(self._bold(str(app_v)))),
                                   i18n=self.i18n):
            self.window.uninstall_app(app_v)

    def _bold(self, text: str) -> str:
        return '<span style="font-weight: bold">{}</span>'.format(text)

    def _parag(self, text: str) -> str:
        return '<p>{}</p>'.format(text)

    def _install_app(self, pkgv: PackageView):

        body = self.i18n['manage_window.apps_table.row.actions.install.popup.body'].format(self._bold(str(pkgv)))

        warning = self.i18n.get('gem.{}.install.warning'.format(pkgv.model.get_type().lower()))

        if warning:
            body += '<br/><br/> {}'.format('<br/>'.join(('{}.'.format(phrase) for phrase in warning.split('.') if phrase)))

        if dialog.ask_confirmation(
                title=self.i18n['manage_window.apps_table.row.actions.install.popup.title'],
                body=self._parag(body),
                i18n=self.i18n):

            self.window.install(pkgv)

    def _load_icon_and_cache(self, http_response: QNetworkReply):
        icon_url = http_response.request().url().toString()

        icon_data = self.icon_cache.get(icon_url)
        icon_was_cached = True

        if not icon_data:
            icon_bytes = http_response.readAll()

            if not icon_bytes:
                return

            icon_was_cached = False
            pixmap = QPixmap()
            pixmap.loadFromData(icon_bytes)

            if not pixmap.isNull():
                icon = QIcon(pixmap)
                icon_data = {'icon': icon, 'bytes': icon_bytes}
                self.icon_cache.add(icon_url, icon_data)

        if icon_data:
            for idx, app in enumerate(self.window.pkgs):
                if app.model.icon_url == icon_url:
                    col_name = self.item(idx, 0)
                    col_name.setIcon(icon_data['icon'])

                    if app.model.supports_disk_cache() and app.model.get_disk_icon_path():
                        if not icon_was_cached or not os.path.exists(app.model.get_disk_icon_path()):
                            self.window.manager.cache_to_disk(pkg=app.model, icon_bytes=icon_data['bytes'], only_icon=True)

    def update_packages(self, pkgs: List[PackageView], update_check_enabled: bool = True):
        self.setRowCount(len(pkgs) if pkgs else 0)
        self.setEnabled(True)

        if pkgs:
            for idx, pkg in enumerate(pkgs):
                pkg.table_index = idx

                if self.download_icons and pkg.model.status == PackageStatus.READY and pkg.model.icon_url:
                    icon_request = QNetworkRequest(QUrl(pkg.model.icon_url))
                    icon_request.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
                    self.network_man.get(icon_request)

                self._update_row(pkg, update_check_enabled)

    def _update_row(self, pkg: PackageView, update_check_enabled: bool = True, change_update_col: bool = True):
        self._set_col_name(0, pkg)
        self._set_col_version(1, pkg)
        self._set_col_description(2, pkg)
        self._set_col_publisher(3, pkg)
        self._set_col_type(4, pkg)
        self._set_col_installed(5, pkg)
        self._set_col_settings(6, pkg)

        if change_update_col:
            col_update = None

            if update_check_enabled and pkg.model.update:
                col_update = QToolBar()
                col_update.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
                col_update.addWidget(UpdateToggleButton(pkg=pkg,
                                                        root=self.window,
                                                        i18n=self.i18n,
                                                        checked=pkg.update_checked if pkg.model.can_be_updated() else False,
                                                        clickable=pkg.model.can_be_updated()))

            self.setCellWidget(pkg.table_index, 7, col_update)

    def _gen_row_button(self, text: str, style: str, callback) -> QWidget:
        col = QWidget()
        col.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        col_bt = QToolButton()
        col_bt.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        col_bt.setText(text)
        col_bt.setStyleSheet('QToolButton { ' + style + '}')
        col_bt.setMinimumWidth(80)
        col_bt.clicked.connect(callback)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)

        layout.addWidget(col_bt)

        col.setLayout(layout)
        return col

    def _set_col_installed(self, col: int, pkg: PackageView):
        toolbar = QToolBar()
        toolbar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)

        if pkg.model.installed:
            if pkg.model.can_be_uninstalled():
                def uninstall():
                    self._uninstall_app(pkg)

                item = self._gen_row_button(self.i18n['uninstall'].capitalize(), INSTALL_BT_STYLE.format(back='#cc0000'), uninstall)
            else:
                item = QLabel()
                item.setPixmap((QPixmap(resource.get_path('img/checked.svg'))))
                item.setAlignment(Qt.AlignCenter)
                item.setToolTip(self.i18n['installed'])
        elif pkg.model.can_be_installed():
            def install():
                self._install_app(pkg)

            item = self._gen_row_button(self.i18n['install'].capitalize(), INSTALL_BT_STYLE.format(back='#088A08'), install)
        else:
            item = None

        toolbar.addWidget(item)
        self.setCellWidget(pkg.table_index, col, toolbar)

    def _set_col_type(self, col: int, pkg: PackageView):
        icon_data = self.cache_type_icon.get(pkg.model.get_type())

        if icon_data is None:
            pixmap = QIcon(pkg.model.get_type_icon_path()).pixmap(QSize(16, 16))
            icon_data = {'px': pixmap, 'tip': '{}: {}'.format(self.i18n['type'], pkg.get_type_label())}
            self.cache_type_icon[pkg.model.get_type()] = icon_data

        item = QLabel()
        item.setPixmap(icon_data['px'])
        item.setAlignment(Qt.AlignCenter)

        item.setToolTip(icon_data['tip'])
        self.setCellWidget(pkg.table_index, col, item)

    def _set_col_version(self, col: int, pkg: PackageView):
        label_version = QLabel(str(pkg.model.version if pkg.model.version else '?'))
        label_version.setMinimumWidth(100)
        label_version.setAlignment(Qt.AlignCenter)

        item = QWidget()
        item.setLayout(QHBoxLayout())
        item.layout().addWidget(label_version)

        if pkg.model.version:
            tooltip = self.i18n['version.installed'] if pkg.model.installed else self.i18n['version']
        else:
            tooltip = self.i18n['version.unknown']

        if pkg.model.update:
            label_version.setStyleSheet("color: #20A435; font-weight: bold")
            tooltip = self.i18n['version.installed_outdated']

        if pkg.model.installed and pkg.model.update and pkg.model.version and pkg.model.latest_version and pkg.model.version != pkg.model.latest_version:
            tooltip = '{}. {}: {}'.format(tooltip, self.i18n['version.latest'], pkg.model.latest_version)
            label_version.setText(label_version.text() + '  >  {}'.format(pkg.model.latest_version))

        item.setToolTip(tooltip)
        self.setCellWidget(pkg.table_index, col, item)

    def _set_col_name(self, col: int, pkg: PackageView):
        item = QTableWidgetItem()
        item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

        name = pkg.model.get_display_name()
        if name:
            item.setToolTip('{}: {}'.format(self.i18n['app.name'].lower(), pkg.model.get_name_tooltip()))
        else:
            name = '...'
            item.setToolTip(self.i18n['app.name'].lower())

        if len(name) > NAME_MAX_SIZE:
            name = name[0:NAME_MAX_SIZE - 3] + '...'

        if len(name) < NAME_MAX_SIZE:
            name = name + ' ' * (NAME_MAX_SIZE-len(name))

        item.setText(name)

        icon_path = pkg.model.get_disk_icon_path()
        if pkg.model.supports_disk_cache() and icon_path and os.path.isfile(icon_path):
            with open(icon_path, 'rb') as f:
                icon_bytes = f.read()
                pixmap = QPixmap()
                pixmap.loadFromData(icon_bytes)
                icon = QIcon(pixmap)
                self.icon_cache.add_non_existing(pkg.model.icon_url, {'icon': icon, 'bytes': icon_bytes})

        elif not pkg.model.icon_url:
            icon = QIcon(pkg.model.get_default_icon_path())
        else:
            icon_data = self.icon_cache.get(pkg.model.icon_url)
            icon = icon_data['icon'] if icon_data else QIcon(pkg.model.get_default_icon_path())

        item.setIcon(icon)
        self.setItem(pkg.table_index, col, item)

    def _set_col_description(self, col: int, pkg: PackageView):
        item = QLabel()
        item.setMinimumWidth(300)

        if pkg.model.description is not None or not pkg.model.is_application() or pkg.model.status == PackageStatus.READY:
            desc = pkg.model.description.split('\n')[0] if pkg.model.description else pkg.model.description
        else:
            desc = '...'

        if desc and desc != '...' and len(desc) > DESC_MAX_SIZE:
            desc = strip_html(desc[0: DESC_MAX_SIZE - 1]) + '...'

        item.setText(desc)

        if pkg.model.description:
            item.setToolTip(pkg.model.description)

        self.setCellWidget(pkg.table_index, col, item)

    def _set_col_publisher(self, col: int, pkg: PackageView):
        item = QToolBar()

        publisher = pkg.model.get_publisher()
        full_publisher = None

        if publisher:
            publisher = publisher.strip()
            full_publisher = publisher

            if len(publisher) > PUBLISHER_MAX_SIZE:
                publisher = full_publisher[0: PUBLISHER_MAX_SIZE - 3] + '...'

        if not publisher:
            if not pkg.model.installed:
                item.setStyleSheet('QLabel { color: red; }')

            publisher = self.i18n['unknown']

        lb_name = QLabel('  {}'.format(publisher))
        item.addWidget(lb_name)

        if publisher and full_publisher:
            lb_name.setToolTip(self.i18n['publisher'].capitalize() + ((': ' + full_publisher) if full_publisher else ''))

            if pkg.model.is_trustable():
                lb_verified = QLabel()
                lb_verified.setPixmap(self.pixmap_verified)
                lb_verified.setToolTip(self.i18n['publisher.verified'].capitalize())
                item.addWidget(lb_verified)
            else:
                lb_name.setText(lb_name.text() + "   ")

        self.setCellWidget(pkg.table_index, col, item)

    def _set_col_settings(self, col: int, pkg: PackageView):
        item = QToolBar()
        item.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)

        if pkg.model.installed:
            def run():
                self.window.run_app(pkg)

            bt = IconButton(QIcon(resource.get_path('img/app_play.svg')), i18n=self.i18n, action=run, background='#088A08', tooltip=self.i18n['action.run.tooltip'])
            bt.setEnabled(pkg.model.can_be_run())
            item.addWidget(bt)

        def get_info():
            self.window.get_app_info(pkg)

        bt = IconButton(QIcon(resource.get_path('img/app_info.svg')), i18n=self.i18n, action=get_info, background='#2E68D3', tooltip=self.i18n['action.info.tooltip'])
        bt.setEnabled(bool(pkg.model.has_info()))
        item.addWidget(bt)

        if not pkg.model.installed:
            def get_screenshots():
                self.window.get_screenshots(pkg)

            bt = IconButton(QIcon(resource.get_path('img/camera.svg')), i18n=self.i18n, action=get_screenshots, background='purple', tooltip=self.i18n['action.screenshots.tooltip'])
            bt.setEnabled(bool(pkg.model.has_screenshots()))
            item.addWidget(bt)

        def handle_click():
            self.show_pkg_settings(pkg)

        settings = self.has_any_settings(pkg)
        if pkg.model.installed:
            bt = IconButton(QIcon(resource.get_path('img/app_settings.svg')), i18n=self.i18n, action=handle_click, background='#12ABAB', tooltip=self.i18n['action.settings.tooltip'])
            bt.setEnabled(bool(settings))
            item.addWidget(bt)

        self.setCellWidget(pkg.table_index, col, item)

    def change_headers_policy(self, policy: QHeaderView = QHeaderView.ResizeToContents):
        header_horizontal = self.horizontalHeader()
        for i in range(self.columnCount()):
            header_horizontal.setSectionResizeMode(i, policy)

    def get_width(self):
        return reduce(operator.add, [self.columnWidth(i) for i in range(self.columnCount())])
