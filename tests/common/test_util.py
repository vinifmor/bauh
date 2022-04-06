from unittest import TestCase

from bauh.commons.util import size_to_byte


class SizeToByteTest(TestCase):

    def test_must_return_right_number_of_bytes(self):
        self.assertEqual(1.0, size_to_byte(1, 'B'))
        self.assertEqual(1024, size_to_byte(1, 'K'))
        self.assertEqual(58675.2, size_to_byte(57.3, 'K'))
        self.assertEqual(1048576, size_to_byte(1, 'M'))
        self.assertEqual(60083404.8, size_to_byte(57.3, 'M'))
        self.assertEqual(1073741824, size_to_byte(1, 'G'))
        self.assertEqual(61525406515.2, size_to_byte(57.3, 'G'))
        self.assertEqual(1099511627776, size_to_byte(1, 'T'))
        self.assertEqual(63002016271564.8, size_to_byte(57.3, 'T'))
        self.assertEqual(1125899906842624, size_to_byte(1, 'P'))
        self.assertEqual(6383852471797678, size_to_byte(5.67, 'P'))

    def test_must_return_right_number_of_bytes_for_bit_units(self):
        self.assertEqual(1, size_to_byte(8, 'b'))
        self.assertEqual(2, size_to_byte(16, 'b'))
        self.assertEqual(128, size_to_byte(1, 'KiB'))
        self.assertEqual(197460.48, size_to_byte(1542.66, 'KiB'))
        self.assertEqual(131072, size_to_byte(1, 'MiB'))
        self.assertEqual(546570.24, size_to_byte(4.17, 'MiB'))
        self.assertEqual(134217728, size_to_byte(1, 'GiB'))
        self.assertEqual(2691065446.4, size_to_byte(20.05, 'GiB'))
        self.assertEqual(137438953472, size_to_byte(1, 'TiB'))
        self.assertEqual(6926923254988.8, size_to_byte(50.4, 'TiB'))
        self.assertEqual(140737488355328, size_to_byte(1, 'PiB'))
        self.assertEqual(330733097635020.8, size_to_byte(2.35, 'PiB'))

    def test_must_return_converted_string_sizes(self):
        self.assertEqual(1024, size_to_byte('1', 'K'))
        self.assertEqual(58675.2, size_to_byte('57.3', 'K'))
        self.assertEqual(60083404.8, size_to_byte('57.3', 'M'))
        self.assertEqual(61525406515.2, size_to_byte('57.3', 'G'))
        self.assertEqual(63002016271564.8, size_to_byte('57.3', 'T'))
        self.assertEqual(6383852471797678, size_to_byte('5.67', 'P'))

    def test_must_treat_string_sizes_before_converting(self):
        self.assertEqual(58675.2, size_to_byte(' 57 , 3  ', ' K '))
