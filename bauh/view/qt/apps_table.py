import operator
import os
from functools import reduce
from threading import Lock
from typing import List, Optional

from PyQt5.QtCore import Qt, QUrl, QSize
from PyQt5.QtGui import QPixmap, QIcon, QCursor
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PyQt5.QtWidgets import QTableWidget, QTableView, QMenu, QToolButton, QWidget, \
    QHeaderView, QLabel, QHBoxLayout, QToolBar, QSizePolicy

from bauh.api.abstract.cache import MemoryCache
from bauh.api.abstract.model import PackageStatus, CustomSoftwareAction
from bauh.commons.html import strip_html, bold
from bauh.view.qt.components import IconButton, QCustomMenuAction, QCustomToolbar
from bauh.view.qt.dialog import ConfirmationDialog
from bauh.view.qt.view_model import PackageView
from bauh.view.util.translation import I18n

NAME_MAX_SIZE = 30
DESC_MAX_SIZE = 40
PUBLISHER_MAX_SIZE = 25


class UpgradeToggleButton(QToolButton):

    def __init__(self, pkg: Optional[PackageView], root: QWidget, i18n: I18n, checked: bool = True,
                 clickable: bool = True):
        super(UpgradeToggleButton, self).__init__()
        self.app_view = pkg
        self.root = root

        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setCheckable(True)

        if clickable:
            self.clicked.connect(self.change_state)

        if not clickable and not checked:
            self.setProperty('enabled', 'false')

        if not checked:
            self.click()

        if clickable:
            self.setToolTip('{} {}'.format(i18n['manage_window.apps_table.upgrade_toggle.tooltip'],
                                           i18n['manage_window.apps_table.upgrade_toggle.enabled.tooltip']))
        else:
            if not checked:
                self.setEnabled(False)

                tooltip = i18n['{}.update.disabled.tooltip'.format(pkg.model.gem_name)]

                if tooltip:
                    self.setToolTip(tooltip)
                else:
                    self.setToolTip('{} {}'.format(i18n['manage_window.apps_table.upgrade_toggle.tooltip'],
                                                   i18n['manage_window.apps_table.upgrade_toggle.disabled.tooltip']))
            else:
                self.setCheckable(False)

    def change_state(self, not_checked: bool):
        self.app_view.update_checked = not not_checked
        self.setProperty('toggled', str(self.app_view.update_checked).lower())
        self.root.update_bt_upgrade()
        self.style().unpolish(self)
        self.style().polish(self)


