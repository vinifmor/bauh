import warnings
from unittest import TestCase

from bauh.gems.arch import version


class MatchRequiredVersionTest(TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings('ignore', category=DeprecationWarning)

    def test_must_accept_single_or_both_equal_symbols_as_valid(self):
        self.assertTrue(version.match_required_version('1', '=', '1'))
        self.assertTrue(version.match_required_version('1', '==', '1'))

    def test_must_ignore_release_number_when_required_has_no_defined(self):
        self.assertTrue(version.match_required_version('1.3.0-2', '==', '1.3.0'))
        self.assertTrue(version.match_required_version('1.3.0-2', '<=', '1.3.0'))
        self.assertTrue(version.match_required_version('1.3.0-2', '>=', '1.3.0'))
        self.assertFalse(version.match_required_version('1.3.0-2', '<', '1.3.0'))
        self.assertFalse(version.match_required_version('1.3.0-2', '>', '1.3.0'))

    def test_must_ignore_epoch_number_when_required_has_no_defined(self):
        self.assertTrue(version.match_required_version('1:1.3.0-1', '>', '1.1.0'))
        self.assertTrue(version.match_required_version('1:1.3.0-1', '>=', '1.1.0'))
        self.assertFalse(version.match_required_version('1:1.3.0-1', '<', '1.1.0'))
        self.assertFalse(version.match_required_version('1:1.3.0-1', '<=', '1.1.0'))
        self.assertFalse(version.match_required_version('1:1.3.0-1', '==', '1.1.0'))

    def test_must_consider_default_epoch_for_current_version_when_required_has_epoch(self):
        self.assertFalse(version.match_required_version('1.1.0', '==', '1:1.1.0'))  # 1.1.0 -> 0:1.1.0
        self.assertFalse(version.match_required_version('1.1.0', '>', '1:1.1.0'))  # 1.1.0 -> 0:1.1.0
        self.assertFalse(version.match_required_version('1.1.0', '>=', '1:1.1.0'))  # 1.1.0 -> 0:1.1.0
        self.assertTrue(version.match_required_version('1.1.0', '<', '1:1.1.0'))  # 1.1.0 -> 0:1.1.0
        self.assertTrue(version.match_required_version('1.1.0', '<=', '1:1.1.0'))  # 1.1.0 -> 0:1.1.0

        self.assertTrue(version.match_required_version('1.1.0', '==', '0:1.1.0'))  # 1.1.0 -> 0:1.1.0

    def test_must_match_when_current_version_is_composed_of_alphanumerics_but_required_no(self):
        self.assertTrue(version.match_required_version('2.3.3op2', '>', '2.2.6'))
        self.assertTrue(version.match_required_version('2.3.3op2', '>=', '2.2.6'))
        self.assertFalse(version.match_required_version('2.3.3op2', '==', '2.2.6'))
        self.assertFalse(version.match_required_version('2.3.3op2', '<', '2.2.6'))
        self.assertFalse(version.match_required_version('2.3.3op2', '<=', '2.2.6'))

        # opposite comparisons
        self.assertFalse(version.match_required_version('2.2.6', '>', '2.3.3op2'))
        self.assertFalse(version.match_required_version('2.2.6', '>=', '2.3.3op2'))
        self.assertFalse(version.match_required_version('2.2.6', '==', '2.3.3op2'))
        self.assertTrue(version.match_required_version('2.2.6', '<', '2.3.3op2'))
        self.assertTrue(version.match_required_version('2.2.6', '<=', '2.3.3op2'))

    def test_must_match_when_both_versions_are_composed_of_alphanumerics(self):
        self.assertTrue(version.match_required_version('2.3.3ab', '==', '2.3.3ab'))
        self.assertTrue(version.match_required_version('2.3.3ab', '<', '2.3.3ac'))
        self.assertTrue(version.match_required_version('2.3.3ad', '>', '2.3.3ac'))
        self.assertTrue(version.match_required_version('2.3.3ad', '<', '2.3.3ad.1'))
