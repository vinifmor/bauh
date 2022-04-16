import os
import warnings
from unittest import TestCase
from unittest.mock import patch, Mock

from bauh import __app_name__
from bauh.gems.arch import pacman

FILE_DIR = os.path.dirname(os.path.abspath(__file__))


class PacmanTest(TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings('ignore', category=DeprecationWarning)

    def test_list_ignored_packages(self):
        ignored = pacman.list_ignored_packages(FILE_DIR + '/resources/pacman_ign_pkgs.conf')

        self.assertIsNotNone(ignored)
        self.assertEqual(2, len(ignored))
        self.assertIn('google-chrome', ignored)
        self.assertIn('firefox', ignored)

    def test_list_ignored_packages__no_ignored_packages(self):
        ignored = pacman.list_ignored_packages(FILE_DIR + '/resources/pacman.conf')

        self.assertIsNotNone(ignored)
        self.assertEqual(0, len(ignored))

    @patch(f'{__app_name__}.gems.arch.pacman.run_cmd', return_value="""
Name            : package-test
Version         : 3.4.4-1
Description     : Test
Depends On      : embree  freetype2  libglvnd
Optional Deps   : lib32-vulkan-icd-loader: Vulkan support [installed]
Required By     : None
            """)
    def test_map_optional_deps__no_remote_and_not_installed__only_one_installed_with_description(self, run_cmd: Mock):
        res = pacman.map_optional_deps(('package-test',), remote=False, not_installed=True)
        run_cmd.assert_called_once_with('pacman -Qi package-test')
        self.assertEqual({'package-test': {}}, res)

    @patch(f'{__app_name__}.gems.arch.pacman.run_cmd', return_value="""
Name            : package-test
Version         : 3.4.4-1
Description     : Test
Depends On      : embree  freetype2  libglvnd
Optional Deps   : lib32-vulkan-icd-loader: Vulkan support
Required By     : None
        """)
    def test_map_optional_deps__no_remote_and_not_installed__only_one_not_installed_with_description(self, run_cmd: Mock):
        res = pacman.map_optional_deps(('package-test',), remote=False, not_installed=True)
        run_cmd.assert_called_once_with('pacman -Qi package-test')
        self.assertEqual({'package-test': {'lib32-vulkan-icd-loader': 'Vulkan support'}}, res)

    @patch(f'{__app_name__}.gems.arch.pacman.run_cmd', return_value="""
Name            : package-test
Version         : 3.4.4-1
Description     : Test
Depends On      : embree  freetype2  libglvnd
Optional Deps   : pipewire-alsa
Required By     : None
            """)
    def test_map_optional_deps__no_remote_and_not_installed__only_one_not_installed_no_description(self, run_cmd: Mock):
            res = pacman.map_optional_deps(('package-test',), remote=False, not_installed=True)
            run_cmd.assert_called_once_with('pacman -Qi package-test')
            self.assertEqual({'package-test': {'pipewire-alsa': ''}}, res)

    @patch(f'{__app_name__}.gems.arch.pacman.run_cmd', return_value="""
Name            : package-test
Version         : 3.4.4-1
Description     : Test
Depends On      : embree  freetype2  libglvnd
Optional Deps   : pipewire-alsa [installed]
Required By     : None
                """)
    def test_map_optional_deps__no_remote_and_not_installed__only_one_installed_no_description(self, run_cmd: Mock):
        res = pacman.map_optional_deps(('package-test',), remote=False, not_installed=True)
        run_cmd.assert_called_once_with('pacman -Qi package-test')
        self.assertEqual({'package-test': {}}, res)

    @patch(f'{__app_name__}.gems.arch.pacman.run_cmd', return_value="""
Name            : package-test
Version         : 3.4.4-1
Description     : Test
Depends On      : embree  freetype2  libglvnd  libtheora
Optional Deps   : pipewire-alsa
                  pipewire-pulse [installed]
                  pipewire
                  lib32-vulkan-icd-loader: Vulkan support [installed]
Required By     : None
    """)
    def test_map_optional_deps__no_remote_and_not_installed__several(self, run_cmd: Mock):
        res = pacman.map_optional_deps(('package-test',), remote=False, not_installed=True)
        run_cmd.assert_called_once_with('pacman -Qi package-test')
        self.assertEqual({'package-test': {'pipewire-alsa': '', 'pipewire': ''}}, res)
