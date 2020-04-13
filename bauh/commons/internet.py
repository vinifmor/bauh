import subprocess
import traceback
from subprocess import Popen


def is_available() -> bool:
    try:
        res = Popen(['ping', '-q', '-w1', '-c1', 'google.com'], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        res.wait()
        return res.returncode == 0
    except:
        traceback.print_exc()
        return False
