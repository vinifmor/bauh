from unittest import TestCase

from bauh.gems.arch.util import clean_version


class TestUtil(TestCase):

    def test_clean_version__blank_version(self):
        self.assertEqual('', clean_version(''))

    def test_clean_version__blank_version_with_several_spaces(self):
        self.assertEqual('', clean_version('       '))

    def test_clean_version__with_epic(self):
        self.assertEqual('12.0.0', clean_version('1:12.0.0'))

    def test_clean_version__with_release(self):
        self.assertEqual('12.0.0', clean_version('12.0.0-1'))

    def test_clean_version__with_epic_and_release(self):
        self.assertEqual('12.0.0', clean_version('1:12.0.0-2'))

    def test_clean_version__with_several_releases(self):
        self.assertEqual('12.0.0-1-2', clean_version('12.0.0-1-2-3'))

    def test_clean_version__(self):
        self.assertEqual('29', clean_version('29-1.0'))
