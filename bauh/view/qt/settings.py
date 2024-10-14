import gc
from io import StringIO
from typing import Optional

from PyQt6.QtCore import Qt, QCoreApplication, QThread, pyqtSignal
from PyQt6.QtGui import QCursor, QShowEvent
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy, QPushButton, QHBoxLayout, QApplication

from bauh import __app_name__
from bauh.api.abstract.controller import SoftwareManager
from bauh.api.abstract.view import MessageType
from bauh.view.core.controller import GenericSoftwareManager
from bauh.view.qt import dialog
from bauh.view.qt.components import to_widget, new_spacer
from bauh.view.qt.dialog import ConfirmationDialog
from bauh.view.qt.qt_utils import centralize
from bauh.view.util import util
from bauh.view.util.translation import I18n


class ReloadManagePanel(QThread):

    signal_finished = pyqtSignal()

    def __init__(self, manager: SoftwareManager):
        super(ReloadManagePanel, self).__init__()
        self.manager = manager

    def run(self):
        if isinstance(self.manager, GenericSoftwareManager):
            self.manager.reset_cache()

        self.manager.prepare(task_manager=None, root_password=None, internet_available=None)
        self.signal_finished.emit()


class SettingsWindow(QWidget):

    def __init__(self, manager: SoftwareManager, i18n: I18n, window: QWidget, parent: Optional[QWidget] = None):
        super(SettingsWindow, self).__init__(parent=parent, flags=Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)
        self.setWindowTitle(f"{i18n['settings'].capitalize()} ({__app_name__})")
        self.setLayout(QVBoxLayout())
        self.manager = manager
        self.i18n = i18n
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        self.window = window

        self.settings_model = tuple(v for v in self.manager.get_settings())[0].component

        self.tab_group = to_widget(self.settings_model, i18n)
        self.tab_group.setObjectName('settings')
        self.layout().addWidget(self.tab_group)

        lower_container = QWidget()
        lower_container.setObjectName('lower_container')
        lower_container.setProperty('container', 'true')
        lower_container.setLayout(QHBoxLayout())
        lower_container.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        self.bt_close = QPushButton()
        self.bt_close.setObjectName('cancel')
        self.bt_close.setAutoDefault(True)
        self.bt_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.bt_close.setText(self.i18n['close'].capitalize())
        self.bt_close.clicked.connect(lambda: self.close())
        lower_container.layout().addWidget(self.bt_close)

        lower_container.layout().addWidget(new_spacer())

        self.bt_change = QPushButton()
        self.bt_change.setAutoDefault(True)
        self.bt_change.setObjectName('ok')
        self.bt_change.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.bt_change.setText(self.i18n['change'].capitalize())
        self.bt_change.clicked.connect(self._save_settings)
        lower_container.layout().addWidget(self.bt_change)

        self.layout().addWidget(lower_container)

        self.thread_reload_panel = ReloadManagePanel(manager=manager)
        self.thread_reload_panel.signal_finished.connect(self._reload_manage_panel)
        centralize(self)

    def showEvent(self, event: Optional[QShowEvent]):
        super(SettingsWindow, self).showEvent(event)
        self.setMinimumWidth(int(self.sizeHint().width()))
        centralize(self)

    def closeEvent(self, event):
        if self.window and self.window.settings_window == self:
            self.deleteLater()
            self.window.settings_window = None
        elif not self.window:
            QCoreApplication.exit()

        gc.collect()

    def handle_display(self):
        if self.isMinimized():
            self.setWindowState(Qt.WindowState.WindowNoState)
        elif self.isHidden():
            self.show()
        else:
            self.setWindowState(self.windowState() and Qt.WindowState.WindowMinimized or Qt.WindowState.WindowActive)

    def _save_settings(self):
        self.tab_group.setEnabled(False)
        self.bt_change.setEnabled(False)
        self.bt_close.setEnabled(False)

        success, warnings = self.manager.save_settings(self.settings_model)

        if success:
            if not self.window:
                ConfirmationDialog(title=self.i18n['success'].capitalize(),
                                   body=f"<p>{self.i18n['settings.changed.success.warning']}</p>",
                                   i18n=self.i18n,
                                   confirmation_label=self.i18n['ok'],
                                   confirmation_icon=False,
                                   deny_button=False).ask()
                QCoreApplication.exit()
            elif ConfirmationDialog(title=self.i18n['warning'].capitalize(),
                                    body=f"<p>{self.i18n['settings.changed.success.warning']}</p>"
                                         f"<p>{self.i18n['settings.changed.success.reboot']}</p>",
                                    i18n=self.i18n).ask():
                self.close()
                util.restart_app()
            else:
                self.thread_reload_panel.start()
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            msg = StringIO()
            msg.write(f"<p>{self.i18n['settings.error']}</p>")

            for w in warnings:
                msg.write(f'<p style="font-weight: bold">* {w}</p><br/>')

            dialog.show_message(title=self.i18n['warning'].capitalize(), body=msg.getvalue(), type_=MessageType.WARNING)

            self.tab_group.setEnabled(True)
            self.bt_change.setEnabled(True)
            self.bt_close.setEnabled(True)

    def _reload_manage_panel(self):
        if self.window and self.window.isVisible():
            self.window.reload()

        QApplication.restoreOverrideCursor()
        self.close()
