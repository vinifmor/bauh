from typing import List

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QPixmap, QIcon, QColor, QCursor
from PyQt5.QtNetwork import QNetworkRequest, QNetworkAccessManager
from PyQt5.QtWidgets import QTableWidget, QTableView, QMenu, QAction, QTableWidgetItem, QToolButton, QWidget, \
    QHeaderView, QLabel

from fpakman.core import resource, util
from fpakman.view.qt import dialog


class UpdateToggleButton(QToolButton):

    def __init__(self, model: dict, root: QWidget, locale_keys: dict, checked: bool = True):
        super(UpdateToggleButton, self).__init__()
        self.app = model
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
        self.app['update_checked'] = not not_checked
        self.setIcon(self.icon_on if not not_checked else self.icon_off)
        self.root.change_update_state()


class AppsTable(QTableWidget):

    def __init__(self, parent: QWidget):
        super(AppsTable, self).__init__()
        self.setParent(parent)
        self.window = parent
        self.column_names = [parent.locale_keys[key].capitalize() for key in ['flatpak.info.name',
                                                                              'flatpak.info.version',
                                                                              'manage_window.columns.latest_version',
                                                                              'flatpak.info.branch',
                                                                              'flatpak.info.arch',
                                                                              'flatpak.info.id',
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

        self.icon_cache = {}

    def contextMenuEvent(self, QContextMenuEvent):  # selected row right click event

        app = self.get_selected_app()

        menu_row = QMenu()

        if app['model']['installed']:
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

            if not app['model']['runtime']:  # not available for runtimes
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

    def get_selected_app(self):
        return self.window.apps[self.currentRow()]

    def get_selected_app_icon(self):
        return self.item(self.currentRow(), 0).icon()

    def _uninstall_app(self):
        selected_app = self.get_selected_app()

        if dialog.ask_confirmation(title=self.window.locale_keys['manage_window.apps_table.row.actions.uninstall.popup.title'],
                                   body=self.window.locale_keys['manage_window.apps_table.row.actions.uninstall.popup.body'].format(selected_app['model']['name']),
                                   locale_keys=self.window.locale_keys):
            self.window.uninstall_app(selected_app['model']['ref'])

    def _downgrade_app(self):
        selected_app = self.get_selected_app()

        if dialog.ask_confirmation(title=self.window.locale_keys['manage_window.apps_table.row.actions.downgrade'],
                                   body=self.window.locale_keys['manage_window.apps_table.row.actions.downgrade.popup.body'].format(selected_app['model']['name']),
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
        pixmap = QPixmap()
        pixmap.loadFromData(http_response.readAll())
        icon = QIcon(pixmap)
        self.icon_cache[icon_url] = icon

        for idx, app in enumerate(self.window.apps):
            if app['model']['icon'] == icon_url:
                self.item(idx, 0).setIcon(icon)
                self.window.resize_and_center()
                break

    def update_apps(self, apps: List[dict]):
        self.setEnabled(True)
        self.setRowCount(len(apps) if apps else 0)

        if apps:
            for idx, app in enumerate(apps):

                tooltip = util.strip_html(app['model']['description']) if app['model']['description'] else None

                col_name = QTableWidgetItem()
                col_name.setText(app['model']['name'])
                col_name.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                col_name.setToolTip(tooltip)

                if not app['model']['icon']:
                    col_name.setIcon(self.icon_flathub)
                else:
                    cached_icon = self.icon_cache.get(app['model']['icon'])

                    if cached_icon:
                        col_name.setIcon(cached_icon)
                    else:
                        col_name.setIcon(self.icon_flathub)
                        self.network_man.get(QNetworkRequest(QUrl(app['model']['icon'])))

                self.setItem(idx, 0, col_name)

                col_version = QTableWidgetItem()
                col_version.setText(app['model']['version'])
                col_version.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                col_version.setToolTip(tooltip)
                self.setItem(idx, 1, col_version)

                col_release = QTableWidgetItem()
                col_release.setText(app['model']['latest_version'])
                col_release.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                col_release.setToolTip(tooltip)
                self.setItem(idx, 2, col_release)

                if app['model']['version'] and app['model']['latest_version'] and app['model']['version'] < app['model']['latest_version']:
                    col_release.setForeground(QColor('orange'))

                col_branch = QTableWidgetItem()
                col_branch.setText(app['model']['branch'])
                col_branch.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                col_branch.setToolTip(tooltip)
                self.setItem(idx, 3, col_branch)

                col_arch = QTableWidgetItem()
                col_arch.setText(app['model']['arch'])
                col_arch.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                col_arch.setToolTip(tooltip)
                self.setItem(idx, 4, col_arch)

                col_id = QTableWidgetItem()
                col_id.setText(app['model']['id'])
                col_id.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                col_id.setToolTip(tooltip)
                self.setItem(idx, 5, col_id)

                col_origin = QTableWidgetItem()
                col_origin.setText(app['model']['origin'])
                col_origin.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                col_origin.setToolTip(tooltip)
                self.setItem(idx, 6, col_origin)

                col_installed = QLabel()
                col_installed.setPixmap((QPixmap(resource.get_path('img/{}.svg'.format('checked' if app['model']['installed'] else 'red_cross')))))
                col_installed.setToolTip(tooltip)
                col_installed.setAlignment(Qt.AlignCenter)

                self.setCellWidget(idx, 7, col_installed)

                col_update = UpdateToggleButton(app, self.window, self.window.locale_keys, app['model']['update']) if app['model']['update'] else None
                self.setCellWidget(idx, 8, col_update)

    def change_headers_policy(self, policy: QHeaderView = QHeaderView.ResizeToContents):
        header_horizontal = self.horizontalHeader()
        for i in range(self.columnCount()):
            header_horizontal.setSectionResizeMode(i, policy)
