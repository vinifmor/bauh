from typing import Dict, Optional

from bauh.gems.debian.model import DebianPackage


def strip_maintainer_email(maintainer: str) -> str:
    return maintainer.split('<')[0].strip()


def strip_section(section: str) -> Optional[str]:
    if section:
        section_split = section.split('/')
        return section_split[1] if len(section_split) > 1 else section


def fill_show_data(pkg: DebianPackage, data: Dict[str, object]):
    if data:
        for attr, val in data.items():
            final_attr = attr.replace(' ', '_')

            if not val or val == '<none>':
                final_val = None
            else:
                if attr == 'maintainer':
                    final_val = strip_maintainer_email(str(val))
                elif attr == 'section':
                    final_attr = 'categories'
                    final_val = (strip_section(str(val)),)
                else:
                    final_val = val

            setattr(pkg, final_attr, final_val)
