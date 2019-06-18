import subprocess
from typing import List


def run_cmd(cmd: str, expected_code: int = 0, ignore_return_code: bool = False) -> str:
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE)
    return res.stdout.decode() if ignore_return_code or res.returncode == expected_code else None


def stream_cmd(cmd: List[str]):
    return subprocess.Popen(cmd, stdout=subprocess.PIPE).stdout
