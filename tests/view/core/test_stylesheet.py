from unittest import TestCase

from bauh import stylesheet


class StylesheetTest(TestCase):

    def test__process_var_of_vars__it_should_remove_vars_pointing_to_themselves(self):
        var_map = {
            'abc': 'aaa',
            'xxx': '@xxx'
        }

        stylesheet.process_var_of_vars(var_map)

        self.assertEqual(1, len(var_map))
        self.assertIn('abc', var_map)
        self.assertEqual('aaa', var_map['abc'])

    def test__process_var_of_vars__it_should_remove_vars_pointing_to_unknown_vars(self):
        var_map = {
            'abc': 'aaa',
            'xxx': '@def'
        }

        stylesheet.process_var_of_vars(var_map)

        self.assertEqual(1, len(var_map))
        self.assertIn('abc', var_map)
        self.assertEqual('aaa', var_map['abc'])

    def test__process_var_of_vars__it_should_not_replace_invalid_expressions(self):
        var_map = {
            'abc': 'aaa',
            'bcd': '@ xpto'  # has a space between @ and 'xpto'
        }

        self.assertEqual(2, len(var_map))
        self.assertIn('abc', var_map)
        self.assertEqual('aaa', var_map['abc'])
        self.assertIn('bcd', var_map)
        self.assertEqual('@ xpto', var_map['bcd'])

    def test__process_var_of_vars__it_should_replace_value_at_first_iteration(self):
        var_map = {
            'abc': 'aaa',
            'xxx': '@abc'
        }

        stylesheet.process_var_of_vars(var_map)

        self.assertEqual(2, len(var_map))
        self.assertIn('abc', var_map)
        self.assertEqual('aaa', var_map['abc'])
        self.assertIn('xxx', var_map)
        self.assertEqual('aaa', var_map['xxx'])

    def test__process_var_of_vars__it_should_replace_value_at_second_iteration(self):
        var_map = {
            'abc': 'aaa',
            'def': '@abc',
            'xxx': '@def'
        }

        stylesheet.process_var_of_vars(var_map)

        self.assertEqual(3, len(var_map))
        self.assertIn('abc', var_map)
        self.assertEqual('aaa', var_map['abc'])
        self.assertIn('def', var_map)
        self.assertEqual('aaa', var_map['def'])
        self.assertIn('xxx', var_map)
        self.assertEqual('aaa', var_map['xxx'])

    def test__process_var_of_vars__it_should_replace_value_at_third_iteration(self):
        var_map = {
            'abc': 'aaa',
            'def': '@abc',
            'fgh': '@def',
            'xxx': '@fgh'
        }

        stylesheet.process_var_of_vars(var_map)

        self.assertEqual(4, len(var_map))
        self.assertIn('abc', var_map)
        self.assertEqual('aaa', var_map['abc'])
        self.assertIn('def', var_map)
        self.assertEqual('aaa', var_map['def'])
        self.assertIn('fgh', var_map)
        self.assertEqual('aaa', var_map['fgh'])
        self.assertIn('xxx', var_map)
        self.assertEqual('aaa', var_map['xxx'])

    def test__process_var_of_vars__it_should_replace_multiple_vars(self):
        var_map = {
            'abc': 'aaa',
            'def': '@abc',
            'fgh': 'bbb',
            'ijk': '@fgh',
            'lmn': '@ijk'
        }

        stylesheet.process_var_of_vars(var_map)

        self.assertEqual(5, len(var_map))
        self.assertIn('abc', var_map)
        self.assertEqual('aaa', var_map['abc'])
        self.assertIn('def', var_map)
        self.assertEqual('aaa', var_map['def'])
        self.assertIn('fgh', var_map)
        self.assertEqual('bbb', var_map['fgh'])
        self.assertIn('ijk', var_map)
        self.assertEqual('bbb', var_map['ijk'])
        self.assertIn('lmn', var_map)
        self.assertEqual('bbb', var_map['lmn'])
