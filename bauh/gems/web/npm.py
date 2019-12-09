from bauh.commons.system import run_cmd


def is_available() -> bool:
    res = run_cmd('which npm', print_error=False)
    return res and not res.strip().startswith('which ')
