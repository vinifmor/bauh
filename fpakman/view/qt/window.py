import operator
from functools import reduce
from threading import Lock
from typing import List

from PyQt5.QtCore import QEvent
from PyQt5.QtGui import QIcon, QWindowStateChangeEvent
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QApplication, QCheckBox, QHeaderView, QToolButton, QToolBar, \
    QSizePolicy, QLabel, QPlainTextEdit

from fpakman.core import resource, flatpak
from fpakman.core.controller import FlatpakManager
from fpakman.view.qt import dialog
from fpakman.view.qt.apps_table import AppsTable
from fpakman.view.qt.history import HistoryDialog
from fpakman.view.qt.info import InfoDialog
from fpakman.view.qt.root import is_root, ask_root_password
from fpakman.view.qt.thread import UpdateSelectedApps, RefreshApps, UninstallApp, DowngradeApp, GetAppInfo, \
    GetAppHistory


class ManageWindow(QWidget):

    __BASE_HEIGHT__ = 400

    def __init__(self, locale_keys: dict, manager: FlatpakManager, tray_icon=None):
        super(ManageWindow, self).__init__()
        self.locale_keys = locale_keys
        self.column_names = [locale_keys[key].capitalize() for key in ['flatpak.info.name',
                                                                       'flatpak.info.version',
                                                                       'manage_window.columns.latest_version',
                                                                       'flatpak.info.branch',
                                                                       'flatpak.info.arch',
                                                                       'flatpak.info.ref',
                                                                       'flatpak.info.origin',
                                                                       'manage_window.columns.update']]
        self.manager = manager
        self.tray_icon = tray_icon
        self.thread_lock = Lock()
        self.working = False  # restrict the number of threaded actions
        self.apps = []
        self.label_flatpak = None

        self.icon_flathub = QIcon(resource.get_path('img/flathub_45.svg'))
        self._check_flatpak_installed()
        self.resize(ManageWindow.__BASE_HEIGHT__, ManageWindow.__BASE_HEIGHT__)
        self.setWindowTitle(locale_keys['manage_window.title'])
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
        self.label_status.setStyleSheet("color: orange")
        toolbar.addWidget(self.label_status)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        toolbar.addWidget(spacer)

        self.bt_refresh = QToolButton()
        self.bt_refresh.setToolTip(locale_keys['manage_window.bt.refresh.tooltip'])
        self.bt_refresh.setIcon(QIcon(resource.get_path('img/refresh.svg')))
        self.bt_refresh.clicked.connect(lambda: self.refresh(clear_output=True))
        toolbar.addWidget(self.bt_refresh)

        self.bt_upgrade = QToolButton()
        self.bt_upgrade.setToolTip(locale_keys['manage_window.bt.upgrade.tooltip'])
        self.bt_upgrade.setIcon(QIcon(resource.get_path('img/update_green.svg')))
        self.bt_upgrade.setEnabled(False)
        self.bt_upgrade.clicked.connect(self.update_selected)
        toolbar.addWidget(self.bt_upgrade)

        self.layout.addWidget(toolbar)

        self.table_apps = AppsTable(self, self.column_names)
        self.table_apps.change_headers_policy()

        self.layout.addWidget(self.table_apps)

        self.textarea_output = QPlainTextEdit(self)
        self.textarea_output.resize(self.table_apps.size())
        self.textarea_output.setStyleSheet("background: black; color: white;")
        self.layout.addWidget(self.textarea_output)
        self.textarea_output.setVisible(False)
        self.textarea_output.setReadOnly(True)

        self.thread_update = UpdateSelectedApps()
        self.thread_update.signal_output.connect(self._update_action_output)
        self.thread_update.signal_finished.connect(self._finish_update_selected)

        self.thread_refresh = RefreshApps(self.manager)
        self.thread_refresh.signal.connect(self._finish_refresh)

        self.thread_uninstall = UninstallApp()
        self.thread_uninstall.signal_output.connect(self._update_action_output)
        self.thread_uninstall.signal_finished.connect(self._finish_uninstall)

        self.thread_downgrade = DowngradeApp(self.manager, self.locale_keys)
        self.thread_downgrade.signal_output.connect(self._update_action_output)
        self.thread_downgrade.signal_finished.connect(self._finish_downgrade)

        self.thread_get_info = GetAppInfo()
        self.thread_get_info.signal_finished.connect(self._finish_get_info)

        self.thread_get_history = GetAppHistory()
        self.thread_get_history.signal_finished.connect(self._finish_get_history)

        self.toolbar_bottom = QToolBar()
        self.label_updates = QLabel('')
        self.label_updates.setStyleSheet("color: red;")
        self.toolbar_bottom.addWidget(self.label_updates)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.toolbar_bottom.addWidget(spacer)

        self.label_flatpak = QLabel(self._get_flatpak_label())
        self.toolbar_bottom.addWidget(self.label_flatpak)
        self.layout.addWidget(self.toolbar_bottom)

        self.centralize()

    def changeEvent(self, e: QEvent):

        if isinstance(e, QWindowStateChangeEvent):
            policy = QHeaderView.Stretch if self.isMaximized() else QHeaderView.ResizeToContents
            self.table_apps.change_headers_policy(policy)

    def closeEvent(self, event):

        if self.tray_icon:
            event.ignore()
            self.hide()

    def _check_flatpak_installed(self):

        if not flatpak.is_installed():
            dialog.show_error(title=self.locale_keys['popup.flatpak_not_installed.title'],
                              body=self.locale_keys['popup.flatpak_not_installed.msg'] + '...',
                              icon=self.icon_flathub)
            exit(1)

        if self.label_flatpak:
            self.label_flatpak.setText(self._get_flatpak_label())

    def _get_flatpak_label(self):
        return 'flatpak: ' + flatpak.get_version()

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

    def refresh(self, clear_output: bool = True):

        if self._acquire_lock():
            self._check_flatpak_installed()
            self._begin_action(self.locale_keys['manage_window.status.refreshing'])

            if clear_output:
                self.textarea_output.clear()
                self.textarea_output.hide()

            self.thread_refresh.start()

    def _finish_refresh(self, apps: List[dict]):

        self.update_apps(apps)
        self.finish_action()
        self._release_lock()

    def uninstall_app(self, app_ref: str):
        self._check_flatpak_installed()

        if self._acquire_lock():
            self.textarea_output.clear()
            self.textarea_output.setVisible(True)
            self._begin_action(self.locale_keys['manage_window.status.uninstalling'])

            self.thread_uninstall.app_ref = app_ref
            self.thread_uninstall.start()

    def _finish_uninstall(self):
        self.finish_action()
        self._release_lock()
        self.refresh(clear_output=False)

    def _finish_downgrade(self):
        self.finish_action()
        self._release_lock()
        self.refresh(clear_output=False)

    def filter_only_apps(self, only_apps: int):

        if self.apps:
            show_only_apps = True if only_apps == 2 else False

            for idx, app in enumerate(self.apps):
                hidden = show_only_apps and app['model']['runtime']
                self.table_apps.setRowHidden(idx, hidden)
                app['visible'] = not hidden

            self.change_update_state()
            self.table_apps.change_headers_policy(QHeaderView.Stretch)
            self.table_apps.change_headers_policy()
            self.resize_and_center()

    def change_update_state(self):

        enable_bt_update = False

        app_updates, runtime_updates = 0, 0

        for app in self.apps:
            if app['model']['update']:
                if app['model']['runtime']:
                    runtime_updates += 1
                else:
                    app_updates += 1

        total_updates = app_updates + runtime_updates
        if total_updates > 0:
            self.label_updates.setText('{}: {} ( {} {} | {} runtimes )'.format(self.locale_keys['manage_window.label.updates'],
                                                                               total_updates,
                                                                               app_updates,
                                                                               self.locale_keys['manage_window.checkbox.only_apps'].lower(),
                                                                               runtime_updates))
        else:
            self.label_updates.setText('')

        for app in self.apps:
            if app['visible'] and app['update_checked']:
                enable_bt_update = True
                break

        self.bt_upgrade.setEnabled(enable_bt_update)

        self.tray_icon.notify_updates(total_updates)

    def centralize(self):
        geo = self.frameGeometry()
        screen = QApplication.desktop().screenNumber(QApplication.desktop().cursor().pos())
        center_point = QApplication.desktop().screenGeometry(screen).center()
        geo.moveCenter(center_point)
        self.move(geo.topLeft())

    def update_apps(self, apps: List[dict]):
        self._check_flatpak_installed()

        self.apps = []

        napps = 0  # number of apps (not runtimes)

        if apps:
            for app in apps:
                app_model = {'model': app,
                             'update_checked': app['update'],
                             'visible': not app['runtime'] or not self.checkbox_only_apps.isChecked()}

                napps += 1 if not app['runtime'] else 0
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

    def resize_and_center(self):
        new_width = reduce(operator.add, [self.table_apps.columnWidth(i) for i in range(len(self.column_names))]) * 1.05
        self.resize(new_width, self.height())
        self.centralize()

    def update_selected(self):

        if self._acquire_lock():
            if self.apps:

                to_update = [pak['model']['ref'] for pak in self.apps if pak['visible'] and pak['update_checked']]

                if to_update:
                    self.textarea_output.clear()
                    self.textarea_output.setVisible(True)

                    self._begin_action(self.locale_keys['manage_window.status.upgrading'])
                    self.thread_update.refs_to_update = to_update
                    self.thread_update.start()

    def _finish_update_selected(self):
        self.finish_action()
        self._release_lock()
        self.refresh(clear_output=False)

    def _update_action_output(self, output: str):
        self.textarea_output.appendPlainText(output)

    def _begin_action(self, action_label: str):
        self.label_status.setText(action_label + "...")
        self.bt_upgrade.setEnabled(False)
        self.bt_refresh.setEnabled(False)
        self.checkbox_only_apps.setEnabled(False)
        self.table_apps.setEnabled(False)

    def finish_action(self):
        self.bt_refresh.setEnabled(True)
        self.checkbox_only_apps.setEnabled(True)
        self.table_apps.setEnabled(True)
        self.label_status.setText('')

    def downgrade_app(self, app: dict):

        self._check_flatpak_installed()

        if self._acquire_lock():

            pwd = None

            if not is_root():
                pwd, ok = ask_root_password(self.locale_keys)

                if not ok:
                    self._release_lock()
                    return

            self.textarea_output.clear()
            self.textarea_output.setVisible(True)
            self._begin_action(self.locale_keys['manage_window.status.downgrading'])

            self.thread_downgrade.app = app
            self.thread_downgrade.root_password = pwd
            self.thread_downgrade.start()

    def get_app_info(self, app: dict):

        if self._acquire_lock():
            self.textarea_output.clear()
            self.textarea_output.setVisible(False)
            self._begin_action(self.locale_keys['manage_window.status.info'])

            self.thread_get_info.app = app
            self.thread_get_info.start()

    def get_app_history(self, app: dict):
        if self._acquire_lock():
            self.textarea_output.clear()
            self.textarea_output.setVisible(False)
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
        dialog_history = HistoryDialog(app, self.table_apps.get_selected_app_icon(), self.locale_keys)
        dialog_history.exec_()
