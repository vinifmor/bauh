from unittest import TestCase

from bauh.gems.arch.controller import ArchManager
from bauh.gems.arch.model import ArchPackage


class ArchManagerSortUpdateOrderTest(TestCase):

    def test__sort_deps__not_related_packages(self):
        deps = {
            ArchPackage(name='google-chrome', package_base='google-chrome'): {'alsa-lib', 'gtk3', 'libcups'},
            ArchPackage(name='git-cola', package_base='git-cola'): {'git', 'python-pyqt5', 'icu qt5-svg'},
            ArchPackage(name='kazam', package_base='kazam'): {'python', 'python-cairo'}
        }

        sorted_list = ArchManager._sort_deps(deps, {d.name: d for d in deps})
        self.assertIsInstance(sorted_list, list)
        self.assertEqual(len(deps), len(sorted_list))

        for pkg in sorted_list:
            self.assertIn(pkg, deps)

    def test__sort_deps__all_packages_no_deps(self):
        deps = {
            ArchPackage(name='xpto', package_base='xpto'): set(),
            ArchPackage(name='abc', package_base='abc'): None
        }

        sorted_list = ArchManager._sort_deps(deps, {d.name: d for d in deps})
        self.assertIsInstance(sorted_list, list)
        self.assertEqual(len(deps), len(sorted_list))

        for pkg in sorted_list:
            self.assertIn(pkg, deps)

    def test__sort_deps__one_of_three_related(self):
        deps = {
            ArchPackage(name='abc', package_base='abc'): {'ghi', 'xpto'},
            ArchPackage(name='def', package_base='def'): {'jkl'},
            ArchPackage(name='ghi', package_base='ghi'): {}
        }

        name_map = {d.name: d for d in deps}
        for _ in range(5):  # testing n times to see if the same result is produced
            sorted_list = ArchManager._sort_deps(deps, name_map)
            self.assertIsInstance(sorted_list, list)
            self.assertEqual(len(deps), len(sorted_list))

            for pkg in sorted_list:
                self.assertIn(pkg, deps)

            ghi = [p for p in sorted_list if p.name == 'ghi']
            self.assertEqual(1, len(ghi))

            ghi_idx = sorted_list.index(ghi[0])

            abc = [p for p in sorted_list if p.name == 'abc']
            self.assertEqual(1, len(abc))

            abc_idx = sorted_list.index(abc[0])
            self.assertGreater(abc_idx, ghi_idx)

    def test__sort_deps__two_of_three_related(self):
        """
            dep order = abc -> ghi -> def
            expected: def, ghi, abc
        """
        deps = {
            ArchPackage(name='abc', package_base='abc'): {'ghi', 'xpto'},
            ArchPackage(name='def', package_base='def'): {'jkl'},
            ArchPackage(name='ghi', package_base='ghi'): {'def'}
        }

        name_map = {d.name: d for d in deps}
        for _ in range(5):  # testing n times to see if the same result is produced
            sorted_list = ArchManager._sort_deps(deps, name_map)
            self.assertIsInstance(sorted_list, list)
            self.assertEqual(len(deps), len(sorted_list))

            for pkg in sorted_list:
                self.assertIn(pkg, deps)

            self.assertEqual(sorted_list[0].name, 'def')
            self.assertEqual(sorted_list[1].name, 'ghi')
            self.assertEqual(sorted_list[2].name, 'abc')

    def test__sort_deps__two_relying_on_the_same_package(self):
        """
            dep order:
                abc -> ghi
                jkl -> ghi
                ghi -> def
                def -> mno
            expected: def, ghi, (abc | jkl )
        """

        deps = {
            ArchPackage(name='abc', package_base='abc'): {'ghi', 'xpto'},
            ArchPackage(name='def', package_base='def'): {'mno'},
            ArchPackage(name='ghi', package_base='ghi'): {'def'},
            ArchPackage(name='jkl', package_base='jkl'): {'ghi'}
        }

        name_map = {d.name: d for d in deps}
        for _ in range(5):  # testing n times to see if the same result is produced
            sorted_list = ArchManager._sort_deps(deps, name_map)
            self.assertIsInstance(sorted_list, list)
            self.assertEqual(len(deps), len(sorted_list))

            for pkg in sorted_list:
                self.assertIn(pkg, deps)

            self.assertEqual(sorted_list[0].name, 'def')
            self.assertEqual(sorted_list[1].name, 'ghi')

            self.assertNotEqual(sorted_list[2].name,  sorted_list[3].name)
            self.assertIn(sorted_list[2].name, {'abc', 'jkl'})
            self.assertIn(sorted_list[3].name, {'abc', 'jkl'})

    def test__sort_deps__with_cycle(self):
        """
            dep order:
                abc -> def -> ghi -> jkl -> abc
        """
        deps = {
            ArchPackage(name='abc', package_base='abc'): {'def'},
            ArchPackage(name='def', package_base='def'): {'ghi'},
            ArchPackage(name='ghi', package_base='ghi'): {'jkl'},
            ArchPackage(name='jkl', package_base='jkl'): {'abc'}
        }

        sorted_list = ArchManager._sort_deps(deps, {d.name: d for d in deps})
        self.assertIsInstance(sorted_list, list)
        self.assertEqual(len(deps), len(sorted_list))

        for pkg in sorted_list:
            self.assertIn(pkg, deps)

    def test__sort_deps__a_declared_dep_provided_as_a_different_name(self):
        """
            dep order:
                abc -> fed
                def (fed)
                ghi -> abc
            expected: def, abc, ghi
        """
        def_pkg = ArchPackage(name='def', package_base='def')

        deps = {
            ArchPackage(name='abc', package_base='abc'): {'fed'},
            def_pkg: {},
            ArchPackage(name='ghi', package_base='ghi'): {'abc'}
        }

        name_map = {d.name: d for d in deps}
        name_map['fed'] = def_pkg

        for _ in range(5):
            sorted_list = ArchManager._sort_deps(deps, name_map)
            self.assertIsInstance(sorted_list, list)
            self.assertEqual(len(deps), len(sorted_list))

            for pkg in sorted_list:
                self.assertIn(pkg, deps)

            self.assertEqual(sorted_list[0].name, 'def')
            self.assertEqual(sorted_list[1].name, 'abc')
            self.assertEqual(sorted_list[2].name, 'ghi')
