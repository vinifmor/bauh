import os
import subprocess

from PyQt5.QtWidgets import QInputDialog, QLineEdit

from fpakman.view.qt.dialog import show_error


def is_root():
    return os.getuid() == 0


def ask_root_password(locale_keys: dict):

    dialog_pwd = QInputDialog()
    dialog_pwd.setInputMode(QInputDialog.TextInput)
    dialog_pwd.setTextEchoMode(QLineEdit.Password)
    dialog_pwd.setWindowTitle(locale_keys['popup.root.title'])
    dialog_pwd.setLabelText(locale_keys['popup.root.password'] + ':')
    dialog_pwd.setCancelButtonText(locale_keys['popup.button.cancel'])
    dialog_pwd.resize(400, 200)

    ok = dialog_pwd.exec_()

    if ok:
        if not validate_password(dialog_pwd.textValue()):
            show_error(title=locale_keys['popup.root.bad_password.title'],
                       body=locale_keys['popup.root.bad_password.body'])
            ok = False

    return dialog_pwd.textValue(), ok


def validate_password(password: str) -> bool:
    f = os.popen('echo {} | sudo -S whoami'.format(password))
    res = f.read()
    f.close()

    return bool(res.strip())
