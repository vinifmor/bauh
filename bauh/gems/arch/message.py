from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.view import MessageType


def show_dep_not_installed(watcher: ProcessWatcher, pkgname: str, depname: str, i18n: dict):
    watcher.show_message(title=i18n['error'],
                         body=i18n['arch.install.dependency.install.error'].format('"{}"'.format(depname), '"{}"'.format(pkgname)),
                         type_=MessageType.ERROR)


def show_dep_not_found(depname: str, i18n: dict, watcher: ProcessWatcher):
    watcher.show_message(title=i18n['arch.install.dep_not_found.title'],
                         body=i18n['arch.install.dep_not_found.body'].format('"{}"'.format(depname)),
                         type_=MessageType.ERROR)


def show_optdep_not_installed(depname: str, watcher: ProcessWatcher, i18n: dict):
    watcher.show_message(title=i18n['error'],
                         body=i18n['arch.install.optdep.error'].format('"{}"'.format(depname)),
                         type_=MessageType.ERROR)
