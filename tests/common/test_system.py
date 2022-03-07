from unittest import TestCase

from bauh.commons import system


class GetHumanSizeStr(TestCase):

    def test__must_return_1Kb_for_1024(self):
        self.assertEqual('1.00 Kb', system.get_human_size_str(1024))

    def test__must_return_1_5Kb_for_1536(self):
        self.assertEqual('1.50 Kb', system.get_human_size_str(1536))

    def test__must_return_1_75Kb_for_1792(self):
        self.assertEqual('1.75 Kb', system.get_human_size_str(1792))

    def test__must_return_1Mb_for_1048576(self):
        self.assertEqual('1.00 Mb', system.get_human_size_str(1048576))

    def test__must_return_1_2Mb_for_1258291(self):
        self.assertEqual('1.20 Mb', system.get_human_size_str(1258291))

    def test__must_return_1_5Mb_for_1572864(self):
        self.assertEqual('1.50 Mb', system.get_human_size_str(1572864))

    def test__must_return_1Gb_for_1073741824(self):
        self.assertEqual('1.00 Gb', system.get_human_size_str(1073741824))

    def test__must_return_1Tb_for_1099511627776(self):
        self.assertEqual('1.00 Tb', system.get_human_size_str(1099511627776))

    def test__must_return_1Pb_for_1125899906842624(self):
        self.assertEqual('1.00 Pb', system.get_human_size_str(1125899906842624))
