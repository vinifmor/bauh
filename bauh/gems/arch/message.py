from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.view import MessageType
from bauh.commons.html import bold
from bauh.view.util.translation import I18n


def show_dep_not_installed(watcher: ProcessWatcher, pkgname: str, depname: str, i18n: I18n):
    watcher.show_message(title=i18n['error'],
                         body=i18n['arch.install.dependency.install.error'].format(bold(depname), bold(pkgname)),
                         type_=MessageType.ERROR)


def show_dep_not_found(depname: str, i18n: I18n, watcher: ProcessWatcher):
    watcher.show_message(title=i18n['arch.install.dep_not_found.title'],
                         body=i18n['arch.install.dep_not_found.body'].format(bold(depname)),
                         type_=MessageType.ERROR)


def show_optdep_not_installed(depname: str, watcher: ProcessWatcher, i18n: I18n):
    watcher.show_message(title=i18n['error'],
                         body=i18n['arch.install.optdep.error'].format(bold(depname)),
                         type_=MessageType.ERROR)
