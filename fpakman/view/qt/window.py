import operator
from functools import reduce
from typing import List, Set

from PyQt5.QtCore import QEvent, Qt, QSize
from PyQt5.QtGui import QIcon, QWindowStateChangeEvent, QPixmap
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QApplication, QCheckBox, QHeaderView, QToolButton, QToolBar, \
    QSizePolicy, QLabel, QPlainTextEdit, QLineEdit, QProgressBar, QHBoxLayout

from fpakman.core import resource, system
from fpakman.core.controller import ApplicationManager
from fpakman.core.model import Application
from fpakman.util.cache import Cache
from fpakman.view.qt import dialog
from fpakman.view.qt.about import AboutDialog
from fpakman.view.qt.apps_table import AppsTable
from fpakman.view.qt.history import HistoryDialog
from fpakman.view.qt.info import InfoDialog
from fpakman.view.qt.root import is_root, ask_root_password
from fpakman.view.qt.thread import UpdateSelectedApps, RefreshApps, UninstallApp, DowngradeApp, GetAppInfo, \
    GetAppHistory, SearchApps, InstallApp, AnimateProgress, VerifyModels, RefreshApp, FindSuggestions
from fpakman.view.qt.view_model import ApplicationView

DARK_ORANGE = '#FF4500'


class ManageWindow(QWidget):
    __BASE_HEIGHT__ = 400

    def __init__(self, locale_keys: dict, icon_cache: Cache, manager: ApplicationManager, disk_cache: bool, download_icons: bool, screen_size, suggestions: bool, tray_icon=None):
        super(ManageWindow, self).__init__()
        self.locale_keys = locale_keys
        self.manager = manager
        self.tray_icon = tray_icon
        self.working = False  # restrict the number of threaded actions
        self.apps = []
        self.label_flatpak = None
        self.icon_cache = icon_cache
        self.disk_cache = disk_cache
        self.download_icons = download_icons
        self.screen_size = screen_size

        self.icon_flathub = QIcon(resource.get_path('img/logo.svg'))
        self.resize(ManageWindow.__BASE_HEIGHT__, ManageWindow.__BASE_HEIGHT__)
        self.setWindowIcon(self.icon_flathub)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.toolbar_top = QToolBar()
        self.toolbar_top.addWidget(self._new_spacer())

        self.label_status = QLabel()
        self.label_status.setText('')
        self.label_status.setStyleSheet("font-weight: bold")
        self.toolbar_top.addWidget(self.label_status)

        self.toolbar_search = QToolBar()
        self.toolbar_search.setStyleSheet("spacing: 0px;")
        self.toolbar_search.setContentsMargins(0, 0, 0, 0)

        label_pre_search = QLabel()
        label_pre_search.setStyleSheet("background: white; border-top-left-radius: 5px; border-bottom-left-radius: 5px;")
        self.toolbar_search.addWidget(label_pre_search)

        self.input_search = QLineEdit()
        self.input_search.setMaxLength(20)
        self.input_search.setFrame(False)
        self.input_search.setPlaceholderText(self.locale_keys['window_manage.input_search.placeholder'] + "...")
        self.input_search.setToolTip(self.locale_keys['window_manage.input_search.tooltip'])
        self.input_search.setStyleSheet("QLineEdit { background-color: white; color: gray; spacing: 0;}")
        self.input_search.returnPressed.connect(self.search)
        self.toolbar_search.addWidget(self.input_search)

        label_pos_search = QLabel()
        label_pos_search.setPixmap(QPixmap(resource.get_path('img/search.svg')))
        label_pos_search.setStyleSheet("background: white; padding-right: 10px; border-top-right-radius: 5px; border-bottom-right-radius: 5px;")
        self.toolbar_search.addWidget(label_pos_search)

        self.ref_toolbar_search = self.toolbar_top.addWidget(self.toolbar_search)
        self.toolbar_top.addWidget(self._new_spacer())
        self.layout.addWidget(self.toolbar_top)

        toolbar = QToolBar()

        self.checkbox_updates = QCheckBox()
        self.checkbox_updates.setText(self.locale_keys['updates'].capitalize())
        self.checkbox_updates.stateChanged.connect(self._handle_updates_filter)
        self.ref_checkbox_updates = toolbar.addWidget(self.checkbox_updates)

        self.checkbox_only_apps = QCheckBox()
        self.checkbox_only_apps.setText(self.locale_keys['manage_window.checkbox.only_apps'])
        self.checkbox_only_apps.setChecked(True)
        self.checkbox_only_apps.stateChanged.connect(self._handle_filter_only_apps)
        self.ref_checkbox_only_apps = toolbar.addWidget(self.checkbox_only_apps)

        self.extra_filters = QWidget()
        self.extra_filters.setLayout(QHBoxLayout())
        toolbar.addWidget(self.extra_filters)

        toolbar.addWidget(self._new_spacer())

        self.bt_refresh = QToolButton()
        self.bt_refresh.setToolTip(locale_keys['manage_window.bt.refresh.tooltip'])
        self.bt_refresh.setIcon(QIcon(resource.get_path('img/refresh.svg')))
        self.bt_refresh.clicked.connect(lambda: self.refresh_apps(keep_console=False))
        toolbar.addWidget(self.bt_refresh)

        self.bt_upgrade = QToolButton()
        self.bt_upgrade.setToolTip(locale_keys['manage_window.bt.upgrade.tooltip'])
        self.bt_upgrade.setIcon(QIcon(resource.get_path('img/update_green.svg')))
        self.bt_upgrade.setEnabled(False)
        self.bt_upgrade.clicked.connect(self.update_selected)
        self.ref_bt_upgrade = toolbar.addWidget(self.bt_upgrade)

        self.layout.addWidget(toolbar)

        self.table_apps = AppsTable(self, self.icon_cache, disk_cache=self.disk_cache, download_icons=self.download_icons)
        self.table_apps.change_headers_policy()

        self.layout.addWidget(self.table_apps)

        toolbar_console = QToolBar()

        self.checkbox_console = QCheckBox()
        self.checkbox_console.setText(self.locale_keys['manage_window.checkbox.show_details'])
        self.checkbox_console.stateChanged.connect(self._handle_console)
        self.checkbox_console.setVisible(False)
        self.ref_checkbox_console = toolbar_console.addWidget(self.checkbox_console)

        toolbar_console.addWidget(self._new_spacer())
        self.layout.addWidget(toolbar_console)

        self.textarea_output = QPlainTextEdit(self)
        self.textarea_output.resize(self.table_apps.size())
        self.textarea_output.setStyleSheet("background: black; color: white;")
        self.layout.addWidget(self.textarea_output)
        self.textarea_output.setVisible(False)
        self.textarea_output.setReadOnly(True)

        self.thread_update = UpdateSelectedApps(self.manager)
        self.thread_update.signal_output.connect(self._update_action_output)
        self.thread_update.signal_finished.connect(self._finish_update_selected)
        self.thread_update.signal_status.connect(self._change_updating_app_status)

        self.thread_refresh = RefreshApps(self.manager)
        self.thread_refresh.signal.connect(self._finish_refresh_apps)

        self.thread_uninstall = UninstallApp(self.manager, self.icon_cache)
        self.thread_uninstall.signal_output.connect(self._update_action_output)
        self.thread_uninstall.signal_finished.connect(self._finish_uninstall)

        self.thread_downgrade = DowngradeApp(self.manager, self.locale_keys)
        self.thread_downgrade.signal_output.connect(self._update_action_output)
        self.thread_downgrade.signal_finished.connect(self._finish_downgrade)

        self.thread_get_info = GetAppInfo(self.manager)
        self.thread_get_info.signal_finished.connect(self._finish_get_info)

        self.thread_get_history = GetAppHistory(self.manager, self.locale_keys)
        self.thread_get_history.signal_finished.connect(self._finish_get_history)

        self.thread_search = SearchApps(self.manager)
        self.thread_search.signal_finished.connect(self._finish_search)

        self.thread_install = InstallApp(manager=self.manager, disk_cache=self.disk_cache, icon_cache=self.icon_cache, locale_keys=self.locale_keys)
        self.thread_install.signal_output.connect(self._update_action_output)
        self.thread_install.signal_finished.connect(self._finish_install)

        self.thread_animate_progress = AnimateProgress()
        self.thread_animate_progress.signal_change.connect(self._update_progress)

        self.thread_verify_models = VerifyModels()
        self.thread_verify_models.signal_updates.connect(self._notify_model_data_change)

        self.thread_refresh_app = RefreshApp(manager=self.manager)
        self.thread_refresh_app.signal_finished.connect(self._finish_refresh)
        self.thread_refresh_app.signal_output.connect(self._update_action_output)

        self.thread_suggestions = FindSuggestions(man=self.manager)
        self.thread_suggestions.signal_finished.connect(self._finish_search)

        self.toolbar_bottom = QToolBar()
        self.toolbar_bottom.setIconSize(QSize(16, 16))

        self.label_updates = QLabel()
        self.ref_label_updates = self.toolbar_bottom.addWidget(self.label_updates)

        self.toolbar_bottom.addWidget(self._new_spacer())

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.ref_progress_bar = self.toolbar_bottom.addWidget(self.progress_bar)

        self.toolbar_bottom.addWidget(self._new_spacer())

        bt_about = QToolButton()
        bt_about.setStyleSheet('QToolButton { border: 0px; }')
        bt_about.setIcon(QIcon(resource.get_path('img/about.svg')))
        bt_about.clicked.connect(self._show_about)
        bt_about.setToolTip(self.locale_keys['manage_window.bt_about.tooltip'])
        self.ref_bt_about = self.toolbar_bottom.addWidget(bt_about)

        self.layout.addWidget(self.toolbar_bottom)

        self.centralize()

        self.filter_only_apps = True
        self.filter_types = set()
        self.filter_updates = False
        self._maximized = False

        self.dialog_about = None
        self.first_refresh = suggestions

    def _show_about(self):
        if self.dialog_about is None:
            self.dialog_about = AboutDialog(self.locale_keys)

        self.dialog_about.show()

    def _handle_updates_filter(self, status: int):
        self.filter_updates = status == 2
        self.apply_filters()

    def _handle_filter_only_apps(self, status: int):
        self.filter_only_apps = status == 2
        self.apply_filters()

    def _handle_type_filter(self, status: int, app_type: str):

        if status == 2:
            self.filter_types.add(app_type)
        elif app_type in self.filter_types:
            self.filter_types.remove(app_type)

        self.apply_filters()

    def _notify_model_data_change(self):
        self.table_apps.fill_async_data()

    def _new_spacer(self):
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return spacer

    def changeEvent(self, e: QEvent):
        if isinstance(e, QWindowStateChangeEvent):
            self._maximized = self.isMaximized()
            policy = QHeaderView.Stretch if self._maximized else QHeaderView.ResizeToContents
            self.table_apps.change_headers_policy(policy)

    def closeEvent(self, event):

        if self.tray_icon:
            event.ignore()
            self.hide()
            self._handle_console_option(False)

    def _handle_console(self, checked: bool):

        if checked:
            self.textarea_output.show()
        else:
            self.textarea_output.hide()

    def _handle_console_option(self, enable: bool):

        if enable:
            self.textarea_output.clear()

        self.ref_checkbox_console.setVisible(enable)
        self.checkbox_console.setChecked(False)
        self.textarea_output.hide()

    def refresh_apps(self, keep_console: bool = True):
        self.filter_types.clear()
        self.input_search.clear()

        if not keep_console:
            self._handle_console_option(False)

        self.ref_checkbox_updates.setVisible(False)
        self.ref_checkbox_only_apps.setVisible(False)
        self._begin_action(self.locale_keys['manage_window.status.refreshing'], clear_filters=True)
        self.thread_refresh.start()

    def _finish_refresh_apps(self, apps: List[Application]):
        self.finish_action()
        self.ref_checkbox_only_apps.setVisible(True)
        self.ref_bt_upgrade.setVisible(True)
        self.update_apps(apps)
        self.first_refresh = False

    def uninstall_app(self, app: ApplicationView):
        pwd = None
        requires_root = self.manager.requires_root('uninstall', app.model)

        if not is_root() and requires_root:
            pwd, ok = ask_root_password(self.locale_keys)

            if not ok:
                return

        self._handle_console_option(True)
        self._begin_action('{} {}'.format(self.locale_keys['manage_window.status.uninstalling'], app.model.base_data.name))

        self.thread_uninstall.app = app
        self.thread_uninstall.root_password = pwd
        self.thread_uninstall.start()

    def refresh(self, app: ApplicationView):
        pwd = None
        requires_root = self.manager.requires_root('refresh', app.model)

        if not is_root() and requires_root:
            pwd, ok = ask_root_password(self.locale_keys)

            if not ok:
                return

        self._handle_console_option(True)
        self._begin_action('{} {}'.format(self.locale_keys['manage_window.status.refreshing_app'], app.model.base_data.name))

        self.thread_refresh_app.app = app
        self.thread_refresh_app.root_password = pwd
        self.thread_refresh_app.start()

    def _finish_uninstall(self, app: ApplicationView):
        self.finish_action()

        if app:
            if self._can_notify_user():
                system.notify_user('{} ({}) {}'.format(app.model.base_data.name, app.model.get_type(), self.locale_keys['uninstalled']))

            self.refresh_apps()
        else:
            if self._can_notify_user():
                system.notify_user('{}: {}'.format(app.model.base_data.name, self.locale_keys['notification.uninstall.failed']))

            self.checkbox_console.setChecked(True)

    def _can_notify_user(self):
        return self.isHidden() or self.isMinimized()

    def _finish_downgrade(self, success: bool):
        self.finish_action()

        if success:
            if self._can_notify_user():
                app = self.table_apps.get_selected_app()
                system.notify_user('{} ({}) {}'.format(app.model.base_data.name, app.model.get_type(), self.locale_keys['downgraded']))

            self.refresh_apps()

            if self.tray_icon:
                self.tray_icon.verify_updates(notify_user=False)
        else:
            if self._can_notify_user():
                system.notify_user(self.locale_keys['notification.downgrade.failed'])

            self.checkbox_console.setChecked(True)

    def _finish_refresh(self, success: bool):
        self.finish_action()

        if success:
            self.refresh_apps()
        else:
            self.checkbox_console.setChecked(True)

    def _change_updating_app_status(self, app_name: str):
        self.label_status.setText('{} {}...'.format(self.locale_keys['manage_window.status.upgrading'], app_name))

    def apply_filters(self):
        if self.apps:
            visible_apps = len(self.apps)
            for idx, app_v in enumerate(self.apps):
                hidden = self.filter_only_apps and app_v.model.is_library()

                if not hidden and self.filter_types is not None:
                    hidden = app_v.model.get_type() not in self.filter_types

                if not hidden and self.filter_updates:
                    hidden = not app_v.model.update

                self.table_apps.setRowHidden(idx, hidden)
                app_v.visible = not hidden
                visible_apps -= 1 if hidden else 0

            self.change_update_state(change_filters=False)

            if not self._maximized:
                self.table_apps.change_headers_policy(QHeaderView.Stretch)
                self.table_apps.change_headers_policy()
                self.resize_and_center(accept_lower_width=visible_apps > 0)

    def change_update_state(self, change_filters: bool = True):
        enable_bt_update = False
        app_updates, library_updates, not_installed = 0, 0, 0

        for app_v in self.apps:
            if app_v.model.update:
                if app_v.model.runtime:
                    library_updates += 1
                else:
                    app_updates += 1

            if not app_v.model.installed:
                not_installed += 1

        for app_v in self.apps:
            if not_installed == 0 and app_v.visible and app_v.update_checked:
                enable_bt_update = True
                break

        self.bt_upgrade.setEnabled(enable_bt_update)

        total_updates = app_updates + library_updates

        if total_updates > 0:
            self.label_updates.setPixmap(QPixmap(resource.get_path('img/exclamation.svg')).scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.label_updates.setToolTip('{}: {} ( {} {} | {} {} )'.format(self.locale_keys['manage_window.label.updates'],
                                                                            total_updates,
                                                                            app_updates,
                                                                            self.locale_keys['manage_window.checkbox.only_apps'].lower(),
                                                                            library_updates,
                                                                            self.locale_keys['others'].lower()))

            if not_installed == 0:
                if not self.ref_checkbox_updates.isVisible():
                    self.ref_checkbox_updates.setVisible(True)

                if change_filters and not self.checkbox_updates.isChecked():
                    self.checkbox_updates.setChecked(True)

            if change_filters and library_updates > 0 and self.checkbox_only_apps.isChecked():
                self.checkbox_only_apps.setChecked(False)
        else:
            self.checkbox_updates.setChecked(False)
            self.ref_checkbox_updates.setVisible(False)
            self.label_updates.setPixmap(QPixmap())

    def centralize(self):
        geo = self.frameGeometry()
        screen = QApplication.desktop().screenNumber(QApplication.desktop().cursor().pos())
        center_point = QApplication.desktop().screenGeometry(screen).center()
        geo.moveCenter(center_point)
        self.move(geo.topLeft())

    def update_apps(self, apps: List[Application], update_check_enabled: bool = True):
        self.apps = []

        napps = 0  # number of apps (not libraries)
        available_types = set()

        if apps:
            for app in apps:
                app_model = ApplicationView(model=app, visible=(not app.is_library()) or not self.checkbox_only_apps.isChecked())
                available_types.add(app.get_type())
                napps += 1 if not app.is_library() else 0
                self.apps.append(app_model)

        if napps == 0:

            if self.first_refresh:
                self._begin_search('')
                self.thread_suggestions.start()
                return
            else:
                self.checkbox_only_apps.setChecked(False)
                self.checkbox_only_apps.setCheckable(False)
        else:
            self.checkbox_only_apps.setCheckable(True)
            self.checkbox_only_apps.setChecked(True)

        self._update_type_filters(available_types)
        self.table_apps.update_apps(self.apps, update_check_enabled=update_check_enabled)
        self.apply_filters()
        self.change_update_state()
        self.resize_and_center()

        self.thread_verify_models.apps = self.apps
        self.thread_verify_models.start()

    def _update_type_filters(self, available_types: Set[str]):

        self.filter_types = available_types

        filters_layout = self.extra_filters.layout()
        for i in reversed(range(filters_layout.count())):
            filters_layout.itemAt(i).widget().setParent(None)

        if available_types:
            for app_type in sorted(list(available_types)):
                checkbox_app_type = QCheckBox()
                checkbox_app_type.setChecked(True)
                checkbox_app_type.setText(app_type.capitalize())

                def handle_click(status: int, filter_type: str = app_type):
                    self._handle_type_filter(status, filter_type)

                checkbox_app_type.stateChanged.connect(handle_click)
                filters_layout.addWidget(checkbox_app_type)

    def resize_and_center(self, accept_lower_width: bool = True):
        new_width = reduce(operator.add, [self.table_apps.columnWidth(i) for i in range(len(self.table_apps.column_names))]) * 1.05

        if accept_lower_width or new_width > self.width():
            self.resize(new_width, self.height())

        self.centralize()

    def update_selected(self):
        if self.apps:

            to_update = [app_v for app_v in self.apps if app_v.visible and app_v.update_checked]

            if to_update:
                if dialog.ask_confirmation(
                        title=self.locale_keys['manage_window.upgrade_all.popup.title'],
                        body=self.locale_keys['manage_window.upgrade_all.popup.body'],
                        locale_keys=self.locale_keys):
                    self._handle_console_option(True)

                    self._begin_action(self.locale_keys['manage_window.status.upgrading'])
                    self.thread_update.apps_to_update = to_update
                    self.thread_update.start()

    def _finish_update_selected(self, success: bool, updated: int):
        self.finish_action()

        if success:
            if self._can_notify_user():
                system.notify_user('{} {}'.format(updated, self.locale_keys['notification.update_selected.success']))

            self.refresh_apps()

            if self.tray_icon:
                self.tray_icon.verify_updates()
        else:
            if self._can_notify_user():
                system.notify_user(self.locale_keys['notification.update_selected.failed'])

            self.bt_upgrade.setEnabled(True)
            self.checkbox_console.setChecked(True)

    def _update_action_output(self, output: str):
        self.textarea_output.appendPlainText(output)

    def _begin_action(self, action_label: str, keep_search: bool = False, clear_filters: bool = False):
        self.ref_bt_about.setVisible(False)
        self.ref_label_updates.setVisible(False)
        self.thread_animate_progress.stop = False
        self.thread_animate_progress.start()
        self.ref_progress_bar.setVisible(True)

        self.label_status.setText(action_label + "...")
        self.bt_upgrade.setEnabled(False)
        self.bt_refresh.setEnabled(False)
        self.checkbox_only_apps.setEnabled(False)
        self.table_apps.setEnabled(False)
        self.checkbox_updates.setEnabled(False)

        if keep_search:
            self.ref_toolbar_search.setVisible(True)
        else:
            self.ref_toolbar_search.setVisible(False)

        if clear_filters:
            self._update_type_filters(set())
        else:
            self.extra_filters.setEnabled(False)

    def finish_action(self):
        self.ref_bt_about.setVisible(True)
        self.ref_progress_bar.setVisible(False)
        self.ref_label_updates.setVisible(True)
        self.thread_animate_progress.stop = True
        self.progress_bar.setValue(0)
        self.bt_refresh.setEnabled(True)
        self.checkbox_only_apps.setEnabled(True)
        self.table_apps.setEnabled(True)
        self.input_search.setEnabled(True)
        self.label_status.setText('')
        self.ref_toolbar_search.setVisible(True)
        self.ref_toolbar_search.setEnabled(True)
        self.extra_filters.setEnabled(True)
        self.checkbox_updates.setEnabled(True)

    def downgrade_app(self, app: ApplicationView):
        pwd = None
        requires_root = self.manager.requires_root('downgrade', self.table_apps.get_selected_app().model)

        if not is_root() and requires_root:
            pwd, ok = ask_root_password(self.locale_keys)

            if not ok:
                return

        self._handle_console_option(True)
        self._begin_action('{} {}'.format(self.locale_keys['manage_window.status.downgrading'], app.model.base_data.name))

        self.thread_downgrade.app = app
        self.thread_downgrade.root_password = pwd
        self.thread_downgrade.start()

    def get_app_info(self, app: dict):
        self._handle_console_option(False)
        self._begin_action(self.locale_keys['manage_window.status.info'])

        self.thread_get_info.app = app
        self.thread_get_info.start()

    def get_app_history(self, app: dict):
        self._handle_console_option(False)
        self._begin_action(self.locale_keys['manage_window.status.history'])

        self.thread_get_history.app = app
        self.thread_get_history.start()

    def _finish_get_info(self, app_info: dict):
        self.finish_action()
        self.change_update_state(change_filters=False)
        dialog_info = InfoDialog(app=app_info, icon_cache=self.icon_cache, locale_keys=self.locale_keys, screen_size=self.screen_size)
        dialog_info.exec_()

    def _finish_get_history(self, app: dict):
        self.finish_action()
        self.change_update_state(change_filters=False)

        if app.get('error'):
            self._handle_console_option(True)
            self.textarea_output.appendPlainText(app['error'])
            self.checkbox_console.setChecked(True)
        else:
            dialog_history = HistoryDialog(app, self.icon_cache, self.locale_keys)
            dialog_history.exec_()

    def _begin_search(self, word):
        self._handle_console_option(False)
        self.ref_checkbox_only_apps.setVisible(False)
        self.ref_checkbox_updates.setVisible(False)
        self.filter_updates = False
        self._begin_action('{}{}'.format(self.locale_keys['manage_window.status.searching'], '"{}"'.format(word) if word else ''), clear_filters=True)

    def search(self):

        word = self.input_search.text().strip()

        if word:
            self._begin_search(word)
            self.thread_search.word = word
            self.thread_search.start()

    def _finish_search(self, apps_found: List[Application]):
        self.finish_action()
        self.ref_bt_upgrade.setVisible(False)
        self.update_apps(apps_found, update_check_enabled=False)

    def install_app(self, app: ApplicationView):
        pwd = None
        requires_root = self.manager.requires_root('install', app.model)

        if not is_root() and requires_root:
            pwd, ok = ask_root_password(self.locale_keys)

            if not ok:
                return

        self._handle_console_option(True)
        self._begin_action('{} {}'.format(self.locale_keys['manage_window.status.installing'], app.model.base_data.name))

        self.thread_install.app = app
        self.thread_install.root_password = pwd
        self.thread_install.start()

    def _finish_install(self, app: ApplicationView):
        self.input_search.setText('')
        self.finish_action()

        if app:
            if self._can_notify_user():
                system.notify_user('{} ({}) {}'.format(app.model.base_data.name, app.model.get_type(), self.locale_keys['installed']))

            self.refresh_apps()
        else:
            if self._can_notify_user():
                system.notify_user('{}: {}'.format(app.model.base_data.name, self.locale_keys['notification.install.failed']))

            self.checkbox_console.setChecked(True)

    def _update_progress(self, value: int):
        self.progress_bar.setValue(value)
