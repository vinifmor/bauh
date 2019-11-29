import os

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QInputDialog, QLineEdit

from bauh.api.abstract.view import MessageType
from bauh.commons.system import new_subprocess
from bauh.view.qt.dialog import show_message
from bauh.view.util import resource
from bauh.view.util.translation import I18n


def is_root():
    return os.getuid() == 0


def ask_root_password(i18n: I18n):
    diag = QInputDialog()
    diag.setStyleSheet("""QLineEdit {  border-radius: 5px; font-size: 16px; border: 1px solid lightblue }""")
    diag.setInputMode(QInputDialog.TextInput)
    diag.setTextEchoMode(QLineEdit.Password)
    diag.setWindowIcon(QIcon(resource.get_path('img/lock.png')))
    diag.setWindowTitle(i18n['popup.root.title'])
    diag.setLabelText('')
    diag.setOkButtonText(i18n['popup.root.continue'].capitalize())
    diag.setCancelButtonText(i18n['popup.button.cancel'].capitalize())
    diag.resize(400, 200)

    for attempt in range(3):

        ok = diag.exec_()

        if ok:
            if not validate_password(diag.textValue()):

                body = i18n['popup.root.bad_password.body']

                if attempt == 2:
                    body += '. ' + i18n['popup.root.bad_password.last_try']

                show_message(title=i18n['popup.root.bad_password.title'],
                             body=body,
                             type_=MessageType.ERROR)
                ok = False
                diag.setTextValue('')

            if ok:
                return diag.textValue(), ok
        else:
            break

    return '', False


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
