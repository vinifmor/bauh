from typing import Set

from bauh.commons import system


def is_installed() -> bool:
    return system.execute(cmd='which checkrebuild', output=False)[0] == 0


def list_required_rebuild() -> Set[str]:
    code, output = system.execute(cmd='checkrebuild')

    required = set()
    if code == 0 and output:
        for line in output.split('\n'):
            line_strip = line.strip()

            if line_strip:
                line_split = line_strip.split('\t')

                if len(line_split) > 1:
                    required.add(line_split[1])

    return required
