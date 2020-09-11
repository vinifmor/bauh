import json
import os
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Callable

from bauh.gems.arch import pacman
from bauh.gems.arch.model import ArchPackage

RE_DESKTOP_ENTRY = re.compile(r'[\n^](Exec|Icon|NoDisplay)\s*=\s*(.+)')
RE_CLEAN_NAME = re.compile(r'[+*?%]')


def write_several(pkgs: Dict[str, ArchPackage], overwrite: bool = True, maintainer: str = None, after_desktop_files:  Optional[Callable] = None, after_written: Optional[Callable[[str], None]] = None) -> int:
    if overwrite:
        to_cache = {p.name for p in pkgs.values()}
    else:
        to_cache = {p.name for p in pkgs.values() if not os.path.exists(p.get_disk_cache_path())}

    desktop_files = pacman.map_desktop_files(*to_cache)

    if after_desktop_files:
        after_desktop_files()

    if not desktop_files:
        for pkgname in to_cache:
            write(pkg=pkgs[pkgname], maintainer=maintainer, after_written=after_written)

        return len(to_cache)
    else:
        for pkgname in to_cache:
            pkgfiles = desktop_files.get(pkgname)

            if not pkgfiles:
                write(pkg=pkgs[pkgname], maintainer=maintainer, after_written=after_written)
            else:
                desktop_entry = find_best_desktop_entry(pkgname, pkgfiles)

                if desktop_entry:
                    write(pkg=pkgs[pkgname], maintainer=maintainer, after_written=after_written,
                          desktop_file=desktop_entry[0], command=desktop_entry[1], icon=desktop_entry[2])
                else:
                    write(pkg=pkgs[pkgname], maintainer=maintainer, after_written=after_written)

        return len(to_cache)


def find_best_desktop_entry(pkgname: str, desktop_files: List[str]) -> Optional[Tuple[str, str, str]]:
    if len(desktop_files) == 1:
        exec_icon = read_desktop_exec_and_icon(pkgname, desktop_files[0])

        if exec_icon:
            return desktop_files[0], exec_icon[0], exec_icon[1]
    else:
        # trying to find the exact name match:
        for dfile in desktop_files:
            if dfile.endswith('{}.desktop'.format(pkgname)):
                exec_icon = read_desktop_exec_and_icon(pkgname, dfile)

                if exec_icon:
                    return dfile, exec_icon[0], exec_icon[1]

        # trying to find a close name match:
        clean_name = RE_CLEAN_NAME.sub('', pkgname)
        for dfile in desktop_files:
            if dfile.endswith('{}.desktop'.format(clean_name)):
                exec_icon = read_desktop_exec_and_icon(clean_name, dfile)

                if exec_icon:
                    return dfile, exec_icon[0], exec_icon[1]

        # finding any match:
        for dfile in desktop_files:
            exec_icon = read_desktop_exec_and_icon(pkgname, dfile)

            if exec_icon:
                return dfile, exec_icon[0], exec_icon[1]


def read_desktop_exec_and_icon(pkgname: str, desktop_file: str) -> Optional[Tuple[str, str]]:
    if os.path.isfile(desktop_file):
        with open(desktop_file) as f:
            possibilities = set()

            content = f.read()
            cmd, icon = None, None
            for field in RE_DESKTOP_ENTRY.findall(content):
                if field[0] == 'Exec':
                    cmd = field[1].strip().replace('"', '')
                elif field[0] == 'Icon':
                    icon = field[1].strip()
                elif field[0] == 'NoDisplay' and field[1].strip().lower() == 'true':
                    cmd, icon = None, None

                if cmd and icon:
                    possibilities.add((cmd, icon))
                    cmd, icon = None, None

            if possibilities:
                if len(possibilities) == 1:
                    return [*possibilities][0]
                else:
                    # trying to find the exact name x command match
                    for p in possibilities:
                        if p[0].startswith('{} '.format(pkgname)):
                            return p

                    return sorted(possibilities)[0]  # returning any possibility


def write(pkg: ArchPackage, desktop_file: Optional[str] = None, command: Optional[str] = None,
          icon: Optional[str] = None, maintainer: Optional[str] = None, after_written: Optional[callable] = None):
    pkg.desktop_entry = desktop_file
    pkg.command = command
    pkg.icon_path = icon

    if maintainer and not pkg.maintainer:
        pkg.maintainer = maintainer

    Path(pkg.get_disk_cache_path()).mkdir(parents=True, exist_ok=True)

    data = pkg.get_data_to_cache()

    with open(pkg.get_disk_data_path(), 'w+') as f:
        f.write(json.dumps(data))

    if after_written:
        after_written(pkg.name)
