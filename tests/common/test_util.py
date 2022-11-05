from unittest import TestCase

from bauh.commons.util import size_to_byte, sanitize_command_input


class SizeToByteTest(TestCase):

    def test_must_return_right_number_of_bytes_for_bit_size(self):
        self.assertEqual(0.125, size_to_byte(1, 'b'))
        self.assertEqual(0.250, size_to_byte(2, 'b'))
        self.assertEqual(0.40625, size_to_byte(3.25, 'b'))

    def test_must_return_right_number_of_bytes_for_byte_based_units(self):
        self.assertEqual(1.0, size_to_byte(1, 'B'))
        self.assertEqual(587, size_to_byte(587, 'B'))
        self.assertEqual(1000, size_to_byte(1, 'K'))
        self.assertEqual(57300, size_to_byte(57.3, 'K'))
        self.assertEqual(1000000, size_to_byte(1, 'M'))
        self.assertEqual(57300000, size_to_byte(57.3, 'M'))
        self.assertEqual(1000000000, size_to_byte(1, 'G'))
        self.assertEqual(57300000000, size_to_byte(57.3, 'G'))
        self.assertEqual(1000000000000, size_to_byte(1, 'T'))
        self.assertEqual(57300000000000, size_to_byte(57.3, 'T'))
        self.assertEqual(1000000000000000, size_to_byte(1, 'P'))
        self.assertEqual(5670000000000000, size_to_byte(5.67, 'P'))

    def test_must_return_right_number_of_bytes_for_bibyte_units(self):
        self.assertEqual(1024.0, size_to_byte(1, 'KiB'))
        self.assertEqual(1579683.84, size_to_byte(1542.66, 'KiB'))
        self.assertEqual(1048576, size_to_byte(1, 'MiB'))
        self.assertEqual(4372561.92, size_to_byte(4.17, 'MiB'))
        self.assertEqual(1073741824, size_to_byte(1, 'GiB'))
        self.assertEqual(2168958484.48, size_to_byte(2.02, 'GiB'))
        self.assertEqual(1099511627776, size_to_byte(1, 'TiB'))
        self.assertEqual(3375500697272.32, size_to_byte(3.07, 'TiB'))
        self.assertEqual(1125899906842624, size_to_byte(1, 'PiB'))
        self.assertEqual(1294784892869017.5, size_to_byte(1.15, 'PiB'))

    def test_must_return_converted_string_sizes(self):
        self.assertEqual(1000, size_to_byte('1', 'K'))
        self.assertEqual(57300, size_to_byte('57.3', 'K'))
        self.assertEqual(57300000, size_to_byte('57.3', 'M'))
        self.assertEqual(57300000000, size_to_byte('57.3', 'G'))
        self.assertEqual(57300000000000, size_to_byte('57.3', 'T'))
        self.assertEqual(5670000000000000, size_to_byte('5.67', 'P'))

    def test_must_treat_string_sizes_before_converting(self):
        self.assertEqual(57300, size_to_byte(' 57 , 3  ', ' K '))


class SanitizeCommandInputTest(TestCase):

    def test__must_remove_any_forbidden_symbols(self):
        input_ = ' #$%* abc-def@ #%<<>> '
        res = sanitize_command_input(input_)
        self.assertEqual('abc-def@', res)

    def test__must_remove_single_quotes(self):
        input_ = " 'abc'-'xpto' "
        res = sanitize_command_input(input_)
        self.assertEqual('abc-xpto', res)

    def test__must_remove_double_quotes(self):
        input_ = ' "abc"-"xpto" '
        res = sanitize_command_input(input_)
        self.assertEqual('abc-xpto', res)

    def test__must_remove_the_pipe_operator(self):
        input_ = '  abc | ls /home/xpto | cat /home/xpto/secret.txt'
        res = sanitize_command_input(input_)
        self.assertEqual('abc', res)

    def test__must_remove_the_and_operator(self):
        input_ = '  abc && ls /home/xpto & cat /home/xpto/secret.txt'
        res = sanitize_command_input(input_)
        self.assertEqual('abc', res)

    def test__must_remove_several_operator(self):
        input_ = '  abc | ls /home/xpto && cat /home/xpto/secret.txt'
        res = sanitize_command_input(input_)
        self.assertEqual('abc', res)

    def test__must_remove_single_dash_parameters(self):
        input_ = '-cat abc-def -user -system ghi--jkl -xpto '
        res = sanitize_command_input(input_)
        self.assertEqual('abc-def ghi--jkl', res)

    def test__must_remove_double_dash_parameters(self):
        input_ = '--cat abc-def --user -system ghi--jkl --xpto '
        res = sanitize_command_input(input_)
        self.assertEqual('abc-def ghi--jkl', res)
