from unittest import TestCase

from bauh.commons.view_utils import get_human_size_str


class GetHumanSizeStrTest(TestCase):

    def test__must_properly_display_B(self):
        self.assertEqual('1023 B', get_human_size_str(1023))
        self.assertEqual('-1023 B', get_human_size_str(-1023))

    def test__must_properly_convert_to_Kb(self):
        self.assertEqual('1.00 Kb', get_human_size_str(1024))
        self.assertEqual('1.50 Kb', get_human_size_str(1536))
        self.assertEqual('1.75 Kb', get_human_size_str(1792))
        self.assertEqual('57.30 Kb', get_human_size_str(58675.2))
        self.assertEqual('-1.00 Kb', get_human_size_str(-1024))

    def test__must_properly_convert_to_Mb(self):
        self.assertEqual('1.00 Mb', get_human_size_str(1048576))
        self.assertEqual('1.20 Mb', get_human_size_str(1258291))
        self.assertEqual('1.50 Mb', get_human_size_str(1572864))
        self.assertEqual('57.30 Mb', get_human_size_str(60083404.8))

    def test__must_properly_convert_to_Gb(self):
        self.assertEqual('1.00 Gb', get_human_size_str(1073741824))
        self.assertEqual('57.30 Gb', get_human_size_str(61525406515.2))

    def test__must_properly_convert_to_Tb(self):
        self.assertEqual('1.00 Tb', get_human_size_str(1099511627776))
        self.assertEqual('57.30 Tb', get_human_size_str(63002016271564.8))

    def test__must_properly_convert_to_Pb(self):
        self.assertEqual('1.00 Pb', get_human_size_str(1125899906842624))
        self.assertEqual('57.30 Pb', get_human_size_str(64514064662082350))
