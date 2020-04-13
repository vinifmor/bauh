from unittest import TestCase

from bauh.gems.arch import sorting


class SortingTest(TestCase):

    def test_sort__aur_not_related(self):
        pkgs = {'google-chrome': {'d': {'alsa-lib', 'gtk3', 'libcups'}, 'p': {'google-chrome': 'google-chrome'}, 'r': 'extra'},
                'git-cola': {'d': {'git', 'python-pyqt5', 'icu qt5-svg'}, 'p': {'git-cola': 'git-cola'}, 'r': 'extra'},
                'kazam': {'d': {'python', 'python-cairo'}, 'p': {'kazam': 'kazam'}, 'r': 'extra'}}

        sorted_list = sorting.sort(pkgs.keys(), pkgs)
        self.assertIsInstance(sorted_list, list)
        self.assertEqual(len(pkgs), len(sorted_list))

        for pkg in sorted_list:
            self.assertIn(pkg[0], pkgs)

    def test_sort__all_packages_no_deps(self):
        pkgs = {'xpto': {'d': set(), 'p': {'xpto': 'xpto'}, 'r': 'extra'},
                'abc': {'d': None, 'p': {'abc': 'abc'}, 'r': 'extra'}}

        sorted_list = sorting.sort(pkgs.keys(), pkgs)
        self.assertIsInstance(sorted_list, list)
        self.assertEqual(len(pkgs), len(sorted_list))

        for pkg in sorted_list:
            self.assertIn(pkg[0], pkgs)

    def test_sort__one_of_three_related(self):
        pkgs = {'def': {'d': {'jkl'}, 'p': {'def': 'def'}, 'r': 'extra'},
                'abc': {'d': {'ghi', 'xpto'}, 'p': {'abc': 'abc'}, 'r': 'extra'},
                'ghi': {'d': None, 'p': {'ghi': 'ghi'}, 'r': 'extra'}}

        for _ in range(5):  # testing n times to see if the same result is produced
            sorted_list = sorting.sort(pkgs.keys(), pkgs)
            self.assertIsInstance(sorted_list, list)
            self.assertEqual(len(pkgs), len(sorted_list))

            for pkg in sorted_list:
                self.assertIn(pkg[0], pkgs)

            ghi = [p for p in sorted_list if p[0] == 'ghi']
            self.assertEqual(1, len(ghi))

            ghi_idx = sorted_list.index(ghi[0])

            abc = [p for p in sorted_list if p[0] == 'abc']
            self.assertEqual(1, len(abc))

            abc_idx = sorted_list.index(abc[0])
            self.assertGreater(abc_idx, ghi_idx)

    def test_sort__two_of_three_related(self):
        """
            dep order = abc -> ghi -> def
            expected: def, ghi, abc
        """
        pkgs = {'def': {'d': {'jkl'}, 'p': {'def': 'def'}, 'r': 'extra'},
                'abc': {'d': {'ghi', 'xpto'}, 'p': {'abc': 'abc'}, 'r': 'extra'},
                'ghi': {'d': {'def'}, 'p': {'ghi': 'ghi'}, 'r': 'extra'}}

        for _ in range(5):  # testing n times to see if the same result is produced
            sorted_list = sorting.sort(pkgs.keys(), pkgs)
            self.assertIsInstance(sorted_list, list)
            self.assertEqual(len(pkgs), len(sorted_list))

            for pkg in sorted_list:
                self.assertIn(pkg[0], pkgs)

            self.assertEqual(sorted_list[0][0], 'def')
            self.assertEqual(sorted_list[1][0], 'ghi')
            self.assertEqual(sorted_list[2][0], 'abc')

    def test_sort__all_related(self):
        pkgs = {'lutris': {'d': {'unzip', 'python-requests'}, 'p': {'lutris': 'lutris'}, 'r': 'community'},
                'python-requests': {'d': {'python-urllib3', 'python-chardet'},
                                    'p': {'python-requests': 'python-requests'}, 'r': 'extra'},
                'python-chardet': {'d': {'python-setuptools'}, 'p': {'python-chardet': 'python-chardet'},
                                   'r': 'extra'}}

        sorted_list = sorting.sort(pkgs.keys(), pkgs)
        self.assertIsInstance(sorted_list, list)
        self.assertEqual(len(pkgs), len(sorted_list))

        for pkg in sorted_list:
            self.assertIn(pkg[0], pkgs)

        self.assertEqual('python-chardet', sorted_list[0][0])
        self.assertEqual('python-requests', sorted_list[1][0])
        self.assertEqual('lutris', sorted_list[2][0])

    def test_sorting__pkg_should_be_after_its_latest_dependency(self):
        pkgs = {'abc': {'d': {'def', 'ghi'}, 'p': {'abc': 'abc'}, 'r': 'community'},
                'ghi': {'d': {'xpto'}, 'p': {'ghi': 'ghi'}, 'r': 'extra'},
                'xpto': {'d': {'zzz'}, 'p': {'xpto': 'xpto'}, 'r': 'extra'},
                'def': {'d': None, 'p': {'def': 'def'}, 'r': 'extra'}}

        for _ in range(5):  # to ensure the result is always the same
            sorted_list = sorting.sort(pkgs.keys(), pkgs)
            self.assertIsInstance(sorted_list, list)
            self.assertEqual(len(pkgs), len(sorted_list))

            for pkg in sorted_list:
                self.assertIn(pkg[0], pkgs)

            self.assertEqual('def', sorted_list[0][0])
            self.assertEqual('xpto', sorted_list[1][0])
            self.assertEqual('ghi', sorted_list[2][0])
            self.assertEqual('abc', sorted_list[3][0])

    def test_sort__two_relying_on_the_same_package(self):
        """
            dep order:
                abc -> ghi
                jkl -> ghi
                ghi -> def
                def -> mno
            expected: def, ghi, (abc | jkl )
        """
        pkgs = {'def': {'d': {'mno'}, 'p': {'def': 'def'}, 'r': 'extra'},
                'abc': {'d': {'ghi', 'xpto'}, 'p': {'abc': 'abc'}, 'r': 'extra'},
                'ghi': {'d': {'def'}, 'p': {'ghi': 'ghi'}, 'r': 'extra'},
                'jkl': {'d': {'ghi'}, 'p': {'jkl': 'jkl'}, 'r': 'extra'}}

        for _ in range(5):  # testing n times to see if the same result is produced
            sorted_list = sorting.sort(pkgs.keys(), pkgs)
            self.assertIsInstance(sorted_list, list)
            self.assertEqual(len(pkgs), len(sorted_list))

            for pkg in sorted_list:
                self.assertIn(pkg[0], pkgs)

            self.assertEqual(sorted_list[0][0], 'def')
            self.assertEqual(sorted_list[1][0], 'ghi')

            self.assertNotEqual(sorted_list[2][0],  sorted_list[3][0])
            self.assertIn(sorted_list[2][0], {'abc', 'jkl'})
            self.assertIn(sorted_list[3][0], {'abc', 'jkl'})

    def test_sort__with_cycle(self):
        """
            dep order:
                abc -> def -> ghi -> jkl -> abc
        """
        pkgs = {'def': {'d': {'ghi'}, 'p': {'def': 'def'}, 'r': 'extra'},
                'abc': {'d': {'def'}, 'p': {'abc': 'abc'}, 'r': 'extra'},
                'ghi': {'d': {'jkl'}, 'p': {'ghi': 'ghi'}, 'r': 'extra'},
                'jkl': {'d': {'abc'}, 'p': {'jkl': 'jkl'}, 'r': 'extra'}}

        sorted_list = sorting.sort(pkgs.keys(), pkgs)
        self.assertIsInstance(sorted_list, list)
        self.assertEqual(len(pkgs), len(sorted_list))

        for pkg in sorted_list:
            self.assertIn(pkg[0], pkgs)

    def test_sort__dep_provided_as_a_different_name(self):
        """
            dep order:
                abc -> fed
                def (fed)
                ghi -> abc
            expected: def, abc, ghi
        """
        pkgs = {'def': {'d': None, 'p': {'def': 'def', 'fed': 'def'}, 'r': 'extra'},
                'abc': {'d': {'fed'}, 'p': {'abc': 'abc'}, 'r': 'extra'},
                'ghi': {'d': {'abc'}, 'p': {'ghi': 'ghi'}, 'r': 'extra'}}

        for _ in range(5):
            sorted_list = sorting.sort(pkgs.keys(), pkgs)
            self.assertIsInstance(sorted_list, list)
            self.assertEqual(len(pkgs), len(sorted_list))

            for pkg in sorted_list:
                self.assertIn(pkg[0], pkgs)

            self.assertEqual(sorted_list[0][0], 'def')
            self.assertEqual(sorted_list[1][0], 'abc')
            self.assertEqual(sorted_list[2][0], 'ghi')
            
    def test_sort__aur_pkgs_should_be_always_in_the_end(self):
        """
            dep order:
                abc -> fed
                def (fed)
                ghi -> abc
            expected: def, abc, ghi
        """
        pkgs = {'def': {'d': None, 'p': {'def': 'def'}, 'r': 'aur'},
                'abc': {'d': {'ghi'}, 'p': {'abc': 'abc'}, 'r': 'extra'},
                'ghi': {'d': {'xxx'}, 'p': {'ghi': 'ghi'}, 'r': 'extra'}}

        for _ in range(5):
            sorted_list = sorting.sort(pkgs.keys(), pkgs)
            self.assertIsInstance(sorted_list, list)
            self.assertEqual(len(pkgs), len(sorted_list))

            for pkg in sorted_list:
                self.assertIn(pkg[0], pkgs)

            self.assertEqual(sorted_list[0][0], 'ghi')
            self.assertEqual(sorted_list[1][0], 'abc')
            self.assertEqual(sorted_list[2][0], 'def')
