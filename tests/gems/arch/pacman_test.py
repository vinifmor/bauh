import os
from unittest import TestCase

from bauh.gems.arch import pacman

FILE_DIR = os.path.dirname(os.path.abspath(__file__))


class PacmanTest(TestCase):

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
