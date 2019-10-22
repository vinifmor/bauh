import os

from bauh.api.constants import CACHE_PATH

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = '/tmp/bauh/aur'
ARCH_CACHE_PATH = CACHE_PATH + '/arch'

