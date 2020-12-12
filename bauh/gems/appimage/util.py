import os
import re

RE_DESKTOP_EXEC = re.compile(r'(Exec\s*=(.+)(\n?))')
RE_MANY_SPACES = re.compile(r'\s+')


def find_appimage_file(folder: str) -> str:
    for r, d, files in os.walk(folder):
        for f in files:
            if f.lower().endswith('.appimage'):
                return '{}/{}'.format(folder, f)


def replace_desktop_entry_exec_command(desktop_entry: str, appname: str, file_path: str) -> str:
    execs = RE_DESKTOP_EXEC.findall(desktop_entry)

    if not execs:
        return desktop_entry

    final_entry = desktop_entry
    treated_name = appname.strip().lower()

    for exec_groups in execs:
        full_match = exec_groups[0]
        cmd = RE_MANY_SPACES.sub(' ', exec_groups[1].strip())
        if cmd:
            words = cmd.split(' ')
            changed = False

            for idx in range(len(words)):
                if words[idx].lower() == treated_name:
                    words[idx] = '"{}"'.format(file_path)
                    changed = True
                    break

            if not changed:
                words = ['"{}"'.format(file_path)]

            final_entry = final_entry.replace(full_match, full_match.replace(exec_groups[1], ' '.join(words)))

    return final_entry
