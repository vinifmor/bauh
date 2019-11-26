from typing import Set

from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.view import MultipleSelectComponent, InputOption
from bauh.commons import resource
from bauh.commons.html import bold
from bauh.gems.arch import ROOT_DIR
from bauh.view.util.translation import I18n


def _get_mirror_icon(mirror: str):
    return resource.get_path('img/{}.png'.format('arch' if mirror == 'aur' else 'mirror'), ROOT_DIR)


def request_optional_deps(pkgname: str, pkg_mirrors: dict, watcher: ProcessWatcher, i18n: I18n) -> Set[str]:
    opts = []

    for p, d in pkg_mirrors.items():
        op = InputOption('{}{} ( {}: {} )'.format(p, ': ' + d['desc'] if d['desc'] else '', i18n['mirror'], d['mirror'].upper()), p)
        op.icon_path = _get_mirror_icon(d['mirror'])
        opts.append(op)

    view_opts = MultipleSelectComponent(label='',
                                        options=opts,
                                        default_options=None)

    install = watcher.request_confirmation(title=i18n['arch.install.optdeps.request.title'],
                                           body='<p>{}</p>'.format(i18n['arch.install.optdeps.request.body'].format(bold(pkgname)) + ':'),
                                           components=[view_opts],
                                           confirmation_label=i18n['install'],
                                           deny_label=i18n['cancel'])

    if install:
        return {o.value for o in view_opts.values}


def request_install_missing_deps(pkgname: str, pkg_mirrors: dict, watcher: ProcessWatcher, i18n: I18n) -> bool:
    msg = '<p>{}</p>'.format(i18n['arch.missing_deps.body'].format(bold(pkgname)) + ':')

    opts = []
    for p, m in pkg_mirrors.items():
        op = InputOption('{} ( {}: {} )'.format(p, i18n['mirror'], m.upper()), p)
        op.read_only = True
        op.icon_path = _get_mirror_icon(m)
        opts.append(op)

    comp = MultipleSelectComponent(label='', options=opts, default_options=set(opts))

    return watcher.request_confirmation(i18n['arch.missing_deps.title'], msg, [comp], confirmation_label=i18n['continue'].capitalize())
