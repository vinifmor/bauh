from unittest import TestCase
from unittest.mock import MagicMock, patch, Mock

from bauh import __app_name__
from bauh.api.abstract.controller import SearchResult
from bauh.gems.debian.controller import DebianPackageManager
from bauh.gems.debian.model import DebianPackage, DebianApplication


class DebianPackageManagerTest(TestCase):

    def setUp(self):
        self.controller = DebianPackageManager(MagicMock())
        self.controller._apps_index = {}

    @patch(f'{__app_name__}.gems.debian.controller.Aptitude.read_installed', return_value=iter((
            DebianPackage(name='gir1.2-javascriptcoregtk-4.0', version='2.34.1-0distro0.20.04.1',
                          latest_version='2.34.1-0distro0.20.04.1',
                          maintainer='Distro Developers', update=False, installed=True,
                          description='JavaScript engine library from WebKitGTK - GObject introspection data'),
            DebianPackage(name='xwayland', version='2:1.20.13-1distro1~20.04.2',
                          latest_version='2:1.20.13-1distro1~20.04.2',
                          maintainer='Distro X-SWAT', update=False, installed=True,
                          description='Xwayland X server')
    )))
    def test_read_installed__must_associated_packages_found_to_applications_if_appliable(self, read_installed: Mock):
        app = DebianApplication(name='xwayland', exe_path='xwayland', icon_path='xwayland', categories=('app',))

        self.controller.__apps_index = {'xwayland': app}

        result = self.controller.read_installed(disk_loader=None, pkg_types=None, internet_available=False)
        read_installed.assert_called_once()

        self.assertIsNone(result.new)

        expected = [DebianPackage(name='gir1.2-javascriptcoregtk-4.0', version='2.34.1-0distro0.20.04.1', latest_version='2.34.1-0distro0.20.04.1',
                                  maintainer='Distro Developers', update=False, installed=True,
                                  description='JavaScript engine library from WebKitGTK - GObject introspection data'),
                    DebianPackage(name='xwayland', version='2:1.20.13-1distro1~20.04.2', latest_version='2:1.20.13-1distro1~20.04.2',
                                  maintainer='Distro X-SWAT', update=False, installed=True,
                                  description='Xwayland X server', app=app)
                    ]

        self.assertEqual(expected, result.installed)

    @patch(f'{__app_name__}.gems.debian.controller.Aptitude.read_installed', return_value=iter((
            DebianPackage(name='gir1.2-javascriptcoregtk-4.0', version='2.34.1-0distro0.20.04.1',
                          latest_version='2.34.1-0distro0.20.04.1',
                          maintainer='Distro Developers', update=False, installed=True,
                          description='JavaScript engine library from WebKitGTK - GObject introspection data'),
            DebianPackage(name='xwayland', version='2:1.20.13-1distro1~20.04.2',
                          latest_version='2:1.20.13-1distro1~20.04.2',
                          maintainer='Distro X-SWAT', update=False, installed=True,
                          description='Xwayland X server')
    )))
    def test_read_installed__internet_not_available(self, read_installed: Mock):
        result = self.controller.read_installed(disk_loader=None, pkg_types=None, internet_available=False)
        read_installed.assert_called_once()

        self.assertIsNone(result.new)

        expected = [DebianPackage(name='gir1.2-javascriptcoregtk-4.0', version='2.34.1-0distro0.20.04.1', latest_version='2.34.1-0distro0.20.04.1',
                                  maintainer='Distro Developers', update=False, installed=True,
                                  description='JavaScript engine library from WebKitGTK - GObject introspection data'),
                    DebianPackage(name='xwayland', version='2:1.20.13-1distro1~20.04.2', latest_version='2:1.20.13-1distro1~20.04.2',
                                  maintainer='Distro X-SWAT', update=False, installed=True,
                                  description='Xwayland X server')
                    ]

        self.assertEqual(expected, result.installed)

    @patch(f'{__app_name__}.gems.debian.controller.Aptitude.read_installed')
    def test_search__must_return_empty_result_when_url(self, read_installed: Mock):
        words = 'i'
        res = self.controller.search(words=words, disk_loader=None, limit=-1, is_url=True)
        read_installed.assert_not_called()
        self.assertEqual(SearchResult.empty(), res)

    @patch(f'{__app_name__}.gems.debian.controller.Aptitude.search', return_value=iter((
        DebianPackage(name='xpto', version='1.0', latest_version='1.0', installed=True, update=False, description=''),
        DebianPackage(name='test', version='1.0', latest_version='1.0', installed=False, update=False, description=''),
        DebianPackage(name='myapp', version='1.0', latest_version='1.0', installed=True, update=False, description=''),
    )))
    def test_search__returned_packages_should_be_associated_with_apps_if_appliable(self, search: Mock):
        app = DebianApplication(name='myapp', exe_path='myapp', icon_path='myapp',
                                                                  categories=('app',))
        self.controller._apps_index = {'myapp': app}

        words = 'test'
        res = self.controller.search(words=words, disk_loader=None, limit=-1, is_url=False)
        search.assert_called_once_with(words)

        self.assertEqual([DebianPackage(name='xpto', version='1.0', latest_version='1.0', installed=True, update=False, description=''),
                          DebianPackage(name='myapp', version='1.0', latest_version='1.0', installed=True, update=False,
                                        description='', app=app)
                          ], res.installed)

        self.assertEqual([DebianPackage(name='test', version='1.0', latest_version='1.0', installed=False, update=False, description='')],
                         res.new)
