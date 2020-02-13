from unittest import TestCase

from bauh.gems.arch.mapper import ArchDataMapper


class ArchDataMapperTest(TestCase):

    def test_check_update_no_suffix(self):
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
        self.assertFalse(ArchDataMapper.check_update('1.1.0.r11.caacf30-1', 'r65.4c7144a-1'))
        self.assertFalse(ArchDataMapper.check_update('1.2.16.r688.8b2c199-1', 'r2105.e91f0e9-3'))

    def test_check_update_no_suffix_3_x_2_digits(self):
        self.assertTrue(ArchDataMapper.check_update('1.0.0-1', '1.1-1'))
        self.assertFalse(ArchDataMapper.check_update('1.2.0-1', '1.1-1'))

    def test_check_update_no_suffix_3_x_1_digits(self):
        self.assertTrue(ArchDataMapper.check_update('1.0.0-1', '2-1'))
        self.assertFalse(ArchDataMapper.check_update('2-1', '1.1-1'))

    def test_check_update_release(self):
        # RE
        self.assertTrue(ArchDataMapper.check_update('1.0.0.R-1', '1.0.0.R-2', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.R-2', '1.0.0.R-1', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.1.R-1', '1.0.0.R-5', check_suffix=True))
        self.assertTrue(ArchDataMapper.check_update('1.0.1.R-1', '1.0.1.R-2', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.2.R-1', '1.0.1.R-7', check_suffix=True))

        self.assertTrue(ArchDataMapper.check_update('1.0.0.RE-1', '1.0.0.R-2', check_suffix=True))
        self.assertTrue(ArchDataMapper.check_update('1.0.0.RELEASE-2', '1.0.0.R-5', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.1.R-1', '1.0.0.RELEASE-5', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.1.R-1', '1.0.0.RE-1', check_suffix=True))

        # GA
        self.assertFalse(ArchDataMapper.check_update('1.0.0.R-1', '1.0.0.Ge-1', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RE-1', '1.0.0.GA-1', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RELEASE-1', '1.0.0.Ge-1', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.R-1', '1.0.0.GE-1', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RE-1', '1.0.0.GE-1', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RELEASE-1', '1.0.0.GE-1', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.R-1', '1.0.0.GA-1', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RE-1', '1.0.0.GA-1', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RELEASE-1', '1.0.0.GA-1', check_suffix=True))

        self.assertTrue(ArchDataMapper.check_update('1.0.0.R-5', '1.0.1.GA-1', check_suffix=True))

        # RCS
        self.assertFalse(ArchDataMapper.check_update('1.0.0.R-1', '1.0.0.RC-1', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RE-1', '1.0.0.RC-1', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RELEASE-1', '1.0.0.RC-1', check_suffix=True))

        self.assertTrue(ArchDataMapper.check_update('1.0.0.R-5', '1.0.1.RC-1', check_suffix=True))

        # BETA
        self.assertFalse(ArchDataMapper.check_update('1.0.0.R-1', '1.0.0.B-2', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RE-1', '1.0.0.B-2', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RELEASE-1', '1.0.0.B-2', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.R-1', '1.0.0.BETA-2', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RE-1', '1.0.0.BETA-2', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RELEASE-1', '1.0.0.BETA-2', check_suffix=True))

        self.assertTrue(ArchDataMapper.check_update('1.0.0.R-5', '1.0.1.BETA-1', check_suffix=True))

        # ALPHA
        self.assertFalse(ArchDataMapper.check_update('1.0.0.R-1', '1.0.0.Alpha-2', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RE-1', '1.0.0.ALPHA-2', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RELEASE-1', '1.0.0.ALPHA-2', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.R-1', '1.0.0.ALPHA-2', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RE-1', '1.0.0.ALPHA-2', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RELEASE-1', '1.0.0.ALPHA-2', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.R-1', '1.0.0.ALFA-2', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RE-1', '1.0.0.ALFA-2', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RELEASE-1', '1.0.0.ALFA-2', check_suffix=True))

        self.assertTrue(ArchDataMapper.check_update('1.0.0.R-5', '1.0.1.Alfa-1', check_suffix=True))

        # DEV
        self.assertFalse(ArchDataMapper.check_update('1.0.0.R-1', '1.0.0.DeV-2', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RE-1', '1.0.0.DEV-2', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RELEASE-1', '1.0.0.DEVEL-2', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.R-1', '1.0.0.DEV-2', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RE-1', '1.0.0.DEV-2', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RELEASE-1', '1.0.0.DEV-2', check_suffix=True))

        self.assertTrue(ArchDataMapper.check_update('1.0.0.R-5', '1.0.1.DEV-1', check_suffix=True))

    def test_check_update_ga(self):
        # GA
        self.assertFalse(ArchDataMapper.check_update('1.0.0.GA-1', '1.0.0.GE-1', check_suffix=True))
        self.assertTrue(ArchDataMapper.check_update('1.0.0.GE-1', '1.0.0.GA-2', check_suffix=True))
        self.assertTrue(ArchDataMapper.check_update('1.0.0.GA-2', '1.0.1.GA-1', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.1.0.GE-3', '1.0.6.GE-10', check_suffix=True))

        # RC
        self.assertFalse(ArchDataMapper.check_update('1.0.0.GA-1', '1.0.0.RC-1', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.GE-1', '1.0.0.RC-1', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.GA-1', '1.0.0.RC-1', check_suffix=True))

        self.assertTrue(ArchDataMapper.check_update('1.0.0.GE-1', '1.0.1.RC-1', check_suffix=True))
        self.assertTrue(ArchDataMapper.check_update('1.0.10.GA-10', '1.1.0.RC-1', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.1.0.GE-1', '1.0.1.RC-1', check_suffix=True))

        # BETA
        self.assertFalse(ArchDataMapper.check_update('1.0.0.GA-1', '1.0.0.BETA-1', check_suffix=True))
        self.assertTrue(ArchDataMapper.check_update('1.0.0.GE-1', '1.0.1.BETA-1', check_suffix=True))

        # ALPHA
        self.assertFalse(ArchDataMapper.check_update('1.0.0.GE-1', '1.0.0.ALPHA-1', check_suffix=True))
        self.assertTrue(ArchDataMapper.check_update('1.0.0.GA-1', '1.0.1.ALPHA-1', check_suffix=True))

        # DEV
        self.assertFalse(ArchDataMapper.check_update('1.0.0.GA-1', '1.0.0.DEV-1', check_suffix=True))
        self.assertTrue(ArchDataMapper.check_update('1.0.0.GE-1', '1.0.1.DEV-1', check_suffix=True))

    def test_check_update_rc(self):
        # RC
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RC-1', '1.0.0.RC-1'))
        self.assertTrue(ArchDataMapper.check_update('1.0.0.RC-1', '1.0.0.RC-2'))
        self.assertTrue(ArchDataMapper.check_update('1.0.0.RC-2', '1.0.1.RC-1'))
        self.assertFalse(ArchDataMapper.check_update('1.1.0.RC-3', '1.0.6.RC-10'))

        # BETA
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RC-1', '1.0.0.BETA-1'))
        self.assertTrue(ArchDataMapper.check_update('1.0.0.RC-1', '1.0.1.BETA-1'))

        # ALPHA
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RC-1', '1.0.0.ALPHA-1'))
        self.assertTrue(ArchDataMapper.check_update('1.0.0.RC-1', '1.0.1.ALPHA-1'))

        # DEV
        self.assertFalse(ArchDataMapper.check_update('1.0.0.RC-1', '1.0.0.DEV-1'))
        self.assertTrue(ArchDataMapper.check_update('1.0.0.RC-1', '1.0.1.DEV-1'))

    def test_check_update_beta(self):
        # BETA
        self.assertFalse(ArchDataMapper.check_update('1.0.0.BETA-1', '1.0.0.BETA-1', check_suffix=True))
        self.assertTrue(ArchDataMapper.check_update('1.0.0.BETA-1', '1.0.0.BETA-2', check_suffix=True))
        self.assertTrue(ArchDataMapper.check_update('1.0.0.BETA-2', '1.0.1.B-1', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.1.0.B-3', '1.0.6.BETA-10', check_suffix=True))

        # ALPHA
        self.assertFalse(ArchDataMapper.check_update('1.0.0.BETA-1', '1.0.0.ALPHA-1', check_suffix=True))
        self.assertTrue(ArchDataMapper.check_update('1.0.0.B-1', '1.0.1.ALPHA-1', check_suffix=True))

        # DEV
        self.assertFalse(ArchDataMapper.check_update('1.0.0.BETA-1', '1.0.0.DEV-1', check_suffix=True))
        self.assertTrue(ArchDataMapper.check_update('1.0.0.B-1', '1.0.1.DEV-1', check_suffix=True))

    def test_check_update_alpha(self):
        # ALPHA
        self.assertFalse(ArchDataMapper.check_update('1.0.0.ALPHA-1', '1.0.0.ALPHA-1', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.ALPHA-1', '1.0.0.ALFA-1', check_suffix=True))
        self.assertTrue(ArchDataMapper.check_update('1.0.0.ALFA-1', '1.0.0.ALPHA-2', check_suffix=True))
        self.assertTrue(ArchDataMapper.check_update('1.0.0.ALPHA-2', '1.0.1.ALFA-1', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.1.0.ALFA-3', '1.0.6.ALFA-10', check_suffix=True))

        # DEV
        self.assertFalse(ArchDataMapper.check_update('1.0.0.ALFA-1', '1.0.0.DEV-1', check_suffix=True))
        self.assertTrue(ArchDataMapper.check_update('1.0.0.ALPHA-1', '1.0.1.DEV-1', check_suffix=True))

    def test_check_update_dev(self):
        self.assertFalse(ArchDataMapper.check_update('1.0.0.DEV-1', '1.0.0.DEV-1', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.DEV-1', '1.0.0.DEVEL-1', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.DEVEL-1', '1.0.0.DEVELOPMENT-1', check_suffix=True))
        self.assertTrue(ArchDataMapper.check_update('1.0.0.DEV-1', '1.0.0.DEVEL-2', check_suffix=True))
        self.assertTrue(ArchDataMapper.check_update('1.0.0.DEVEL-2', '1.0.1.DEV-1', check_suffix=True))
        self.assertFalse(ArchDataMapper.check_update('1.1.0.DEV-3', '1.0.6.DEVELOPMENT-10', check_suffix=True))

    def test_check_update_unknown_suffix(self):
        self.assertTrue(ArchDataMapper.check_update('1.0.0.BALL-1', '1.0.0.TAR-1'))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.TAR-1', '1.0.0.BALL-1'))

    def test_check_update_known_and_unknown_suffix(self):
        self.assertTrue(ArchDataMapper.check_update('1.0.0.RE-1', '1.0.0.TAR-1'))
        self.assertFalse(ArchDataMapper.check_update('1.0.0.TAR-1', '1.0.0.RE-1'))
