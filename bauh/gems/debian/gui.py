from operator import attrgetter
from typing import Collection, Optional, Tuple, List

from bauh.api.abstract.handler import ProcessWatcher
from bauh.api.abstract.view import InputOption, MultipleSelectComponent, TextComponent
from bauh.commons.html import bold
from bauh.commons.view_utils import get_human_size_str
from bauh.gems.debian import DEBIAN_ICON_PATH
from bauh.gems.debian.model import DebianPackage
from bauh.view.util.translation import I18n


class DebianViewBridge:

    def __init__(self, screen_width: int, screen_heigth: int, i18n: I18n):
        self._i18n = i18n
        self._width = screen_width
        self._height = screen_heigth

    @staticmethod
    def _map_to_install(pkgs: Optional[Collection[DebianPackage]]) -> Optional[Tuple[List[InputOption], str, str]]:
        if pkgs:
            download_size, install_size = 0, 0

            views = []
            for p in pkgs:
                if p.compressed_size is not None and p.compressed_size >= 0:
                    compressed = get_human_size_str(p.compressed_size)
                    download_size += p.compressed_size

                else:
                    compressed = '?'

                if p.transaction_size is not None:
                    install_size += p.transaction_size
                    uncompressed = get_human_size_str(p.transaction_size)
                else:
                    uncompressed = '?'

                views.append(InputOption(label=f"{p.name} ({uncompressed} | {compressed})",
                                         value=p.name, read_only=True, icon_path=DEBIAN_ICON_PATH,
                                         tooltip=p.description if p.description else '?'))

            dsize = get_human_size_str(download_size) if download_size > 0 else '?'
            isize = get_human_size_str(install_size) if install_size > 0 else '?'
            return views, isize, dsize

    def _map_to_remove(self, pkgs: Optional[Collection[DebianPackage]]) -> Optional[Tuple[List[InputOption], str]]:
        if pkgs:
            freed_space = 0

            views = []
            for p in pkgs:
                if p.transaction_size is not None:
                    size = p.transaction_size * (-1 if p.transaction_size < 0 else 1)
                    freed_space += size
                    uncompressed = get_human_size_str(size)
                else:
                    uncompressed = '?'

                views.append(InputOption(label=f"{p.name} (-{uncompressed})",
                                         value=p.name, read_only=True, icon_path=DEBIAN_ICON_PATH,
                                         tooltip=p.description if p.description else '?'))

            return views, f'-{get_human_size_str(freed_space)}' if freed_space > 0 else '?'

    def confirm_transaction(self, to_install: Optional[Collection[DebianPackage]],
                            removal: Optional[Collection[DebianPackage]],
                            watcher: ProcessWatcher) -> bool:

        components = []

        to_remove_data = self._map_to_remove(removal)

        text_width, select_width = 672, 595

        if to_remove_data:
            to_remove_data[0].sort(key=attrgetter('label'))
            lb_rem = self._i18n['debian.transaction.to_remove'].format(no=bold(str(len(to_remove_data[0]))),
                                                                       fspace=bold(to_remove_data[1]))

            components.append(TextComponent(html=lb_rem, min_width=text_width))
            components.append(MultipleSelectComponent(id_='rem', options=to_remove_data[0], label=None,
                                                      default_options={*to_remove_data[0]},
                                                      max_width=select_width))

        to_install_data = self._map_to_install(to_install)

        if to_install_data:
            to_install_data[0].sort(key=attrgetter('label'))
            lb_deps = self._i18n['debian.transaction.to_install'].format(no=bold(str(len(to_install_data[0]))),
                                                                         dsize=bold(to_install_data[2]),
                                                                         isize=bold(to_install_data[1]))

            components.append(TextComponent(html=f'<br/>{lb_deps}', min_width=text_width))
            components.append(MultipleSelectComponent(id_='inst', label='', options=to_install_data[0],
                                                      default_options={*to_install_data[0]},
                                                      max_width=select_width))

        return watcher.request_confirmation(title=self._i18n['debian.transaction.title'],
                                            components=components,
                                            confirmation_label=self._i18n['popup.button.continue'],
                                            deny_label=self._i18n['popup.button.cancel'],
                                            body=None,
                                            min_width=text_width,
                                            min_height=54)

    def confirm_removal(self, source_pkg: str, dependencies: Collection[DebianPackage], watcher: ProcessWatcher) -> bool:
        dep_views = []
        freed_space = 0
        for p in sorted(dependencies, key=attrgetter('name')):
            if p.transaction_size is not None:
                size = p.transaction_size * (-1 if p.transaction_size < 0 else 1)
                freed_space += size
                size_str = get_human_size_str(size)
            else:
                size_str = '?'

            dep_views.append(InputOption(label=f"{p.name}: -{size_str}", value=p.name, read_only=True,
                                         icon_path=DEBIAN_ICON_PATH, tooltip=p.description))

        deps_container = MultipleSelectComponent(id_='deps', label='', options=dep_views, default_options={*dep_views},
                                                 max_width=537)

        freed_space_str = bold('-' + get_human_size_str(freed_space))
        body_text = TextComponent(html=self._i18n['debian.remove_deps'].format(no=bold(str(len(dependencies))),
                                                                               pkg=bold(source_pkg),
                                                                               fspace=freed_space_str),
                                  min_width=653)

        return watcher.request_confirmation(title=self._i18n['debian.transaction.title'],
                                            components=[body_text, deps_container],
                                            confirmation_label=self._i18n['popup.button.continue'],
                                            deny_label=self._i18n['popup.button.cancel'],
                                            min_height=200,
                                            body=None)

    def confirm_purge(self, pkg_name: str, watcher: ProcessWatcher) -> bool:
        msg = self._i18n['debian.action.purge.confirmation'].format(pkg=bold(pkg_name))
        return watcher.request_confirmation(title=self._i18n['debian.action.purge'],
                                            body=msg,
                                            confirmation_label=self._i18n['popup.button.continue'])
