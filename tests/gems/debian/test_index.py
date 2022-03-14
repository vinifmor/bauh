import json
import os.path
from unittest import TestCase
from unittest.mock import Mock, patch, call

from bauh import __app_name__
from bauh.gems.debian.index import ApplicationsMapper, ApplicationIndexer
from bauh.gems.debian.model import DebianApplication
from tests.gems.debian import DEBIAN_TESTS_DIR

def mock_read_file(fpath: str):
    if fpath.endswith('firefox.desktop'):
        return """
        [Desktop Entry]
        Version=1.0
        Name=Firefox Web Browser
        Comment=Browse the World Wide Web
        GenericName=Web Browser
        Keywords=Internet;WWW;Browser;Web;Explorer
        Exec=firefox %u
        Terminal=false
        X-MultipleArgs=false
        Type=Application
        Icon=firefox
        Categories=GNOME;GTK;Network;WebBrowser;
        """
    elif fpath.endswith('synaptic.desktop'):
        return """
        [Desktop Entry]
        Name=Synaptic Package Manager
        GenericName=Package Manager
        Comment=Install, remove and upgrade software packages
        Exec=synaptic-pkexec
        Icon=synaptic
        Terminal=false
        Type=Application
        """
    elif fpath.endswith('no-icon.desktop'):
        return """
        [Desktop Entry]
        Name=No-icon
        Exec=no-icon
        Terminal=false
        Type=Application
        Categories=PackageManager;GTK;System;Settings;
        """
    elif fpath.endswith('no-exe.desktop'):
        return """
            [Desktop Entry]
            Name=No-exe
            Terminal=false
            Type=Application
            Icon=no-exe
            Categories=PackageManager;GTK;System;Settings;
            """
    elif fpath.endswith('no-display.desktop'):
        return """
                [Desktop Entry]
                Name=No-display
                Exec=no-display
                Terminal=false
                Type=Application
                Icon=no-display
                NoDisplay=true
                Categories=PackageManager;GTK;System;Settings;
                """
    elif fpath.endswith('terminal-app.desktop'):
        return """
                [Desktop Entry]
                Name=Terminal-App
                Exec=terminal-app
                Terminal=true
                Type=Application
                Icon=terminal-app
                Categories=PackageManager;GTK;System;Settings;
                """


class ApplicationsMapperTest(TestCase):

    def setUp(self):
        self.mapper = ApplicationsMapper(logger=Mock(), workers=1)

    @patch(f'{__app_name__}.gems.debian.index.ApplicationsMapper._read_file', side_effect=mock_read_file)
    @patch(f'{__app_name__}.gems.debian.index.system.execute', return_value=(0, """
    firefox: /usr/share/applications/firefox.desktop
    app-install-data: /usr/share/app-install/desktop/firefox-launchpad-plugin.desktop
    app-install-data: /usr/share/app-install/desktop/firefox:firefox.desktop
    xfce4-helpers: /usr/share/xfce4/helpers/firefox.desktop
    synaptic: /usr/share/applications/synaptic.desktop
    no-icon: /usr/share/applications/no-icon.desktop
    no-exe: /usr/share/applications/no-exe.desktop
    no-display: /usr/share/applications/no-display.desktop
    terminal-app: /usr/share/applications/terminal-app.desktop
    """))
    def test_map_executable_applications__return_applications_with_exec_and_icon(self, execute: Mock, read_file: Mock):
        apps = self.mapper.map_executable_applications()
        execute.assert_called_once_with('dpkg-query -S .desktop', shell=True)
        read_file.assert_has_calls([call('/usr/share/applications/firefox.desktop'),
                                    call('/usr/share/applications/synaptic.desktop'),
                                    call('/usr/share/applications/no-icon.desktop'),
                                    call('/usr/share/applications/no-exe.desktop')], any_order=True)

        self.assertEqual({
            DebianApplication(name='firefox', exe_path='firefox %u', icon_path='firefox',
                              categories=('GNOME', 'GTK', 'Network', 'WebBrowser')),
            DebianApplication(name='synaptic', exe_path='synaptic-pkexec', icon_path='synaptic',
                              categories=None)
        }, apps)


class ApplicationIndexerTest(TestCase):

    def setUp(self):
        self.update_idx_file_path = f'{DEBIAN_TESTS_DIR}/resources/apps_idx.json'
        self.update_idx_ts_file_path = f'{self.update_idx_file_path}.ts'
        self.app_indexer = ApplicationIndexer(logger=Mock(),
                                              index_file_path=self.update_idx_file_path)

        if os.path.exists(self.update_idx_file_path):
            os.remove(self.update_idx_file_path)

    def tearDown(self) -> None:
        if os.path.exists(self.update_idx_file_path):
            os.remove(self.update_idx_file_path)

        if os.path.exists(self.update_idx_ts_file_path):
            os.remove(self.update_idx_ts_file_path)

    def test_update_index(self):
        apps = {
            DebianApplication(name='firefox', exe_path='firefox %u', icon_path='firefox',
                              categories=('GNOME', 'GTK', 'Network', 'WebBrowser')),
            DebianApplication(name='synaptic', exe_path='synaptic-pkexec', icon_path='synaptic',
                              categories=None)
        }

        self.app_indexer.update_index(apps)

        self.assertTrue(os.path.exists(self.update_idx_file_path))

        with open(self.update_idx_file_path) as f:
            index_content = f.read()

        self.assertEqual({'firefox': {'exe_path': 'firefox %u', 'icon_path': 'firefox',
                                      'categories': ['GNOME', 'GTK', 'Network', 'WebBrowser']},
                          'synaptic': {'exe_path': 'synaptic-pkexec', 'icon_path': 'synaptic',
                                       'categories': None}
                          }, json.loads(index_content))

        self.assertTrue(os.path.isfile(self.update_idx_ts_file_path))

        with open(self.update_idx_ts_file_path) as f:
            ts_str = f.read()

        try:
            float(ts_str)
        except ValueError:
            self.assertFalse(False, "index timestamp must be a float number")

    def test_read_index(self):
        self.app_indexer._file_path = f'{DEBIAN_TESTS_DIR}/resources/app_idx_full.json'

        expected = {
            DebianApplication(name='firefox', exe_path='firefox %u', icon_path='firefox',
                              categories=('GNOME', 'GTK', 'Network', 'WebBrowser')),
            DebianApplication(name='synaptic', exe_path='synaptic-pkexec', icon_path='synaptic',
                              categories=None)
        }

        self.assertEqual(expected, {app for app in self.app_indexer.read_index()})
