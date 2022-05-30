import os
from typing import Optional, Dict
from bauh import __app_name__


def read_suggestions_mapping() -> Optional[Dict[str, str]]:
    file_path = f'/etc/{__app_name__}/suggestions.conf'

    if os.path.isfile(file_path):
        try:
            with open(file_path) as f:
                file_content = f.read()
        except FileNotFoundError:
            return

        if not file_content:
            return

        mapping = {}
        for line in file_content.split('\n'):
            line_strip = line.strip()

            if not line_strip.startswith('#'):
                gem_file = line_strip.split('=')

                if len(gem_file) == 2:
                    gem_name, file_url = gem_file[0].strip(), gem_file[1].strip()

                    if gem_name and file_url:
                        mapping[gem_name] = file_url

        return mapping if mapping else None
