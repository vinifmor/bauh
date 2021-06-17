from typing import Optional

from packaging.version import parse


def normalize_version(version: str) -> Optional[str]:
    if version:
        final_version = version.strip()

        if final_version:
            if ':' not in final_version:
                final_version = '0:{}'.format(final_version)

            if '-' not in final_version:
                final_version = '{}-1'.format(final_version)

        return final_version


def compare_versions(version_a: str, operator: str, version_b: str) -> bool:
    if operator:
        a_obj, b_obj = parse(normalize_version(version_a)), parse(normalize_version(version_b))

        if operator == '>':
            return a_obj > b_obj
        elif operator == '>=':
            return a_obj >= b_obj
        elif operator == '<':
            return a_obj < b_obj
        elif operator == '<=':
            return a_obj <= b_obj
        elif operator == '==':
            return a_obj == b_obj

    raise Exception("compare: invalid string operator {}".format(operator))
