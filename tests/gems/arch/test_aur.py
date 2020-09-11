import os
from unittest import TestCase

from bauh.gems.arch import aur

FILE_DIR = os.path.dirname(os.path.abspath(__file__))


class AURModuleTest(TestCase):

    def test_map_srcinfo__only_one_pkgname(self):
        expected_fields = {
            'pkgbase': 'bauh',
            'pkgname': 'bauh',
            'pkgver': '0.9.6',
            'pkgrel': '2',
            'url': 'https://github.com/vinifmor/bauh',
            'arch': 'any',
            'license': 'zlib/libpng',
            'makedepends': ['git', 'python', 'python-pip', 'python-setuptools'],
            'depends': [
                'python', 'python-colorama', 'python-pyaml', 'python-pyqt5', 'python-pyqt5-sip', 'python-requests', 'qt5-svg'
            ],
            'optdepends': [
                'flatpak: required for Flatpak support',
                'python-beautifulsoup4: for Native Web applications support',
                'python-lxml: for Native Web applications support',
                'snapd: required for Snap support'
            ],
            'source': ['https://github.com/vinifmor/bauh/archive/0.9.6.tar.gz'],
            'sha512sums': ['cb1820b8a41dccec746d91d71b7f524c2e3caf6b30b0cd9666598b8ad49302654d9ce9bd1a0a2a9612afebc27ef78a2a94ac10e4e6c183742effe4feeabaa7b2']
        }

        with open(FILE_DIR + '/resources/bauh_srcinfo') as f:
            srcinfo = f.read()

        res = aur.map_srcinfo(srcinfo, 'bauh')

        for key, val in expected_fields.items():
            self.assertIn(key, res, "key '{}' not in res".format(key))

            if isinstance(val, list):
                val.sort()
                res[key].sort()

            self.assertEqual(val, res[key], "expected: {}. current: {}".format(val, res[key]))

    def test_map_srcinfo__one_name__only_specific_fields(self):
        expected_fields = {
            'pkgver': '0.9.6',
            'pkgrel': '2'
        }

        with open(FILE_DIR + '/resources/bauh_srcinfo') as f:
            srcinfo = f.read()

        res = aur.map_srcinfo(srcinfo, 'bauh', fields={*expected_fields.keys()})

        self.assertEqual(len(expected_fields), len(res), "Expected: {}. Current: {}".format(len(expected_fields), len(res)))

        for key, val in expected_fields.items():
            self.assertIn(key, res, "key '{}' not in res".format(key))

            if isinstance(val, list):
                val.sort()
                res[key].sort()

            self.assertEqual(val, res[key], "expected: {}. current: {}".format(val, res[key]))

    def test_map_srcinfo__several_pkgnames__pkgname_specified_case_1(self):
        expected_fields = {
            'pkgbase': 'mangohud',
            'pkgname': 'mangohud',
            'pkgver': '0.5.1',
            'pkgrel': '3',
            'pkgdesc': 'A Vulkan overlay layer for monitoring FPS, temperatures, CPU/GPU load and more',
            'source': ['mangohud-0.5.1.tar.gz::https://github.com/flightlessmango/MangoHud/archive/v0.5.1.tar.gz'],
            'sha256sums': ['3e91d4fc7369d46763894c13f3315133871dd02705072981770c3cf58e8081c6'],
            'license': 'MIT',
            'arch': 'x86_64',
            'url': 'https://github.com/flightlessmango/MangoHud',
            'makedepends': [
                'glslang', 'libglvnd', 'lib32-libglvnd', 'meson', 'python-mako', 'vulkan-headers', 'vulkan-icd-loader',
                'lib32-vulkan-icd-loader', 'libxnvctrl'
            ],
            'depends': ['gcc-libs', 'mangohud-common'],
            'optdepends': ['bash: mangohud helper script', 'libxnvctrl: support for older NVIDIA GPUs']
        }

        with open(FILE_DIR + '/resources/mangohud_srcinfo') as f:
            srcinfo = f.read()

        res = aur.map_srcinfo(srcinfo, 'mangohud')

        self.assertEqual(len(expected_fields), len(res), "Expected: {}. Current: {}".format(len(expected_fields), len(res)))

        for key, val in expected_fields.items():
            self.assertIn(key, res, "key '{}' not in res".format(key))

            if isinstance(val, list):
                val.sort()

            if isinstance(res[key], list):
                res[key].sort()

            self.assertEqual(val, res[key], "expected: {}. current: {}".format(val, res[key]))

    def test_map_srcinfo__several_pkgnames__pkgname_specified_case_2(self):
        expected_fields = {
            'pkgbase': 'mangohud',
            'pkgname': 'mangohud-common',
            'pkgver': '0.5.1',
            'pkgrel': '3',
            'pkgdesc': 'Common files for mangohud and lib32-mangohud',
            'source': ['mangohud-0.5.1.tar.gz::https://github.com/flightlessmango/MangoHud/archive/v0.5.1.tar.gz'],
            'sha256sums': ['3e91d4fc7369d46763894c13f3315133871dd02705072981770c3cf58e8081c6'],
            'license': 'MIT',
            'url': 'https://github.com/flightlessmango/MangoHud',
            'arch': 'x86_64',
            'makedepends': [
                'glslang', 'libglvnd', 'lib32-libglvnd', 'meson', 'python-mako', 'vulkan-headers', 'vulkan-icd-loader',
                'lib32-vulkan-icd-loader', 'libxnvctrl'
            ],
            'optdepends': ['bash: mangohud helper script']
        }

        with open(FILE_DIR + '/resources/mangohud_srcinfo') as f:
            srcinfo = f.read()

        res = aur.map_srcinfo(srcinfo, 'mangohud-common')
        self.assertEqual(len(expected_fields), len(res), "Expected: {}. Current: {}".format(len(expected_fields), len(res)))

        for key, val in expected_fields.items():
            self.assertIn(key, res, "key '{}' not in res".format(key))

            if isinstance(val, list):
                val.sort()

            if isinstance(res[key], list):
                res[key].sort()

            self.assertEqual(val, res[key], "expected: {}. current: {}".format(val, res[key]))

    def test_map_srcinfo__several_pkgnames__pkgname_specified_case_3(self):
        expected_fields = {
            'pkgbase': 'mangohud',
            'pkgname': 'lib32-mangohud',
            'pkgver': '0.5.1',
            'pkgrel': '3',
            'pkgdesc': 'A Vulkan overlay layer for monitoring FPS, temperatures, CPU/GPU load and more (32-bit)',
            'source': ['mangohud-0.5.1.tar.gz::https://github.com/flightlessmango/MangoHud/archive/v0.5.1.tar.gz'],
            'sha256sums': ['3e91d4fc7369d46763894c13f3315133871dd02705072981770c3cf58e8081c6'],
            'license': 'MIT',
            'url': 'https://github.com/flightlessmango/MangoHud',
            'arch': 'x86_64',
            'makedepends': [
                'glslang', 'libglvnd', 'lib32-libglvnd', 'meson', 'python-mako', 'vulkan-headers', 'vulkan-icd-loader',
                'lib32-vulkan-icd-loader', 'libxnvctrl'
            ],
            'depends': ['mangohud', 'mangohud-common', 'lib32-gcc-libs'],
            'optdepends': ['lib32-libxnvctrl: support for older NVIDIA GPUs']
        }

        with open(FILE_DIR + '/resources/mangohud_srcinfo') as f:
            srcinfo = f.read()

        res = aur.map_srcinfo(srcinfo, 'lib32-mangohud')
        self.assertEqual(len(expected_fields), len(res), "Expected: {}. Current: {}".format(len(expected_fields), len(res)))

        for key, val in expected_fields.items():
            self.assertIn(key, res, "key '{}' not in res".format(key))

            if isinstance(val, list):
                val.sort()

            if isinstance(res[key], list):
                res[key].sort()

            self.assertEqual(val, res[key], "expected: {}. current: {}".format(val, res[key]))

    def test_map_srcinfo__several_pkgnames__different_pkgname(self):
        expected_fields = {
            'pkgbase': 'mangohud',
            'pkgname': ['lib32-mangohud', 'mangohud', 'mangohud-common'],
            'pkgver': '0.5.1',
            'pkgrel': '3',
            'pkgdesc': [
                'A Vulkan overlay layer for monitoring FPS, temperatures, CPU/GPU load and more (32-bit)',
                'Common files for mangohud and lib32-mangohud',
                'A Vulkan overlay layer for monitoring FPS, temperatures, CPU/GPU load and more',
            ],
            'source': ['mangohud-0.5.1.tar.gz::https://github.com/flightlessmango/MangoHud/archive/v0.5.1.tar.gz'],
            'sha256sums': ['3e91d4fc7369d46763894c13f3315133871dd02705072981770c3cf58e8081c6'],
            'license': 'MIT',
            'url': 'https://github.com/flightlessmango/MangoHud',
            'arch': 'x86_64',
            'makedepends': [
                'glslang', 'libglvnd', 'lib32-libglvnd', 'meson', 'python-mako', 'vulkan-headers', 'vulkan-icd-loader',
                'lib32-vulkan-icd-loader', 'libxnvctrl'
            ],
            'depends': ['mangohud', 'mangohud-common', 'lib32-gcc-libs', 'gcc-libs'],
            'optdepends': ['lib32-libxnvctrl: support for older NVIDIA GPUs',
                           'bash: mangohud helper script',
                           'libxnvctrl: support for older NVIDIA GPUs']
        }

        with open(FILE_DIR + '/resources/mangohud_srcinfo') as f:
            srcinfo = f.read()

        res = aur.map_srcinfo(srcinfo, 'xpto')
        self.assertEqual(len(expected_fields), len(res), "Expected: {}. Current: {}".format(len(expected_fields), len(res)))

        for key, val in expected_fields.items():
            self.assertIn(key, res, "key '{}' not in res".format(key))

            if isinstance(val, list):
                val.sort()

            if isinstance(res[key], list):
                res[key].sort()

            self.assertEqual(val, res[key], "expected: {}. current: {}".format(val, res[key]))

    def test_map_srcinfo__several_names__pkgname_present__only_specific_fields(self):
        expected_fields = {
            'pkgver': '0.5.1',
            'pkgrel': '3'
        }

        with open(FILE_DIR + '/resources/mangohud_srcinfo') as f:
            srcinfo = f.read()

        res = aur.map_srcinfo(srcinfo, 'mangohud-commons', fields={*expected_fields.keys()})

        self.assertEqual(len(expected_fields), len(res), "Expected: {}. Current: {}".format(len(expected_fields), len(res)))

        for key, val in expected_fields.items():
            self.assertIn(key, res, "key '{}' not in res".format(key))

            if isinstance(val, list):
                val.sort()
                res[key].sort()

            self.assertEqual(val, res[key], "expected: {}. current: {}".format(val, res[key]))

    def test_map_srcinfo__several_names__pkgname_not_present__only_specific_fields(self):
        expected_fields = {
            'pkgname': ['mangohud', 'lib32-mangohud', 'mangohud-common'],
            'pkgver': '0.5.1'
        }

        with open(FILE_DIR + '/resources/mangohud_srcinfo') as f:
            srcinfo = f.read()

        res = aur.map_srcinfo(srcinfo, 'xpto', fields={*expected_fields.keys()})

        self.assertEqual(len(expected_fields), len(res), "Expected: {}. Current: {}".format(len(expected_fields), len(res)))

        for key, val in expected_fields.items():
            self.assertIn(key, res, "key '{}' not in res".format(key))

            if isinstance(val, list):
                val.sort()
                res[key].sort()

            self.assertEqual(val, res[key], "expected: {}. current: {}".format(val, res[key]))
