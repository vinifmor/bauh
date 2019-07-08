from fpakman.core import flatpak
from fpakman.view.qt import dialog


def check_flatpak_installed(locale_keys: dict):

    if not flatpak.is_installed():
        dialog.show_error(title=locale_keys['popup.flatpak_not_installed.title'],
                          body=locale_keys['popup.flatpak_not_installed.msg'] + '...')
        exit(1)
