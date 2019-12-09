from typing import Set, List, Tuple

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
        op = InputOption('{}{} ( {}: {} )'.format(p, ': ' + d['desc'] if d['desc'] else '', i18n['repository'], d['mirror'].upper()), p)
        op.icon_path = _get_mirror_icon(d['mirror'])
        opts.append(op)

    view_opts = MultipleSelectComponent(label='',
                                        options=opts,
                                        default_options=None)

    install = watcher.request_confirmation(title=i18n['arch.install.optdeps.request.title'],
                                           body='<p>{}.</p><p>{}:</p>'.format(i18n['arch.install.optdeps.request.body'].format(bold(pkgname)), i18n['arch.install.optdeps.request.help']),
                                           components=[view_opts],
                                           confirmation_label=i18n['install'].capitalize(),
                                           deny_label=i18n['do_not.install'].capitalize())

    if install:
        return {o.value for o in view_opts.values}


def request_install_missing_deps(pkgname: str, deps: List[Tuple[str, str]], watcher: ProcessWatcher, i18n: I18n) -> bool:
    msg = '<p>{}</p>'.format(i18n['arch.missing_deps.body'].format(name=bold(pkgname) if pkgname else '', deps=bold(str(len(deps)))))

    opts = []

    sorted_deps = [*deps]
    sorted_deps.sort(key=lambda e: e[0])

    for dep in sorted_deps:
        op = InputOption('{} ( {}: {} )'.format(dep[0], i18n['repository'], dep[1].upper()), dep[0])
        op.read_only = True
        op.icon_path = _get_mirror_icon(dep[1])
        opts.append(op)

    comp = MultipleSelectComponent(label='', options=opts, default_options=set(opts))

    return watcher.request_confirmation(i18n['arch.missing_deps.title'], msg, [comp], confirmation_label=i18n['continue'].capitalize(), deny_label=i18n['cancel'].capitalize())
