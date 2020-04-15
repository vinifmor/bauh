import os
from typing import Tuple

from PyQt5.QtWidgets import QInputDialog, QLineEdit

from bauh.api.abstract.context import ApplicationContext
from bauh.api.abstract.view import MessageType
from bauh.commons.system import new_subprocess
from bauh.view.core.config import read_config
from bauh.view.qt.dialog import show_message
from bauh.view.qt.view_utils import load_resource_icon
from bauh.view.util import util
from bauh.view.util.translation import I18n


def is_root():
    return os.getuid() == 0


def ask_root_password(context: ApplicationContext, i18n: I18n, app_config: dict = None) -> Tuple[str, bool]:

    cur_config = read_config() if not app_config else app_config
    store_password = bool(cur_config['store_root_password'])

    if store_password and context.root_password and validate_password(context.root_password):
        return context.root_password, True

    diag = QInputDialog()
    diag.setStyleSheet("""QLineEdit {  border-radius: 5px; font-size: 16px; border: 1px solid lightblue }""")
    diag.setInputMode(QInputDialog.TextInput)
    diag.setTextEchoMode(QLineEdit.Password)
    diag.setWindowIcon(util.get_default_icon()[1])
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
                if store_password:
                    context.root_password = diag.textValue()

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
