import multiprocessing
import os
import traceback

from bauh.commons.system import new_root_subprocess


def supports_performance_mode():
    return os.path.exists('/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor')


def all_in_performance() -> bool:
    for i in range(multiprocessing.cpu_count()):
        with open('/sys/devices/system/cpu/cpu{}/cpufreq/scaling_governor'.format(i)) as f:
            if f.read().strip() != 'performance':
                return False

    return False


def set_mode(mode: str, root_password: str):
    new_gov_file = '/tmp/bauh_scaling_governor'
    with open(new_gov_file, 'w+') as f:
        f.write(mode)

    for i in range(multiprocessing.cpu_count()):
        try:
            gov_file = '/sys/devices/system/cpu/cpu{}/cpufreq/scaling_governor'.format(i)
            replace = new_root_subprocess(['cp', new_gov_file, gov_file], root_password=root_password)
            replace.wait()
        except:
            traceback.print_exc()

        if os.path.exists(new_gov_file):
            try:
                os.remove(new_gov_file)
            except:
                traceback.print_exc()
