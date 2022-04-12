import multiprocessing
import os
import shutil
import traceback
from logging import Logger
from typing import Optional, Set, Tuple, Dict

from bauh.api.paths import TEMP_DIR
from bauh.commons.system import new_root_subprocess


def supports_performance_mode() -> bool:
    return os.path.exists('/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor')


def current_governors() -> Dict[str, Set[int]]:
    governors = {}
    for cpu in range(multiprocessing.cpu_count()):
        with open(f'/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor') as f:
            gov = f.read().strip()
            cpus = governors.get(gov, set())
            cpus.add(cpu)
            governors[gov] = cpus

    return governors


def set_governor(governor: str, root_password: Optional[str], cpu_idxs: Optional[Set[int]] = None):
    new_gov_file = f'{TEMP_DIR}/bauh_scaling_governor'
    with open(new_gov_file, 'w+') as f:
        f.write(governor)

    for idx in (cpu_idxs if cpu_idxs else range(multiprocessing.cpu_count())):
        _change_governor(idx, new_gov_file, root_password)

    if os.path.exists(new_gov_file):
        try:
            os.remove(new_gov_file)
        except OSError:
            traceback.print_exc()


def _change_governor(cpu_idx: int, new_gov_file_path: str, root_password: Optional[str]):
    try:
        gov_file = f'/sys/devices/system/cpu/cpu{cpu_idx}/cpufreq/scaling_governor'
        replace = new_root_subprocess((shutil.which('cp'), new_gov_file_path, gov_file), root_password=root_password)
        replace.wait()
    except Exception:
        traceback.print_exc()


def set_all_cpus_to(governor: str, root_password: Optional[str], logger: Optional[Logger] = None) \
        -> Tuple[bool, Optional[Dict[str, Set[int]]]]:
    cpus_changed, cpu_governors = False, current_governors()

    if cpu_governors:
        not_in_performance = set()
        for gov, cpus in cpu_governors.items():
            if gov != governor:
                not_in_performance.update(cpus)

        if not_in_performance:
            if logger:
                logger.info(f"Changing CPUs {not_in_performance} governors to '{governor}'")

            set_governor(governor, root_password, not_in_performance)
            cpus_changed = True

    return cpus_changed, cpu_governors


def set_cpus(governors: Dict[str, Set[int]], root_password: Optional[str], ignore_governors: Optional[Set[str]] = None,
             logger: Optional[Logger] = None):

    for gov, cpus in governors.items():
        if not ignore_governors or gov not in ignore_governors:
            if logger:
                logger.info(f"Changing CPUs {cpus} governors to '{gov}'")

            set_governor(gov, root_password, cpus)
