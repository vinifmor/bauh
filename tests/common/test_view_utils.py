import locale
from unittest import TestCase

from bauh.commons.view_utils import get_human_size_str


class GetHumanSizeStrTest(TestCase):

    def setUp(self):
        try:
            locale.setlocale(locale.LC_NUMERIC, "C")
        except:
            print("Error: could not set locale.LC_NUMERIC to None")

    def test__must_properly_display_B(self):
        self.assertEqual('1 B', get_human_size_str(1))
        self.assertEqual('999 B', get_human_size_str(999))
        self.assertEqual('-999 B', get_human_size_str(-999))

    def test__must_properly_convert_to_kB(self):
        self.assertEqual('1.00 kB', get_human_size_str(1000))
        self.assertEqual('-1.00 kB', get_human_size_str(-1000))
        self.assertEqual('1.50 kB', get_human_size_str(1500))
        self.assertEqual('1.75 kB', get_human_size_str(1750))
        self.assertEqual('57.30 kB', get_human_size_str(57300))

    def test__must_properly_convert_to_MB(self):
        self.assertEqual('1.00 MB', get_human_size_str(1000 ** 2))
        self.assertEqual('-1.00 MB', get_human_size_str(1000 ** 2 * -1))
        self.assertEqual('1.20 MB', get_human_size_str(1000 ** 2 * 1.2))
        self.assertEqual('1.50 MB', get_human_size_str(1000 ** 2 * 1.5))
        self.assertEqual('57.30 MB', get_human_size_str(1000 ** 2 * 57.3))

    def test__must_properly_convert_to_GB(self):
        self.assertEqual('1.00 GB', get_human_size_str(1000 ** 3))
        self.assertEqual('-1.00 GB', get_human_size_str(1000 ** 3 * -1))
        self.assertEqual('57.30 GB', get_human_size_str(1000 ** 3 * 57.3))

    def test__must_properly_convert_to_TB(self):
        self.assertEqual('1.00 TB', get_human_size_str(1000 ** 4))
        self.assertEqual('-1.00 TB', get_human_size_str(1000 ** 4 * -1))
        self.assertEqual('57.30 TB', get_human_size_str(1000 ** 4 * 57.3))

    def test__must_properly_convert_to_PB(self):
        self.assertEqual('1.00 PB', get_human_size_str(1000 ** 5))
        self.assertEqual('-1.00 PB', get_human_size_str(1000 ** 5 * -1))
        self.assertEqual('57.30 PB', get_human_size_str(1000 ** 5 * 57.3))

    def test__must_concatenate_the_plus_sign_if_positive_sign_is_true_and_value_is_positive(self):
        self.assertEqual('+999 B', get_human_size_str(999, positive_sign=True))
        self.assertEqual('+1.00 kB', get_human_size_str(1000, positive_sign=True))

    def test__must_not_concatenate_the_plus_sign_if_positive_sign_is_true_and_value_is_negative(self):
        self.assertEqual('-999 B', get_human_size_str(-999, positive_sign=True))
        self.assertEqual('-1.00 kB', get_human_size_str(-1000, positive_sign=True))

