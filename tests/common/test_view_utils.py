from unittest import TestCase

from bauh.commons.view_utils import get_human_size_str


class GetHumanSizeStrTest(TestCase):

    def test__must_properly_display_B(self):
        self.assertEqual('1023 B', get_human_size_str(1023))
        self.assertEqual('-1023 B', get_human_size_str(-1023))

    def test__must_properly_convert_to_kB(self):
        self.assertEqual('1.00 kB', get_human_size_str(1024))
        self.assertEqual('1.50 kB', get_human_size_str(1536))
        self.assertEqual('1.75 kB', get_human_size_str(1792))
        self.assertEqual('57.30 kB', get_human_size_str(58675.2))
        self.assertEqual('-1.00 kB', get_human_size_str(-1024))

    def test__must_properly_convert_to_MB(self):
        self.assertEqual('1.00 MB', get_human_size_str(1048576))
        self.assertEqual('1.20 MB', get_human_size_str(1258291))
        self.assertEqual('1.50 MB', get_human_size_str(1572864))
        self.assertEqual('57.30 MB', get_human_size_str(60083404.8))

    def test__must_properly_convert_to_GB(self):
        self.assertEqual('1.00 GB', get_human_size_str(1073741824))
        self.assertEqual('57.30 GB', get_human_size_str(61525406515.2))

    def test__must_properly_convert_to_TB(self):
        self.assertEqual('1.00 TB', get_human_size_str(1099511627776))
        self.assertEqual('57.30 TB', get_human_size_str(63002016271564.8))

    def test__must_properly_convert_to_PB(self):
        self.assertEqual('1.00 PB', get_human_size_str(1125899906842624))
        self.assertEqual('57.30 PB', get_human_size_str(64514064662082350))

    def test__must_concatenate_the_plus_sign_if_positive_sign_is_true_and_value_is_positive(self):
        self.assertEqual('+1023 B', get_human_size_str(1023, positive_sign=True))
        self.assertEqual('+1.00 kB', get_human_size_str(1024, positive_sign=True))

    def test__must_not_concatenate_the_plus_sign_if_positive_sign_is_true_and_value_is_negative(self):
        self.assertEqual('-1023 B', get_human_size_str(-1023, positive_sign=True))
        self.assertEqual('-1.00 kB', get_human_size_str(-1024, positive_sign=True))

