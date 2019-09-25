import os

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QInputDialog, QLineEdit

from bauh.api.abstract.view import MessageType
from bauh.commons.system import new_subprocess
from bauh.view.qt.dialog import show_message
from bauh.view.util import resource


def is_root():
    return os.getuid() == 0


def ask_root_password(locale_keys: dict):

    diag = QInputDialog()
    diag.setInputMode(QInputDialog.TextInput)
    diag.setTextEchoMode(QLineEdit.Password)
    diag.setWindowIcon(QIcon(resource.get_path('img/lock.svg')))
    diag.setWindowTitle(locale_keys['popup.root.title'])
    diag.setLabelText(locale_keys['popup.root.password'] + ':')
    diag.setCancelButtonText(locale_keys['popup.button.cancel'])
    diag.resize(400, 200)

    ok = diag.exec_()

    if ok:
        if not validate_password(diag.textValue()):
            show_message(title=locale_keys['popup.root.bad_password.title'],
                         body=locale_keys['popup.root.bad_password.body'],
                         type_=MessageType.ERROR)
            ok = False

    return diag.textValue(), ok


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
