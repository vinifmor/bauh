from unittest import TestCase

from bauh.api.abstract.model import PackageUpdate


class PackageUpdateTest(TestCase):

    def test__hash__return_same_hash_for_equal_packages(self):
        a = PackageUpdate(pkg_id='a', name='b', version='c', pkg_type='d')
        b = PackageUpdate(pkg_id='a', name='b', version='c', pkg_type='d')
        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))

    def test__hash__return_different_hash_for_not_equal_packages(self):
        a = PackageUpdate(pkg_id='a', name='b', version='c', pkg_type='d')
        b = PackageUpdate(pkg_id='a', name='b', version='c', pkg_type='e')
        self.assertNotEqual(a, b)
        self.assertNotEqual(hash(a), hash(b))
