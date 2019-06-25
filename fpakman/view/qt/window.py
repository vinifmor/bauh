import operator
from functools import reduce
from threading import Lock
from typing import List

from PyQt5.QtCore import QThread, pyqtSignal, QEvent
from PyQt5.QtGui import QIcon, QWindowStateChangeEvent
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QApplication, QCheckBox, QHeaderView, QToolButton, QToolBar, \
    QSizePolicy, QLabel, QMessageBox, QPlainTextEdit

from fpakman import __version__
from fpakman.core import resource
from fpakman.core.controller import FlatpakController
from fpakman.view.qt.apps_table import AppsTable


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
        self.tray_icon = tray_icon
        self.thread_lock = Lock()
        self.working = False  # restrict the number of threaded actions
        self.apps = []
        self.label_flatpak = None

        self.icon_flathub = QIcon(resource.get_path('img/flathub_45.svg'))
        self._check_flatpak_installed()
        self.resize(ManageWindow.__BASE_HEIGHT__, ManageWindow.__BASE_HEIGHT__)
        self.setWindowTitle('{} ({})'.format(locale_keys['manage_window.title'], __version__))
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

        self.table_apps = AppsTable(self, self.controller, self.column_names)
        self.table_apps.change_headers_policy()

        self.layout.addWidget(self.table_apps)

        self.textarea_output = QPlainTextEdit(self)
        self.textarea_output.resize(self.table_apps.size())
        self.textarea_output.setStyleSheet("background: black; color: white;")
        self.layout.addWidget(self.textarea_output)
        self.textarea_output.setVisible(False)
        self.textarea_output.setReadOnly(True)

        self.thread_update = UpdateSelectedApps(self.controller)
        self.thread_update.signal_output.connect(self._update_action_output)
        self.thread_update.signal_finished.connect(self._finish_update_selected)

        self.thread_refresh = RefreshApps(self.controller)
        self.thread_refresh.signal.connect(self._finish_refresh)

        self.thread_uninstall = UninstallApp(self.controller)
        self.thread_uninstall.signal_output.connect(self._update_action_output)
        self.thread_uninstall.signal_finished.connect(self._finish_uninstall)

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

    def changeEvent(self, e: QEvent):

        if isinstance(e, QWindowStateChangeEvent):
            policy = QHeaderView.Stretch if self.isMaximized() else QHeaderView.ResizeToContents
            self.table_apps.change_headers_policy(policy)

    def closeEvent(self, event):

        if self.tray_icon:
            event.ignore()
            self.hide()

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

    def refresh(self, clear_output: bool = True):

        if self._acquire_lock():
            self._check_flatpak_installed()
            self._begin_action(self.locale_keys['manage_window.status.refreshing'] + '...')

            if clear_output:
                self.textarea_output.clear()
                self.textarea_output.hide()

            self.thread_refresh.start()

    def _finish_refresh(self):

        self.update_apps(self.thread_refresh.apps)
        self.finish_action()
        self._release_lock()

    def uninstall_app(self, app_ref: str):
        self._check_flatpak_installed()

        if self._acquire_lock():
            self.textarea_output.clear()
            self.textarea_output.setVisible(True)
            self._begin_action(self.locale_keys['manage_window.status.uninstalling'] + '...')

            self.thread_uninstall.app_ref = app_ref
            self.thread_uninstall.start()

    def _finish_uninstall(self):
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
            self.label_updates.setText('{}: {} ( {} apps | {} runtimes )'.format(self.locale_keys['manage_window.label.updates'], total_updates, app_updates, runtime_updates))
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

                    self._begin_action(self.locale_keys['manage_window.status.updating'] + '...')
                    self.thread_update.refs_to_update = to_update
                    self.thread_update.start()

    def _finish_update_selected(self):
        self.finish_action()
        self._release_lock()
        self.refresh(clear_output=False)

    def _update_action_output(self, output: str):
        self.textarea_output.appendPlainText(output)

    def _begin_action(self, action_label: str):
        self.label_status.setText(action_label)
        self.bt_upgrade.setEnabled(False)
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

    signal_finished = pyqtSignal()
    signal_output = pyqtSignal(str)

    def __init__(self, controller: FlatpakController):
        super(UpdateSelectedApps, self).__init__()
        self.controller = controller
        self.refs_to_update = []

    def run(self):

        for app_ref in self.refs_to_update:
            for output in self.controller.update(app_ref):
                line = output.decode().strip()
                if line:
                    self.signal_output.emit(line)

        self.signal_finished.emit()


class RefreshApps(QThread):

    signal = pyqtSignal()

    def __init__(self, controller: FlatpakController):
        super(RefreshApps, self).__init__()
        self.controller = controller
        self.apps = None

    def run(self):
        self.apps = self.controller.refresh()
        self.signal.emit()


class UninstallApp(QThread):
    signal_finished = pyqtSignal()
    signal_output = pyqtSignal(str)

    def __init__(self, controller: FlatpakController):
        super(UninstallApp, self).__init__()
        self.controller = controller
        self.app_ref = None

    def run(self):
        if self.app_ref:
            for output in self.controller.uninstall(self.app_ref):
                line = output.decode().strip()
                if line:
                    self.signal_output.emit(line)

            self.signal_finished.emit()
