import warnings
from unittest import TestCase

from bauh.gems.arch import version


class CompareVersionsTest(TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings('ignore')

    def test_both_versions_only_filled_with_numbers_and_same_number_of_divisions(self):
        self.assertFalse(version.compare_versions('1', '>', '2'))
        self.assertTrue(version.compare_versions('1', '<', '2'))
        self.assertTrue(version.compare_versions('1', '<=', '2'))
        self.assertTrue(version.compare_versions('2', '>=', '1'))
        self.assertTrue(version.compare_versions('1', '==', '1'))
        self.assertFalse(version.compare_versions('1.1', '>', '2.0'))
        self.assertTrue(version.compare_versions('1.1', '<', '2.0'))
        self.assertTrue(version.compare_versions('1.1', '<=', '2.0'))
        self.assertTrue(version.compare_versions('2.1', '>', '2.0'))
        self.assertTrue(version.compare_versions('2.1', '>=', '2.0'))
        self.assertTrue(version.compare_versions('2.0', '==', '2.0'))

    def test_versions_only_filled_with_numbers_and_different_number_of_divisons(self):
        self.assertFalse(version.compare_versions('1.0', '>', '2'))
        self.assertTrue(version.compare_versions('1', '<', '2.0'))
        self.assertTrue(version.compare_versions('1.1.1', '<=', '2'))
        self.assertTrue(version.compare_versions('2', '>=', '1.0'))
        self.assertTrue(version.compare_versions('1.0', '==', '1'))
        self.assertTrue(version.compare_versions('1.1', '>', '1'))
        self.assertFalse(version.compare_versions('1.1', '<', '1'))

    def test_one_version_contain_mixed_letters_and_symbols(self):
        self.assertTrue(version.compare_versions('2.3.3op2', '>=', '2.2.6'))
        self.assertTrue(version.compare_versions('2.2a', '<', '2.2b'))
        self.assertTrue(version.compare_versions('2.2a', '<', '2.3a'))

    def test_versions_with_epochs(self):
        self.assertTrue(version.compare_versions('1:1', '==', '1:1.0'))
        self.assertTrue(version.compare_versions('1:1', '<', '1:1.1'))
        self.assertTrue(version.compare_versions('1:1', '<=', '1:1.1'))
        self.assertTrue(version.compare_versions('2:0', '>', '1:1.1'))
        self.assertTrue(version.compare_versions('1:0', '>', '2.0-1'))

    def test_versions_with_release_number(self):
        self.assertTrue(version.compare_versions('1.0-1', '<', '1.0-2'))
        self.assertTrue(version.compare_versions('1.0-2', '>', '1.0-1'))
        self.assertTrue(version.compare_versions('1.0-1', '<', '1.0-10'))
        self.assertTrue(version.compare_versions('1.0-10', '>', '1.0-1'))
