from unittest import TestCase
from unittest.mock import Mock

from bauh.gems.arch.mapper import AURDataMapper
from bauh.gems.arch.model import ArchPackage


class ArchDataMapperTest(TestCase):

    def test_check_version_update(self):
        self.assertTrue(AURDataMapper.check_version_update('1.0.0-1', '1.0.0-2'))
        self.assertFalse(AURDataMapper.check_version_update('1.0.0-2', '1.0.0-1'))
        self.assertTrue(AURDataMapper.check_version_update('1.0.0-5', '1.0.1-1'))
        self.assertFalse(AURDataMapper.check_version_update('1.0.1-1', '1.0.0-1'))
        self.assertTrue(AURDataMapper.check_version_update('1.0.5-5', '1.1.0-2'))
        self.assertFalse(AURDataMapper.check_version_update('1.1.0-2', '1.0.5-5'))
        self.assertTrue(AURDataMapper.check_version_update('1.5.0-2', '1.5.1-1'))
        self.assertFalse(AURDataMapper.check_version_update('1.5.1-1', '1.5.0-2'))
        self.assertTrue(AURDataMapper.check_version_update('1.5.1-1', '1.5.1-2'))
        self.assertTrue(AURDataMapper.check_version_update('1.5.1-1', '2.0.0-1'))
        self.assertFalse(AURDataMapper.check_version_update('2.0.0-1', '1.5.1-1'))
        self.assertTrue(AURDataMapper.check_version_update('77.0.3865.90-1', '77.0.3865.120-1'))
        self.assertTrue(AURDataMapper.check_version_update('77.0.3865.90-1', '77.0.3865.90-2'))
        self.assertFalse(AURDataMapper.check_version_update('77.0.3865.900-1', '77.0.3865.120-1'))
        self.assertTrue(AURDataMapper.check_version_update('77.0.3865.120-1', '77.0.3865.900-1'))
        self.assertFalse(AURDataMapper.check_version_update('77.0.3865.120-1', '77.0.3865.90-1'))
        self.assertTrue(AURDataMapper.check_version_update('77.0.3865.a-1', '77.0.3865.b-1'))
        self.assertFalse(AURDataMapper.check_version_update('77.0.b.0-1', '77.0.a.1-1'))
        self.assertFalse(AURDataMapper.check_version_update('r25.e22697c-1', 'r8.19fe011-1'))
        self.assertTrue(AURDataMapper.check_version_update('0.9.7.RC-9', '0.9.7.RC-10'))
        self.assertFalse(AURDataMapper.check_version_update('1.1.0.r11.caacf30-1', 'r65.4c7144a-1'))
        self.assertFalse(AURDataMapper.check_version_update('1.2.16.r688.8b2c199-1', 'r2105.e91f0e9-3'))

    def test_check_version_update__versions_with_epics(self):
        self.assertTrue(AURDataMapper.check_version_update('1.2-1', '1:1.1-1'))
        self.assertFalse(AURDataMapper.check_version_update('1:1.1-1', '1.2-1'))

        self.assertTrue(AURDataMapper.check_version_update('1:1.2-1', '2:0.1-1'))
        self.assertFalse(AURDataMapper.check_version_update('2:0.1-1', '1:1.2-1'))

        self.assertTrue(AURDataMapper.check_version_update('10:1.1-1', '10:1.2-1'))
        self.assertFalse(AURDataMapper.check_version_update('10:1.2-1', '10:1.2-1'))

        self.assertTrue(AURDataMapper.check_version_update('9:1.2-1', '10:0.1-1'))

        self.assertTrue(AURDataMapper.check_version_update('9:1.1.1.1-2', '10:0.0'))
        self.assertFalse(AURDataMapper.check_version_update('10:0.0', '9:1.1.1.1-2'))

    def test_check_update__pkg_no_last_modified_and_same_versions(self):
        mapper = AURDataMapper(i18n=Mock(), logger=Mock(), http_client=Mock())
        pkg = ArchPackage(name='test')
        pkg.last_modified = None
        pkg.version = '1.0.0'
        pkg.latest_version = pkg.version

        self.assertFalse(mapper.check_update(pkg=pkg, last_modified=1608143812))

    def test_check_update__pkg_no_last_modified_and_latest_version_higher_than_version(self):
        mapper = AURDataMapper(i18n=Mock(), logger=Mock(), http_client=Mock())
        pkg = ArchPackage(name='test')
        pkg.last_modified = None
        pkg.version = '1.0.0'
        pkg.latest_version = '1.1.0'

        self.assertTrue(mapper.check_update(pkg=pkg, last_modified=1608143812))

    def test_check_update__pkg_no_last_modified_and_no_install_date_and_version_higher_than_latest_version(self):
        mapper = AURDataMapper(i18n=Mock(), logger=Mock(), http_client=Mock())
        pkg = ArchPackage(name='test')
        pkg.last_modified = None
        pkg.install_date = None
        pkg.version = '1.1.0'
        pkg.latest_version = '1.0.0'

        self.assertFalse(mapper.check_update(pkg=pkg, last_modified=1608143812))

    def test_check_update__none_last_modified_and_latest_version_higher_than_version(self):
        mapper = AURDataMapper(i18n=Mock(), logger=Mock(), http_client=Mock())
        pkg = ArchPackage(name='test')
        pkg.last_modified = 1608143812
        pkg.version = '1.0.0'
        pkg.latest_version = '1.1.0'

        self.assertTrue(mapper.check_update(pkg=pkg, last_modified=None))

    def test_check_update__none_last_modified_and_version_equal_latest_version(self):
        mapper = AURDataMapper(i18n=Mock(), logger=Mock(), http_client=Mock())
        pkg = ArchPackage(name='test')
        pkg.last_modified = 1608143812
        pkg.version = '1.0.0'
        pkg.latest_version = pkg.version

        self.assertFalse(mapper.check_update(pkg=pkg, last_modified=None))

    def test_check_update__string_last_modified_and_latest_version_higher_than_version(self):
        mapper = AURDataMapper(i18n=Mock(), logger=Mock(), http_client=Mock())
        pkg = ArchPackage(name='test')
        pkg.last_modified = 1608143812
        pkg.version = '1.0.0'
        pkg.latest_version = '1.1.0'

        self.assertTrue(mapper.check_update(pkg=pkg, last_modified='abc'))

    def test_check_update__pkg_last_modified_equal_last_modified_and_version_equal_latest_version(self):
        mapper = AURDataMapper(i18n=Mock(), logger=Mock(), http_client=Mock())
        pkg = ArchPackage(name='test')
        pkg.last_modified = 1608143812
        pkg.version = '1.0.0'
        pkg.latest_version = pkg.version

        self.assertFalse(mapper.check_update(pkg=pkg, last_modified=pkg.last_modified))

    def test_check_update__pkg_last_modified_higher_than_last_modified_and_latest_version_higher_than_version(self):
        mapper = AURDataMapper(i18n=Mock(), logger=Mock(), http_client=Mock())
        pkg = ArchPackage(name='test')
        pkg.last_modified = 1608143812
        pkg.version = '1.0.0'
        pkg.latest_version = '1.1.0'

        self.assertTrue(mapper.check_update(pkg=pkg, last_modified=pkg.last_modified - 100))

    def test_check_update__pkg_last_modified_less_than_last_modified_and_version_higher_than_latest_version(self):
        mapper = AURDataMapper(i18n=Mock(), logger=Mock(), http_client=Mock())
        pkg = ArchPackage(name='test')
        pkg.last_modified = 1608143812
        pkg.version = '2.0.0'
        pkg.latest_version = '1.0.0'

        # in this case, last modified is more relevant than the string version
        self.assertTrue(mapper.check_update(pkg=pkg, last_modified=pkg.last_modified + 100))

    def test_check_update__pkg_no_last_modified_and_install_date_less_than_last_modified_and_version_higher_than_latest(self):
        mapper = AURDataMapper(i18n=Mock(), logger=Mock(), http_client=Mock())
        pkg = ArchPackage(name='test')
        pkg.last_modified = None
        pkg.install_date = 1608143812
        pkg.version = '3.0.0'
        pkg.latest_version = '2.0.0'

        # in this case, install_date will be considered instead of package's last_modified.
        # even that 'version' is higher than 'latest_version', 'last_modified' is greater than 'install_date'
        self.assertTrue(mapper.check_update(pkg=pkg, last_modified=pkg.install_date + 100))

    def test_check_update__pkg_no_last_modified_and_install_date_higher_than_last_modified_and_version_equal_latest(self):
        mapper = AURDataMapper(i18n=Mock(), logger=Mock(), http_client=Mock())
        pkg = ArchPackage(name='test')
        pkg.last_modified = None
        pkg.install_date = 1608143812
        pkg.version = '2.0.0'
        pkg.latest_version = pkg.version

        # in this case, install_date will be considered instead of package's last_modified.
        # as 'install_date' is higher, only the string versions will be compared
        self.assertFalse(mapper.check_update(pkg=pkg, last_modified=pkg.install_date - 100))

    def test_check_update__pkg_no_last_modified_and_install_date_higher_than_last_modified_and_latest_higher(self):
        mapper = AURDataMapper(i18n=Mock(), logger=Mock(), http_client=Mock())
        pkg = ArchPackage(name='test')
        pkg.last_modified = None
        pkg.install_date = 1608143812
        pkg.version = '1.0.0'
        pkg.latest_version = '1.1.0'

        # in this case, install_date will be considered instead of package's last_modified.
        # as 'install_date' is higher, only the string versions will be compared
        self.assertTrue(mapper.check_update(pkg=pkg, last_modified=pkg.install_date - 100))

    def test_check_update__pkg_no_last_modified_and_install_date_and_no_last_modified_and_latest_higher(self):
        mapper = AURDataMapper(i18n=Mock(), logger=Mock(), http_client=Mock())
        pkg = ArchPackage(name='test')
        pkg.last_modified = None
        pkg.install_date = 1608143812
        pkg.version = '1.0.0'
        pkg.latest_version = '1.1.0'

        # in this case, install_date will be considered instead of package's last_modified.
        # as 'install_date' is higher, only the string versions will be compared
        self.assertTrue(mapper.check_update(pkg=pkg, last_modified=None))
