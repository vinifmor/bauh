import operator
from functools import reduce
from threading import Lock
from typing import List

from PyQt5.QtCore import QEvent
from PyQt5.QtGui import QIcon, QWindowStateChangeEvent, QPixmap
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QApplication, QCheckBox, QHeaderView, QToolButton, QToolBar, \
    QSizePolicy, QLabel, QPlainTextEdit, QLineEdit, QProgressBar

from fpakman.core import resource
from fpakman.core.controller import ApplicationManager
from fpakman.core.model import Application
from fpakman.util.cache import Cache
from fpakman.view.qt.apps_table import AppsTable
from fpakman.view.qt.history import HistoryDialog
from fpakman.view.qt.info import InfoDialog
from fpakman.view.qt.root import is_root, ask_root_password
from fpakman.view.qt.thread import UpdateSelectedApps, RefreshApps, UninstallApp, DowngradeApp, GetAppInfo, \
    GetAppHistory, SearchApps, InstallApp, AnimateProgress, VerifyModels
from fpakman.view.qt.view_model import ApplicationView

DARK_ORANGE = '#FF4500'


class ManageWindow(QWidget):
    __BASE_HEIGHT__ = 400

    def __init__(self, locale_keys: dict, icon_cache: Cache, manager: ApplicationManager, disk_cache: bool,  tray_icon=None):
        super(ManageWindow, self).__init__()
        self.locale_keys = locale_keys
        self.manager = manager
        self.tray_icon = tray_icon
        self.thread_lock = Lock()
        self.working = False  # restrict the number of threaded actions
        self.apps = []
        self.label_flatpak = None
        self.icon_cache = icon_cache
        self.disk_cache = disk_cache

        self.icon_flathub = QIcon(resource.get_path('img/logo.svg'))
        self.resize(ManageWindow.__BASE_HEIGHT__, ManageWindow.__BASE_HEIGHT__)
        self.setWindowTitle(locale_keys['manage_window.title'])
        self.setWindowIcon(self.icon_flathub)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.toolbar_search = QToolBar()
        self.toolbar_search.setStyleSheet("spacing: 0px;")
        self.toolbar_search.setContentsMargins(0, 0, 0, 0)
        self.toolbar_search.addWidget(self._new_spacer())

        label_pre_search = QLabel()
        label_pre_search.setStyleSheet(
            "background: white; border-top-left-radius: 5px; border-bottom-left-radius: 5px;")
        self.toolbar_search.addWidget(label_pre_search)

        self.input_search = QLineEdit()
        self.input_search.setFrame(False)
        self.input_search.setPlaceholderText(self.locale_keys['window_manage.input_search.placeholder'] + "...")
        self.input_search.setToolTip(self.locale_keys['window_manage.input_search.tooltip'])
        self.input_search.setStyleSheet("QLineEdit { background-color: white; color: grey; spacing: 0;}")
        self.input_search.returnPressed.connect(self.search)
        self.toolbar_search.addWidget(self.input_search)

        label_pos_search = QLabel()
        label_pos_search.setPixmap(QPixmap(resource.get_path('img/search.svg')))
        label_pos_search.setStyleSheet("background: white; padding-right: 10px; border-top-right-radius: 5px; border-bottom-right-radius: 5px;")
        self.toolbar_search.addWidget(label_pos_search)

        self.toolbar_search.addWidget(self._new_spacer())
        self.layout.addWidget(self.toolbar_search)

        toolbar = QToolBar()

        self.checkbox_only_apps = QCheckBox()
        self.checkbox_only_apps.setText(self.locale_keys['manage_window.checkbox.only_apps'])
        self.checkbox_only_apps.setChecked(True)
        self.checkbox_only_apps.stateChanged.connect(self.filter_only_apps)
        toolbar.addWidget(self.checkbox_only_apps)

        toolbar.addWidget(self._new_spacer())

        self.label_status = QLabel()
        self.label_status.setText('')
        self.label_status.setStyleSheet("font-weight: bold")
        toolbar.addWidget(self.label_status)

        toolbar.addWidget(self._new_spacer())

        self.bt_refresh = QToolButton()
        self.bt_refresh.setToolTip(locale_keys['manage_window.bt.refresh.tooltip'])
        self.bt_refresh.setIcon(QIcon(resource.get_path('img/refresh.svg')))
        self.bt_refresh.clicked.connect(lambda: self.refresh(keep_console=False))
        toolbar.addWidget(self.bt_refresh)

        self.bt_upgrade = QToolButton()
        self.bt_upgrade.setToolTip(locale_keys['manage_window.bt.upgrade.tooltip'])
        self.bt_upgrade.setIcon(QIcon(resource.get_path('img/update_green.svg')))
        self.bt_upgrade.setEnabled(False)
        self.bt_upgrade.clicked.connect(self.update_selected)
        toolbar.addWidget(self.bt_upgrade)

        self.layout.addWidget(toolbar)

        self.table_apps = AppsTable(self, self.icon_cache, disk_cache=self.disk_cache)
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

        self.thread_refresh = RefreshApps(self.manager)
        self.thread_refresh.signal.connect(self._finish_refresh)

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

        self.thread_install = InstallApp(manager=self.manager, disk_cache=self.disk_cache, icon_cache=self.icon_cache)
        self.thread_install.signal_output.connect(self._update_action_output)
        self.thread_install.signal_finished.connect(self._finish_install)

        self.thread_animate_progress = AnimateProgress()
        self.thread_animate_progress.signal_change.connect(self._update_progress)

        self.thread_verify_models = VerifyModels()
        self.thread_verify_models.signal_updates.connect(self._notify_model_data_change)

        self.toolbar_bottom = QToolBar()
        self.label_updates = QLabel('')
        self.label_updates.setStyleSheet("color: {}; font-weight: bold".format(DARK_ORANGE))
        self.ref_label_updates = self.toolbar_bottom.addWidget(self.label_updates)

        self.toolbar_bottom.addWidget(self._new_spacer())

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.ref_progress_bar = self.toolbar_bottom.addWidget(self.progress_bar)

        self.toolbar_bottom.addWidget(self._new_spacer())

        self.layout.addWidget(self.toolbar_bottom)

        self.centralize()

    def _notify_model_data_change(self):
        self.table_apps.fill_async_data()

    def _new_spacer(self):
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return spacer

    def changeEvent(self, e: QEvent):

        if isinstance(e, QWindowStateChangeEvent):
            policy = QHeaderView.Stretch if self.isMaximized() else QHeaderView.ResizeToContents
            self.table_apps.change_headers_policy(policy)

    def closeEvent(self, event):

        if self.tray_icon:
            event.ignore()
            self.hide()
            self._handle_console_option(False)

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

    def refresh(self, keep_console: bool = True):

        if self._acquire_lock():
            self.input_search.clear()

            if not keep_console:
                self._handle_console_option(False)

            self._begin_action(self.locale_keys['manage_window.status.refreshing'])

            self.thread_refresh.start()

    def _finish_refresh(self, apps: List[Application]):
        self.update_apps(apps)
        self.finish_action()
        self._release_lock()

    def uninstall_app(self, app: ApplicationView):
        if self._acquire_lock():
            self._handle_console_option(True)
            self._begin_action('{} {}'.format(self.locale_keys['manage_window.status.uninstalling'], app.model.base_data.name))

            self.thread_uninstall.app = app
            self.thread_uninstall.start()

    def _finish_uninstall(self):
        self.finish_action()
        self._release_lock()
        self.refresh()

    def _finish_downgrade(self, success: bool):
        self.finish_action()
        self._release_lock()

        if success:
            self.refresh()
        else:
            self.checkbox_console.setChecked(True)

    def filter_only_apps(self, only_apps: int):

        if self.apps:
            show_only_apps = True if only_apps == 2 else False

            for idx, app_v in enumerate(self.apps):
                hidden = show_only_apps and app_v.model.is_library()
                self.table_apps.setRowHidden(idx, hidden)
                app_v.visible = not hidden

            self.change_update_state()
            self.table_apps.change_headers_policy(QHeaderView.Stretch)
            self.table_apps.change_headers_policy()
            self.resize_and_center()

    def change_update_state(self):

        enable_bt_update = False

        app_updates, library_updates = 0, 0

        for app_v in self.apps:
            if app_v.model.update:
                if app_v.model.runtime:
                    library_updates += 1
                else:
                    app_updates += 1

        total_updates = app_updates + library_updates
        if total_updates > 0:
            self.label_updates.setText('{}: {}'.format(self.locale_keys['manage_window.label.updates'], total_updates))
            self.label_updates.setToolTip('{} {} | {} {}'.format(app_updates,
                                                                 self.locale_keys['manage_window.checkbox.only_apps'].lower(),
                                                                 library_updates,
                                                                 self.locale_keys['others'].lower()))
        else:
            self.label_updates.setText('')

        for app_v in self.apps:
            if app_v.visible and app_v.update_checked:
                enable_bt_update = True
                break

        self.bt_upgrade.setEnabled(enable_bt_update)
        self.tray_icon.notify_updates([app.model for app in self.apps if app.model.update])

    def centralize(self):
        geo = self.frameGeometry()
        screen = QApplication.desktop().screenNumber(QApplication.desktop().cursor().pos())
        center_point = QApplication.desktop().screenGeometry(screen).center()
        geo.moveCenter(center_point)
        self.move(geo.topLeft())

    def update_apps(self, apps: List[Application]):
        self.apps = []

        napps = 0  # number of apps (not libraries)

        if apps:
            for app in apps:
                app_model = ApplicationView(model=app,
                                            visible=(not app.is_library()) or not self.checkbox_only_apps.isChecked())

                napps += 1 if not app.is_library() else 0
                self.apps.append(app_model)

        if napps == 0:
            self.checkbox_only_apps.setChecked(False)
            self.checkbox_only_apps.setCheckable(False)
        else:
            self.checkbox_only_apps.setCheckable(True)
            self.checkbox_only_apps.setChecked(True)

        self.table_apps.update_apps(self.apps)
        self.change_update_state()
        self.filter_only_apps(2 if self.checkbox_only_apps.isChecked() else 0)
        self.resize_and_center()

        self.thread_verify_models.apps = self.apps
        self.thread_verify_models.start()

    def resize_and_center(self):
        new_width = reduce(operator.add, [self.table_apps.columnWidth(i) for i in range(len(self.table_apps.column_names))]) * 1.05
        self.resize(new_width, self.height())
        self.centralize()

    def update_selected(self):

        if self._acquire_lock():
            if self.apps:

                to_update = [app_v for app_v in self.apps if app_v.visible and app_v.update_checked]

                if to_update:
                    self._handle_console_option(True)

                    self._begin_action(self.locale_keys['manage_window.status.upgrading'])
                    self.thread_update.apps_to_update = to_update
                    self.thread_update.start()

    def _finish_update_selected(self, success: bool):
        self.finish_action()
        self._release_lock()

        if success:
            self.refresh()
        else:
            self.bt_upgrade.setEnabled(True)
            self.checkbox_console.setChecked(True)

    def _update_action_output(self, output: str):
        self.textarea_output.appendPlainText(output)

    def _begin_action(self, action_label: str, keep_search: bool = False):
        self.ref_label_updates.setVisible(False)
        self.thread_animate_progress.stop = False
        self.thread_animate_progress.start()
        self.ref_progress_bar.setVisible(True)

        self.label_status.setText(action_label + "...")
        self.bt_upgrade.setEnabled(False)
        self.bt_refresh.setEnabled(False)
        self.checkbox_only_apps.setEnabled(False)
        self.table_apps.setEnabled(False)

        if keep_search:
            self.toolbar_search.setEnabled(False)
        else:
            self.toolbar_search.setVisible(False)

    def finish_action(self):
        self.ref_progress_bar.setVisible(False)
        self.ref_label_updates.setVisible(True)
        self.thread_animate_progress.stop = True
        self.progress_bar.setValue(0)
        self.bt_refresh.setEnabled(True)
        self.checkbox_only_apps.setEnabled(True)
        self.table_apps.setEnabled(True)
        self.input_search.setEnabled(True)
        self.label_status.setText('')
        self.toolbar_search.setVisible(True)
        self.toolbar_search.setEnabled(True)

    def downgrade_app(self, app: ApplicationView):
        if self._acquire_lock():

            pwd = None

            if not is_root():
                pwd, ok = ask_root_password(self.locale_keys)

                if not ok:
                    self._release_lock()
                    return

            self._handle_console_option(True)
            self._begin_action('{} {}'.format(self.locale_keys['manage_window.status.downgrading'], app.model.base_data.name))

            self.thread_downgrade.app = app
            self.thread_downgrade.root_password = pwd
            self.thread_downgrade.start()

    def get_app_info(self, app: dict):

        if self._acquire_lock():
            self._handle_console_option(False)
            self._begin_action(self.locale_keys['manage_window.status.info'])

            self.thread_get_info.app = app
            self.thread_get_info.start()

    def get_app_history(self, app: dict):
        if self._acquire_lock():
            self._handle_console_option(False)
            self._begin_action(self.locale_keys['manage_window.status.history'])

            self.thread_get_history.app = app
            self.thread_get_history.start()

    def _finish_get_info(self, app_info: dict):
        self._release_lock()
        self.finish_action()
        self.change_update_state()
        dialog_info = InfoDialog(app_info, self.table_apps.get_selected_app_icon(), self.locale_keys)
        dialog_info.exec_()

    def _finish_get_history(self, app: dict):
        self._release_lock()
        self.finish_action()
        self.change_update_state()

        if app.get('error'):
            self._handle_console_option(True)
            self.textarea_output.appendPlainText(app['error'])
            self.checkbox_console.setChecked(True)
        else:
            dialog_history = HistoryDialog(app, self.table_apps.get_selected_app_icon(), self.locale_keys)
            dialog_history.exec_()

    def search(self):

        word = self.input_search.text().strip()

        if word and self._acquire_lock():
            self._handle_console_option(False)
            self._begin_action(self.locale_keys['manage_window.status.searching'], keep_search=True)
            self.thread_search.word = word
            self.thread_search.start()

    def _finish_search(self, apps_found: List[Application]):
        self._release_lock()
        self.finish_action()
        self.update_apps(apps_found)

    def install_app(self, app: ApplicationView):
        if self._acquire_lock():
            self._handle_console_option(True)
            self._begin_action('{} {}'.format(self.locale_keys['manage_window.status.installing'], app.model.base_data.name))

            self.thread_install.app = app
            self.thread_install.start()

    def _finish_install(self, success: bool):
        self.input_search.setText('')
        self.finish_action()
        self._release_lock()

        if success:
            self.refresh()
        else:
            self.checkbox_console.setChecked(True)

    def _update_progress(self, value: int):
        self.progress_bar.setValue(value)
