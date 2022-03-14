from unittest import TestCase

from bauh.commons.util import size_to_byte


class SizeToByteTest(TestCase):

    def test_must_return_right_number_of_bytes(self):
        self.assertEqual(round(float('58675.2')), size_to_byte(57.3, 'K'))
        self.assertEqual(round(float('60083404.8')), size_to_byte(57.3, 'M'))
        self.assertEqual(round(float('61525406515.2')), size_to_byte(57.3, 'G'))
        self.assertEqual(round(float('63002016271564.8')), size_to_byte(57.3, 'T'))
        self.assertEqual(round(float('64514064662082350')), size_to_byte(57.3, 'P'))
