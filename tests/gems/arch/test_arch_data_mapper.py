from unittest import TestCase

from bauh.gems.arch.mapper import ArchDataMapper


class ArchDataMapperTest(TestCase):

    def test_check_update(self):
        self.assertTrue(ArchDataMapper.check_update('1.0.0-1', '1.0.0-2'))
        self.assertFalse(ArchDataMapper.check_update('1.0.0-2', '1.0.0-1'))
        self.assertTrue(ArchDataMapper.check_update('1.0.0-5', '1.0.1-1'))
        self.assertFalse(ArchDataMapper.check_update('1.0.1-1', '1.0.0-1'))
        self.assertTrue(ArchDataMapper.check_update('1.0.5-5', '1.1.0-2'))
        self.assertFalse(ArchDataMapper.check_update('1.1.0-2', '1.0.5-5'))
        self.assertTrue(ArchDataMapper.check_update('1.5.0-2', '1.5.1-1'))
        self.assertFalse(ArchDataMapper.check_update('1.5.1-1', '1.5.0-2'))
        self.assertTrue(ArchDataMapper.check_update('1.5.1-1', '1.5.1-2'))
        self.assertTrue(ArchDataMapper.check_update('1.5.1-1', '2.0.0-1'))
        self.assertFalse(ArchDataMapper.check_update('2.0.0-1', '1.5.1-1'))
        self.assertTrue(ArchDataMapper.check_update('77.0.3865.90-1', '77.0.3865.120-1'))
        self.assertTrue(ArchDataMapper.check_update('77.0.3865.90-1', '77.0.3865.90-2'))
        self.assertFalse(ArchDataMapper.check_update('77.0.3865.900-1', '77.0.3865.120-1'))
        self.assertTrue(ArchDataMapper.check_update('77.0.3865.120-1', '77.0.3865.900-1'))
        self.assertFalse(ArchDataMapper.check_update('77.0.3865.120-1', '77.0.3865.90-1'))
        self.assertTrue(ArchDataMapper.check_update('77.0.3865.a-1', '77.0.3865.b-1'))
        self.assertFalse(ArchDataMapper.check_update('77.0.b.0-1', '77.0.a.1-1'))
        self.assertFalse(ArchDataMapper.check_update('r25.e22697c-1', 'r8.19fe011-1'))
        self.assertTrue(ArchDataMapper.check_update('0.9.7.RC-9', '0.9.7.RC-10'))
        self.assertFalse(ArchDataMapper.check_update('1.1.0.r11.caacf30-1', 'r65.4c7144a-1'))
        self.assertFalse(ArchDataMapper.check_update('1.2.16.r688.8b2c199-1', 'r2105.e91f0e9-3'))

    def test_check_update__versions_with_epics(self):
        self.assertTrue(ArchDataMapper.check_update('1.2-1', '1:1.1-1'))
        self.assertFalse(ArchDataMapper.check_update('1:1.1-1', '1.2-1'))

        self.assertTrue(ArchDataMapper.check_update('1:1.2-1', '2:0.1-1'))
        self.assertFalse(ArchDataMapper.check_update('2:0.1-1', '1:1.2-1'))

        self.assertTrue(ArchDataMapper.check_update('10:1.1-1', '10:1.2-1'))
        self.assertFalse(ArchDataMapper.check_update('10:1.2-1', '10:1.2-1'))

        self.assertTrue(ArchDataMapper.check_update('9:1.2-1', '10:0.1-1'))

        self.assertTrue(ArchDataMapper.check_update('9:1.1.1.1-2', '10:0.0'))
        self.assertFalse(ArchDataMapper.check_update('10:0.0', '9:1.1.1.1-2'))