class PackagesTable(QTableWidget):
    COL_NUMBER = 9
    DEFAULT_ICON_SIZE = QSize(16, 16)

    def __init__(self, parent: QWidget, icon_cache: MemoryCache, download_icons: bool):
        super(PackagesTable, self).__init__()
        self.setObjectName('table_packages')
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
        self.horizontalScrollBar().setCursor(QCursor(Qt.PointingHandCursor))
        self.verticalScrollBar().setCursor(QCursor(Qt.PointingHandCursor))

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
               pkg.model.supports_ignored_updates() or \
               bool(pkg.model.get_custom_supported_actions())

    def show_pkg_actions(self, pkg: PackageView):
        menu_row = QMenu()
        menu_row.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        menu_row.setObjectName('app_actions')
        menu_row.setCursor(QCursor(Qt.PointingHandCursor))

        if pkg.model.installed:

            if pkg.model.has_history():
                def show_history():
                    self.window.begin_show_history(pkg)

                menu_row.addAction(QCustomMenuAction(parent=menu_row,
                                                     label=self.i18n["manage_window.apps_table.row.actions.history"],
                                                     action=show_history,
                                                     button_name='app_history'))

            if pkg.model.can_be_downgraded():

                def downgrade():
                    if ConfirmationDialog(title=self.i18n['manage_window.apps_table.row.actions.downgrade'],
                                          body=self._parag(self.i18n[
                                                               'manage_window.apps_table.row.actions.downgrade.popup.body'].format(
                                              self._bold(str(pkg)))),
                                          i18n=self.i18n).ask():
                        self.window.begin_downgrade(pkg)

                menu_row.addAction(QCustomMenuAction(parent=menu_row,
                                                     label=self.i18n["manage_window.apps_table.row.actions.downgrade"],
                                                     action=downgrade,
                                                     button_name='app_downgrade'))

            if pkg.model.supports_ignored_updates():
                if pkg.model.is_update_ignored():
                    action_label = self.i18n["manage_window.apps_table.row.actions.ignore_updates_reverse"]
                    button_name = 'revert_ignore_updates'
                else:
                    action_label = self.i18n["manage_window.apps_table.row.actions.ignore_updates"]
                    button_name = 'ignore_updates'

                def ignore_updates():
                    self.window.begin_ignore_updates(pkg)

                menu_row.addAction(QCustomMenuAction(parent=menu_row,
                                                     label=action_label,
                                                     button_name=button_name,
                                                     action=ignore_updates))

        if bool(pkg.model.get_custom_supported_actions()):
            actions = [self._map_custom_action(pkg, a, menu_row) for a in pkg.model.get_custom_supported_actions()]
            menu_row.addActions(actions)

        menu_row.adjustSize()
        menu_row.popup(QCursor.pos())
        menu_row.exec_()

    def _map_custom_action(self, pkg: PackageView, action: CustomSoftwareAction, parent: QWidget) -> QCustomMenuAction:
        def custom_action():
            if action.i18n_confirm_key:
                body = self.i18n[action.i18n_confirm_key].format(bold(pkg.model.name))
            else:
                body = '{} ?'.format(self.i18n[action.i18n_label_key])

            if ConfirmationDialog(icon=QIcon(pkg.model.get_type_icon_path()),
                                  title=self.i18n[action.i18n_label_key],
                                  body=self._parag(body),
                                  i18n=self.i18n).ask():
                self.window.begin_execute_custom_action(pkg, action)

        return QCustomMenuAction(parent=parent,
                                 label=self.i18n[action.i18n_label_key],
                                 icon=QIcon(action.icon_path) if action.icon_path else None,
                                 action=custom_action)

    def refresh(self, pkg: PackageView):
        self._update_row(pkg, update_check_enabled=False, change_update_col=False)

    def update_package(self, pkg: PackageView, change_update_col: bool = False):
        if self.download_icons and pkg.model.icon_url:
            icon_request = QNetworkRequest(QUrl(pkg.model.icon_url))
            icon_request.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
            self.network_man.get(icon_request)

        self._update_row(pkg, change_update_col=change_update_col)

    def _uninstall(self, pkg: PackageView):
        if ConfirmationDialog(title=self.i18n['manage_window.apps_table.row.actions.uninstall.popup.title'],
                              body=self._parag(
                                  self.i18n['manage_window.apps_table.row.actions.uninstall.popup.body'].format(
                                      self._bold(str(pkg)))),
                              i18n=self.i18n).ask():
            self.window.begin_uninstall(pkg)

    def _bold(self, text: str) -> str:
        return '<span style="font-weight: bold">{}</span>'.format(text)

    def _parag(self, text: str) -> str:
        return '<p>{}</p>'.format(text)

    def _install_app(self, pkgv: PackageView):

        body = self.i18n['manage_window.apps_table.row.actions.install.popup.body'].format(self._bold(str(pkgv)))

        warning = self.i18n.get('gem.{}.install.warning'.format(pkgv.model.get_type().lower()))

        if warning:
            body += '<br/><br/> {}'.format(
                '<br/>'.join(('{}.'.format(phrase) for phrase in warning.split('.') if phrase)))

        if ConfirmationDialog(title=self.i18n['manage_window.apps_table.row.actions.install.popup.title'],
                              body=self._parag(body),
                              i18n=self.i18n).ask():
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
                    self._update_icon(self.cellWidget(idx, 0), icon_data['icon'])

                    if app.model.supports_disk_cache() and app.model.get_disk_icon_path() and icon_data['bytes']:
                        if not icon_was_cached or not os.path.exists(app.model.get_disk_icon_path()):
                            self.window.manager.cache_to_disk(pkg=app.model, icon_bytes=icon_data['bytes'],
                                                              only_icon=True)

    def update_packages(self, pkgs: List[PackageView], update_check_enabled: bool = True):
        self.setRowCount(0)  # removes the overwrite effect when updates the table
        self.setEnabled(True)

        if pkgs:
            self.setColumnCount(self.COL_NUMBER if update_check_enabled else self.COL_NUMBER - 1)
            self.setRowCount(len(pkgs))

            for idx, pkg in enumerate(pkgs):
                pkg.table_index = idx

                if self.download_icons and pkg.model.status == PackageStatus.READY and pkg.model.icon_url:
                    icon_request = QNetworkRequest(QUrl(pkg.model.icon_url))
                    icon_request.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
                    self.network_man.get(icon_request)

                self._update_row(pkg, update_check_enabled)

            self.scrollToTop()

    def _update_row(self, pkg: PackageView, update_check_enabled: bool = True, change_update_col: bool = True):
        self._set_col_icon(0, pkg)
        self._set_col_name(1, pkg)
        self._set_col_version(2, pkg)
        self._set_col_description(3, pkg)
        self._set_col_publisher(4, pkg)
        self._set_col_type(5, pkg)
        self._set_col_installed(6, pkg)
        self._set_col_actions(7, pkg)

        if change_update_col and update_check_enabled:
            if pkg.model.installed and not pkg.model.is_update_ignored() and pkg.model.update:
                col_update = QCustomToolbar()
                col_update.add_space()
                col_update.add_widget(UpgradeToggleButton(pkg=pkg,
                                                          root=self.window,
                                                          i18n=self.i18n,
                                                          checked=pkg.update_checked if pkg.model.can_be_updated() else False,
                                                          clickable=pkg.model.can_be_updated()))
                col_update.add_space()
            else:
                col_update = QLabel()

            self.setCellWidget(pkg.table_index, 8, col_update)

    def _gen_row_button(self, text: str, name: str, callback, tip: Optional[str] = None) -> QToolButton:
        col_bt = QToolButton()
        col_bt.setProperty('text_only', 'true')
        col_bt.setObjectName(name)
        col_bt.setCursor(QCursor(Qt.PointingHandCursor))
        col_bt.setText(text)
        col_bt.clicked.connect(callback)

        if tip:
            col_bt.setToolTip(tip)

        return col_bt

    def _set_col_installed(self, col: int, pkg: PackageView):
        toolbar = QCustomToolbar()
        toolbar.add_space()

        if pkg.model.installed:
            if pkg.model.can_be_uninstalled():
                def uninstall():
                    self._uninstall(pkg)

                item = self._gen_row_button(text=self.i18n['uninstall'].capitalize(),
                                            name='bt_uninstall',
                                            callback=uninstall,
                                            tip=self.i18n['manage_window.bt_uninstall.tip'])
            else:
                item = None

        elif pkg.model.can_be_installed():
            def install():
                self._install_app(pkg)

            item = self._gen_row_button(text=self.i18n['install'].capitalize(),
                                        name='bt_install',
                                        callback=install,
                                        tip=self.i18n['manage_window.bt_install.tip'])
        else:
            item = None

        toolbar.add_widget(item)
        toolbar.add_space()
        self.setCellWidget(pkg.table_index, col, toolbar)

    def _set_col_type(self, col: int, pkg: PackageView):
        icon_data = self.cache_type_icon.get(pkg.model.get_type())

        if icon_data is None:
            icon = QIcon(pkg.model.get_type_icon_path())
            pixmap = icon.pixmap(self._get_icon_size(icon))
            icon_data = {'px': pixmap, 'tip': '{}: {}'.format(self.i18n['type'], pkg.get_type_label())}
            self.cache_type_icon[pkg.model.get_type()] = icon_data

        col_type_icon = QLabel()
        col_type_icon.setCursor(QCursor(Qt.WhatsThisCursor))
        col_type_icon.setProperty('icon', 'true')
        col_type_icon.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        col_type_icon.setPixmap(icon_data['px'])
        col_type_icon.setToolTip(icon_data['tip'])
        self.setCellWidget(pkg.table_index, col, col_type_icon)

    def _set_col_version(self, col: int, pkg: PackageView):
        label_version = QLabel(str(pkg.model.version if pkg.model.version else '?'))
        label_version.setObjectName('app_version')
        label_version.setAlignment(Qt.AlignCenter)

        item = QWidget()
        item.setProperty('container', 'true')
        item.setCursor(QCursor(Qt.WhatsThisCursor))
        item.setLayout(QHBoxLayout())
        item.layout().addWidget(label_version)

        if pkg.model.version:
            tooltip = self.i18n['version.installed'] if pkg.model.installed else self.i18n['version']
        else:
            tooltip = self.i18n['version.unknown']

        if pkg.model.update and not pkg.model.is_update_ignored():
            label_version.setProperty('update', 'true')
            tooltip = pkg.model.get_update_tip() or self.i18n['version.installed_outdated']

        if pkg.model.is_update_ignored():
            label_version.setProperty('ignored', 'true')
            tooltip = self.i18n['version.updates_ignored']

        if pkg.model.installed and pkg.model.update and not pkg.model.is_update_ignored() and pkg.model.version and pkg.model.latest_version and pkg.model.version != pkg.model.latest_version:
            tooltip = '{}. {}: {}'.format(tooltip, self.i18n['version.latest'], pkg.model.latest_version)
            label_version.setText(label_version.text() + '  >  {}'.format(pkg.model.latest_version))

        item.setToolTip(tooltip)
        self.setCellWidget(pkg.table_index, col, item)

    def _set_col_icon(self, col: int, pkg: PackageView):
        icon_path = pkg.model.get_disk_icon_path()
        if pkg.model.installed and pkg.model.supports_disk_cache() and icon_path:
            if icon_path.startswith('/'):
                if os.path.isfile(icon_path):
                    with open(icon_path, 'rb') as f:
                        icon_bytes = f.read()
                        pixmap = QPixmap()
                        pixmap.loadFromData(icon_bytes)
                        icon = QIcon(pixmap)
                        self.icon_cache.add_non_existing(pkg.model.icon_url, {'icon': icon, 'bytes': icon_bytes})
                else:
                    icon = QIcon(pkg.model.get_default_icon_path())
            else:
                try:
                    icon = QIcon.fromTheme(icon_path)

                    if icon.isNull():
                        icon = QIcon(pkg.model.get_default_icon_path())
                    else:
                        self.icon_cache.add_non_existing(pkg.model.icon_url, {'icon': icon, 'bytes': None})

                except:
                    icon = QIcon(pkg.model.get_default_icon_path())

        elif not pkg.model.icon_url:
            icon = QIcon(pkg.model.get_default_icon_path())
        else:
            icon_data = self.icon_cache.get(pkg.model.icon_url)
            icon = icon_data['icon'] if icon_data else QIcon(pkg.model.get_default_icon_path())

        col_icon = QLabel()
        col_icon.setProperty('icon', 'true')
        col_icon.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        self._update_icon(col_icon, icon)
        self.setCellWidget(pkg.table_index, col, col_icon)

    def _set_col_name(self, col: int, pkg: PackageView):
        col_name = QLabel()
        col_name.setObjectName('app_name')
        col_name.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        col_name.setCursor(QCursor(Qt.WhatsThisCursor))

        name = pkg.model.get_display_name()
        if name:
            col_name.setToolTip('{}: {}'.format(self.i18n['app.name'].lower(), pkg.model.get_name_tooltip()))
        else:
            name = '...'
            col_name.setToolTip(self.i18n['app.name'].lower())

        if len(name) > NAME_MAX_SIZE:
            name = name[0:NAME_MAX_SIZE - 3] + '...'

        if len(name) < NAME_MAX_SIZE:
            name = name + ' ' * (NAME_MAX_SIZE - len(name))

        col_name.setText(name)
        self.setCellWidget(pkg.table_index, col, col_name)

    def _update_icon(self, label: QLabel, icon: QIcon):
        label.setPixmap(icon.pixmap(self._get_icon_size(icon)))

    def _get_icon_size(self, icon: QIcon) -> QSize:
        sizes = icon.availableSizes()
        return sizes[-1] if sizes else self.DEFAULT_ICON_SIZE

    def _set_col_description(self, col: int, pkg: PackageView):
        item = QLabel()
        item.setObjectName('app_description')
        item.setCursor(QCursor(Qt.WhatsThisCursor))

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

        lb_name = QLabel()
        lb_name.setObjectName('app_publisher')
        lb_name.setCursor(QCursor(Qt.WhatsThisCursor))

        if not publisher:
            if not pkg.model.installed:
                lb_name.setProperty('publisher_known', 'false')

            publisher = self.i18n['unknown']

        lb_name.setText('  {}'.format(publisher))
        item.addWidget(lb_name)

        if publisher and full_publisher:
            lb_name.setToolTip(
                self.i18n['publisher'].capitalize() + ((': ' + full_publisher) if full_publisher else ''))

            if pkg.model.is_trustable():
                lb_verified = QLabel()
                lb_verified.setObjectName('icon_publisher_verified')
                lb_verified.setCursor(QCursor(Qt.WhatsThisCursor))
                lb_verified.setToolTip(self.i18n['publisher.verified'].capitalize())
                item.addWidget(lb_verified)
            else:
                lb_name.setText(lb_name.text() + "   ")

        self.setCellWidget(pkg.table_index, col, item)

    def _set_col_actions(self, col: int, pkg: PackageView):
        toolbar = QCustomToolbar()
        toolbar.setObjectName('app_actions')
        toolbar.add_space()

        if pkg.model.installed:
            def run():
                self.window.begin_launch_package(pkg)

            bt = IconButton(i18n=self.i18n, action=run, tooltip=self.i18n['action.run.tooltip'])
            bt.setObjectName('app_run')

            if not pkg.model.can_be_run():
                bt.setEnabled(False)
                bt.setProperty('_enabled', 'false')

            toolbar.layout().addWidget(bt)

        settings = self.has_any_settings(pkg)

        if pkg.model.installed:
            def handle_custom_actions():
                self.show_pkg_actions(pkg)

            bt = IconButton(i18n=self.i18n, action=handle_custom_actions, tooltip=self.i18n['action.settings.tooltip'])
            bt.setObjectName('app_actions')
            bt.setEnabled(bool(settings))
            toolbar.layout().addWidget(bt)

        if not pkg.model.installed:
            def show_screenshots():
                self.window.begin_show_screenshots(pkg)

            bt = IconButton(i18n=self.i18n, action=show_screenshots,
                            tooltip=self.i18n['action.screenshots.tooltip'])
            bt.setObjectName('app_screenshots')

            if not pkg.model.has_screenshots():
                bt.setEnabled(False)
                bt.setProperty('_enabled', 'false')

            toolbar.layout().addWidget(bt)

        def show_info():
            self.window.begin_show_info(pkg)

        bt = IconButton(i18n=self.i18n, action=show_info, tooltip=self.i18n['action.info.tooltip'])
        bt.setObjectName('app_info')
        bt.setEnabled(bool(pkg.model.has_info()))
        toolbar.layout().addWidget(bt)

        self.setCellWidget(pkg.table_index, col, toolbar)

    def change_headers_policy(self, policy: QHeaderView = QHeaderView.ResizeToContents, maximized: bool = False):
        header_horizontal = self.horizontalHeader()
        for i in range(self.columnCount()):
            if maximized:
                if i not in (4, 5, 8):
                    header_horizontal.setSectionResizeMode(i, QHeaderView.ResizeToContents)
                else:
                    header_horizontal.setSectionResizeMode(i, QHeaderView.Stretch)
            else:
                header_horizontal.setSectionResizeMode(i, policy)

    def get_width(self):
        return reduce(operator.add, [self.columnWidth(i) for i in range(self.columnCount())])
