import os
import traceback
from typing import Tuple, Optional

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QLineEdit, QApplication, QDialog, QPushButton, QVBoxLayout, \
    QSizePolicy, QToolBar, QLabel

from bauh.api.abstract.context import ApplicationContext
from bauh.commons.system import new_subprocess
from bauh.view.core.config import CoreConfigManager
from bauh.view.qt.components import QtComponentsManager, new_spacer
from bauh.view.util import util
from bauh.view.util.translation import I18n

ACTION_ASK_ROOT = 99


class ValidatePassword(QThread):

    signal_valid = pyqtSignal(bool)

    def __init__(self, password: Optional[str] = None):
        super(ValidatePassword, self).__init__()
        self.password = password

    def run(self):
        if self.password is not None:
            try:
                valid = validate_password(self.password)
            except:
                traceback.print_exc()
                valid = False

            self.signal_valid.emit(valid)


class RootDialog(QDialog):

    def __init__(self, i18n: I18n, max_tries: int = 3):
        super(RootDialog, self).__init__(flags=Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self.i18n = i18n
        self.max_tries = max_tries
        self.tries = 0
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        self.setWindowIcon(util.get_default_icon()[1])
        self.setWindowTitle(i18n['popup.root.title'])
        self.setLayout(QVBoxLayout())
        self.setMinimumWidth(300)

        self.label_msg = QLabel(i18n['popup.root.msg'])
        self.label_msg.setObjectName('message')
        self.layout().addWidget(self.label_msg)

        self.input_password = QLineEdit()
        self.input_password.setObjectName('password')
        self.layout().addWidget(self.input_password)

        self.label_error = QLabel()
        self.label_error.setProperty('error', 'true')
        self.layout().addWidget(self.label_error)
        self.label_error.hide()

        self.lower_bar = QToolBar()
        self.layout().addWidget(self.lower_bar)

        self.lower_bar.addWidget(new_spacer())
        self.bt_ok = QPushButton(i18n['popup.root.continue'])
        self.bt_ok.setDefault(True)
        self.bt_ok.setAutoDefault(True)
        self.bt_ok.setCursor(QCursor(Qt.PointingHandCursor))
        self.bt_ok.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.bt_ok.setObjectName('ok')
        self.bt_ok.clicked.connect(self._validate_password)
        self.lower_bar.addWidget(self.bt_ok)

        self.bt_cancel = QPushButton()
        self.bt_cancel.setText(i18n['popup.button.cancel'])

        self.bt_cancel.setCursor(QCursor(Qt.PointingHandCursor))
        self.bt_cancel.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.bt_cancel.setObjectName('bt_cancel')
        self.bt_cancel.clicked.connect(self.close)
        self.lower_bar.addWidget(self.bt_cancel)
        self.lower_bar.addWidget(new_spacer())

        self.valid = False
        self.password = None
        self.validate_password = ValidatePassword()
        self.validate_password.signal_valid.connect(self._handle_password_validated)

    def _validate_password(self):
        password = self.input_password.text().strip()

        if password:
            self.password = password
            self.tries += 1
            self.bt_ok.setEnabled(False)
            self.bt_cancel.setEnabled(False)
            self.input_password.setEnabled(False)
            self.label_error.setText('')

            QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
            self.validate_password.password = password
            self.validate_password.start()

    def _handle_password_validated(self, valid: bool):
        self.valid = valid

        QApplication.restoreOverrideCursor()
        tries_ended = self.tries == self.max_tries

        if not self.valid:
            self.label_error.show()
            self.bt_cancel.setEnabled(True)

            if tries_ended:
                self.bt_cancel.setText(self.i18n['close'].capitalize())
                self.label_error.setText(self.i18n['popup.root.bad_password.last_try'])
                self.bt_cancel.setFocus()
            else:
                self.label_error.setText(self.i18n['popup.root.bad_password.body'])
                self.bt_ok.setEnabled(True)
                self.input_password.setEnabled(True)
                self.input_password.setFocus()
        else:
            self.close()

    @staticmethod
    def ask_password(context: ApplicationContext, i18n: I18n, app_config: Optional[dict] = None,
                     comp_manager: Optional[QtComponentsManager] = None, tries: int = 3) -> Tuple[bool, Optional[str]]:

        current_config = CoreConfigManager().get_config() if not app_config else app_config

        store_password = bool(current_config['store_root_password'])

        if store_password and context.root_password and validate_password(context.root_password):
            return True, context.root_password

        if comp_manager:
            comp_manager.save_states(state_id=ACTION_ASK_ROOT, only_visible=True)
            comp_manager.disable_visible()

        diag = RootDialog(i18n=i18n, max_tries=tries)
        diag.exec()
        password = diag.password

        if comp_manager:
            comp_manager.restore_state(ACTION_ASK_ROOT)

        if password is not None and store_password:
            context.root_password = password

        return (True, password) if diag.valid else (False, None)


def is_root():
    return os.getuid() == 0


def validate_password(password: str) -> bool:
    clean = new_subprocess(['sudo', '-k']).stdout
    echo = new_subprocess(['echo', password], stdin=clean).stdout

    validate = new_subprocess(['sudo', '-S', '-v'], stdin=echo)

    for o in validate.stdout:
        pass

    for o in validate.stderr:
        if o:
            line = o.decode()

            if 'incorrect password attempt' in line:
                return False

    return True
