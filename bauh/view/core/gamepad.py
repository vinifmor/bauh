from typing import List

import evdev
from evdev import InputDevice


def is_gamepad(dev: InputDevice) -> bool:
    return bool({e for cap in dev.capabilities().values() for e in cap if e == 304})


def list_gamepads() -> List[InputDevice]:
    devices = [InputDevice(path) for path in evdev.list_devices()]
    return [d for d in devices if is_gamepad(d)]
