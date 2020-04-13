from typing import Iterable

from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.view import MessageType
from bauh.commons.html import bold
from bauh.view.util.translation import I18n


def show_deps_not_installed(watcher: ProcessWatcher, pkgname: str, depnames: Iterable[str], i18n: I18n):
    deps = ', '.join((bold(d) for d in depnames))
    watcher.show_message(title=i18n['error'].capitalize(),
                         body=i18n['arch.install.dependency.install.error'].format(deps, bold(pkgname)),
                         type_=MessageType.ERROR)


def show_dep_not_found(depname: str, i18n: I18n, watcher: ProcessWatcher):

    body = '<p>{}</p><p>{}</p><p></p><p>{}</p>'.format(i18n['arch.install.dep_not_found.body.l1'].format(bold(depname)),
                                                       i18n['arch.install.dep_not_found.body.l2'],
                                                       i18n['arch.install.dep_not_found.body.l3'])

    watcher.show_message(title=i18n['arch.install.dep_not_found.title'].capitalize(),
                         body=body,
                         type_=MessageType.ERROR)


def show_optdeps_not_installed(depnames: Iterable[str], watcher: ProcessWatcher, i18n: I18n):
    deps = ', '.join((bold(d) for d in depnames))
    watcher.show_message(title=i18n['error'].capitalize(),
                         body=i18n['arch.install.optdep.error'].format(deps),
                         type_=MessageType.ERROR)
