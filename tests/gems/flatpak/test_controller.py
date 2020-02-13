from unittest import TestCase
from unittest.mock import Mock

from bauh.gems.flatpak.controller import FlatpakManager
from bauh.gems.flatpak.model import FlatpakApplication


class FlatpakManagerSortUpdateOrderTest(TestCase):

    def setUp(self):
        self.manager = FlatpakManager(Mock())

    def test__sort_deps__only_apps(self):
        pkgs = [
            FlatpakApplication(id="org.gnome.gedit", name='Gedit', runtime=False),
            FlatpakApplication(id="com.spotify.Client", name='com.spotify.Client', runtime=False),
        ]

        sorted_list = self.manager.sort_update_order(pkgs)
        self.assertIsInstance(sorted_list, list)
        self.assertEqual(len(pkgs), len(sorted_list))

        for pkg in sorted_list:
            self.assertIn(pkg, pkgs)

    def test__sort_deps__one_app_one_runtime(self):
        pkgs = [
            FlatpakApplication(id="org.gnome.gedit", name='Gedit', runtime=False),
            FlatpakApplication(id="org.gnome.Platform", name='org.gnome.Platform', runtime=True),
        ]

        sorted_list = self.manager.sort_update_order(pkgs)
        self.assertIsInstance(sorted_list, list)
        self.assertEqual(len(pkgs), len(sorted_list))

        self.assertEqual(pkgs[1], sorted_list[0])
        self.assertEqual(pkgs[0], sorted_list[1])

    def test__sort_deps__two_apps_one_runtime(self):
        pkgs = [
            FlatpakApplication(id="org.gnome.gedit", name='Gedit', runtime=False),
            FlatpakApplication(id="org.gnome.Platform", name='org.gnome.Platform', runtime=True),
            FlatpakApplication(id="com.spotify.Client", name='com.spotify.Client', runtime=False)
        ]

        sorted_list = self.manager.sort_update_order(pkgs)
        self.assertIsInstance(sorted_list, list)
        self.assertEqual(len(pkgs), len(sorted_list))

        self.assertEqual(pkgs[1], sorted_list[0])
        self.assertEqual(pkgs[0], sorted_list[1])
        self.assertEqual(pkgs[2], sorted_list[2])

    def test_sort_deps_two_apps_two_runtimes(self):
        pkgs = [
            FlatpakApplication(id="org.gnome.gedit", name='Gedit', runtime=False),
            FlatpakApplication(id="org.gnome.Platform", name='Platform', runtime=True),
            FlatpakApplication(id="com.spotify.Client", name='Spotify', runtime=False),
            FlatpakApplication(id="org.freedesktop.Platform.GL.default", name='default', runtime=True)
        ]

        sorted_list = self.manager.sort_update_order(pkgs)
        self.assertIsInstance(sorted_list, list)
        self.assertEqual(len(pkgs), len(sorted_list))

        self.assertEqual(pkgs[1], sorted_list[0])
        self.assertEqual(pkgs[3], sorted_list[1])
        self.assertEqual(pkgs[0], sorted_list[2])
        self.assertEqual(pkgs[2], sorted_list[3])

    def test_sort_deps_two_apps_two_runtimes_one_partial(self):
        gnome_platform = FlatpakApplication(id="org.gnome.Platform", name='Platform', runtime=True)
        gnome_locale = FlatpakApplication(id="org.gnome.Platform.Locale", name="Locale", runtime=True, partial=True)
        gnome_locale.base_id = gnome_platform.id

        pkgs = [
            FlatpakApplication(id="org.gnome.gedit", name='Gedit', runtime=False),
            gnome_platform,
            FlatpakApplication(id="com.spotify.Client", name='Spotify', runtime=False),
            FlatpakApplication(id="org.freedesktop.Platform.GL.default", name='default', runtime=True),
            gnome_locale
        ]

        sorted_list = self.manager.sort_update_order(pkgs)
        self.assertIsInstance(sorted_list, list)
        self.assertEqual(len(pkgs), len(sorted_list))

        self.assertEqual(pkgs[4], sorted_list[0])
        self.assertEqual(pkgs[1], sorted_list[1])
        self.assertEqual(pkgs[3], sorted_list[2])
        self.assertEqual(pkgs[0], sorted_list[3])
        self.assertEqual(pkgs[2], sorted_list[4])

    def test_sort_deps_two_apps_two_runtimes_two_partials(self):
        gnome_platform = FlatpakApplication(id="org.gnome.Platform", name='Platform', runtime=True)
        gnome_locale = FlatpakApplication(id="org.gnome.Platform.Locale", name="Locale", runtime=True, partial=True)
        gnome_locale.base_id = gnome_platform.id

        platform_default = FlatpakApplication(id="org.freedesktop.Platform.GL.default", name='default', runtime=True)
        platform_locale = FlatpakApplication(id="org.freedesktop.Platform.GL.Locale", name='Locale', runtime=True, partial=True)
        platform_locale.base_id = platform_default.id

        pkgs = [
            platform_locale,
            FlatpakApplication(id="org.gnome.gedit", name='Gedit', runtime=False),
            gnome_platform,
            FlatpakApplication(id="com.spotify.Client", name='Spotify', runtime=False),
            platform_default,
            gnome_locale
        ]

        sorted_list = self.manager.sort_update_order(pkgs)
        self.assertIsInstance(sorted_list, list)
        self.assertEqual(len(pkgs), len(sorted_list))

        self.assertEqual(gnome_locale.id, sorted_list[0].id)
        self.assertEqual(gnome_platform.id, sorted_list[1].id)
        self.assertEqual(platform_locale.id, sorted_list[2].id)
        self.assertEqual(platform_default.id, sorted_list[3].id)
        self.assertEqual('org.gnome.gedit', sorted_list[4].id)
        self.assertEqual('com.spotify.Client', sorted_list[5].id)
