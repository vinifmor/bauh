from typing import Set

from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.view import MultipleSelectComponent, InputOption

from bauh.commons.html import bold


def request_optional_deps(pkgname: str, pkg_mirrors: dict, watcher: ProcessWatcher, i18n: dict) -> Set[str]:
    opts = [InputOption('{}{} ( {} )'.format(p, ': ' + d['desc'] if d['desc'] else '', d['mirror'].upper()), p) for p, d in pkg_mirrors.items()]
    view_opts = MultipleSelectComponent(label='',
                                        options=opts,
                                        default_options=set(opts))
    install = watcher.request_confirmation(title=i18n['arch.install.optdeps.request.title'],
                                           body='<p>{}</p>'.format(i18n['arch.install.optdeps.request.body'].format(bold(pkgname)) + ':'),
                                           components=[view_opts],
                                           confirmation_label=i18n['install'],
                                           deny_label=i18n['cancel'])

    if install:
        return {o.value for o in view_opts.values}


def request_install_missing_deps(pkgname: str, pkg_mirrors: dict, watcher: ProcessWatcher, i18n: dict) -> bool:
    deps_str = ''.join(['<br/><span style="font-weight:bold">  - {} ( {} )</span>'.format(d, m.upper()) for d, m in pkg_mirrors.items()])
    msg = '<p>{}</p>'.format(i18n['arch.missing_deps.body'].format(bold(pkgname)) + ':<br/>' + deps_str)
    msg += i18n['ask.continue']

    return watcher.request_confirmation(i18n['arch.missing_deps.title'], msg)
