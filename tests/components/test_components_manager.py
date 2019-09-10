from unittest import TestCase
from unittest.mock import MagicMock

from bauh_api.abstract.component import Component, ComponentType

from bauh.components.manager import PythonComponentsManager


class PythonComponentsManagerTest(TestCase):

    def setUp(self):
        self.github_client = MagicMock()
        self.manager = PythonComponentsManager(MagicMock(), self.github_client)

    def test_list_updates__it_should_return_only_an_api_update_when_its_available(self):

        # setup
        comps = {
            ComponentType.APPLICATION:  {'bauh': Component('bauh', '0.1.0', '0.1.0', ComponentType.APPLICATION, [])},
            ComponentType.LIBRARY: {
                'bauh_api': Component('bauh_api', '0.1.0', '0.1.1', ComponentType.LIBRARY, []),
                'bauh_commons': Component('bauh_commons', '0.1.0', '0.1.0', ComponentType.LIBRARY, [])
            },
            ComponentType.GEM: {'bauh_snap': Component('bauh_snap', '0.1.0', '0.1.0', ComponentType.GEM, [])}
        }

        self.manager.list_components = MagicMock()
        self.manager.list_components.return_value = comps

        def get_requirements(name, version):
            return "bauh_api>=0.1,<0.2,{}".format('\nbauh_commons>=0.1,<0.2' if name != 'bauh_commons' else '')

        self.github_client.get_requirements.side_effect = get_requirements

        # test
        updates = self.manager.list_updates()
        self.assertIsNotNone(updates)
        self.assertEqual(1, len(updates))
        self.assertEqual(comps[ComponentType.LIBRARY]['bauh_api'], updates[0])
        self.assertFalse(updates[0].conflicts)

    def test_list_updates__it_should_return_only_a_commons_update_when_its_available(self):

        # setup
        comps = {
            ComponentType.APPLICATION:  {'bauh': Component('bauh', '0.1.0', '0.1.0', ComponentType.APPLICATION, [])},
            ComponentType.LIBRARY: {
                'bauh_api': Component('bauh_api', '0.1.0', '0.1.0', ComponentType.LIBRARY, []),
                'bauh_commons': Component('bauh_commons', '0.1.0', '0.1.1', ComponentType.LIBRARY, [])
            },
            ComponentType.GEM: {'bauh_snap': Component('bauh_snap', '0.1.0', '0.1.0', ComponentType.GEM, [])}
        }

        self.manager.list_components = MagicMock()
        self.manager.list_components.return_value = comps

        def get_requirements(name, version):
            return "bauh_api>=0.1,<0.2,{}".format('\nbauh_commons>=0.1,<0.2' if name != 'bauh_commons' else '')

        self.github_client.get_requirements.side_effect = get_requirements

        # test
        updates = self.manager.list_updates()
        self.assertIsNotNone(updates)
        self.assertEqual(1, len(updates))
        self.assertEqual(comps[ComponentType.LIBRARY]['bauh_commons'], updates[0])
        self.assertFalse(updates[0].conflicts)

    def test_list_updates__it_should_return_an_api_update_and_its_conflicting_components(self):

        # setup
        comps = {
            ComponentType.APPLICATION:  {'bauh': Component('bauh', '0.1.0', '0.1.0', ComponentType.APPLICATION, [])},
            ComponentType.LIBRARY: {
                'bauh_api': Component('bauh_api', '0.1.0', '0.2.0', ComponentType.LIBRARY, []),
                'bauh_commons': Component('bauh_commons', '0.1.0', '0.1.0', ComponentType.LIBRARY, [])
            },
            ComponentType.GEM: {'bauh_snap': Component('bauh_snap', '0.1.0', '0.1.0', ComponentType.GEM, [])}
        }

        self.manager.list_components = MagicMock()
        self.manager.list_components.return_value = comps

        def get_requirements(name, version):
            return "bauh_api>=0.1,<0.2,{}".format('\nbauh_commons>=0.1,<0.2' if name != 'bauh_commons' else '')

        self.github_client.get_requirements.side_effect = get_requirements

        # test
        updates = self.manager.list_updates()
        self.assertIsNotNone(updates)
        self.assertEqual(1, len(updates))
        self.assertEqual(comps[ComponentType.LIBRARY]['bauh_api'], updates[0])
        self.assertTrue(updates[0].conflicts)

        self.assertEqual(3, len(updates[0].conflicts))
        self.assertIn(comps[ComponentType.LIBRARY]['bauh_commons'], updates[0].conflicts)
        self.assertEqual(1, len(comps[ComponentType.LIBRARY]['bauh_commons'].conflicts))
        self.assertIn(comps[ComponentType.LIBRARY]['bauh_api'], comps[ComponentType.LIBRARY]['bauh_commons'].conflicts)

        self.assertIn(comps[ComponentType.APPLICATION]['bauh'], updates[0].conflicts)
        self.assertEqual(1, len(comps[ComponentType.APPLICATION]['bauh'].conflicts))
        self.assertIn(comps[ComponentType.LIBRARY]['bauh_api'], comps[ComponentType.APPLICATION]['bauh'].conflicts)

        self.assertIn(comps[ComponentType.GEM]['bauh_snap'], updates[0].conflicts)
        self.assertEqual(1, len(comps[ComponentType.GEM]['bauh_snap'].conflicts))
        self.assertIn(comps[ComponentType.LIBRARY]['bauh_api'], comps[ComponentType.GEM]['bauh_snap'].conflicts)

    def test_list_updates__it_should_return_a_gui_update_with_the_installed_api_as_a_conflict(self):

        # setup
        comps = {
            ComponentType.APPLICATION:  {'bauh': Component('bauh', '0.1.0', '0.2.0', ComponentType.APPLICATION, [])},
            ComponentType.LIBRARY: {
                'bauh_api': Component('bauh_api', '0.1.0', '0.1.0', ComponentType.LIBRARY, []),
                'bauh_commons': Component('bauh_commons', '0.1.0', '0.1.0', ComponentType.LIBRARY, [])
            },
            ComponentType.GEM: {'bauh_snap': Component('bauh_snap', '0.1.0', '0.1.0', ComponentType.GEM, [])}
        }

        self.manager.list_components = MagicMock()
        self.manager.list_components.return_value = comps

        def get_requirements(name, version):
            if name == 'bauh':
                return 'bauh_api>=0.2;\nbauh_commons>=0.1,<0.2'
            else:
                return "bauh_api>=0.1,<0.2,{}".format('\nbauh_commons>=0.1,<0.2' if name != 'bauh_commons' else '')

        self.github_client.get_requirements.side_effect = get_requirements

        # test
        updates = self.manager.list_updates()
        self.assertIsNotNone(updates)
        self.assertEqual(1, len(updates))
        self.assertEqual(comps[ComponentType.APPLICATION]['bauh'], updates[0])
        self.assertTrue(updates[0].conflicts)
        self.assertEqual(1, len(updates[0].conflicts))
        self.assertIn(comps[ComponentType.LIBRARY]['bauh_api'], updates[0].conflicts)

    def test_list_updates__it_should_return_a_gui_update_with_the_installed_commons_as_a_conflict(self):

        # setup
        comps = {
            ComponentType.APPLICATION:  {'bauh': Component('bauh', '0.1.0', '0.2.0', ComponentType.APPLICATION, [])},
            ComponentType.LIBRARY: {
                'bauh_api': Component('bauh_api', '0.1.0', '0.1.0', ComponentType.LIBRARY, []),
                'bauh_commons': Component('bauh_commons', '0.1.0', '0.1.0', ComponentType.LIBRARY, [])
            },
            ComponentType.GEM: {'bauh_snap': Component('bauh_snap', '0.1.0', '0.1.0', ComponentType.GEM, [])}
        }

        self.manager.list_components = MagicMock()
        self.manager.list_components.return_value = comps

        def get_requirements(name, version):
            if name == 'bauh':
                return 'bauh_api>=0.1,<0.2;\nbauh_commons>=0.2,<0.3'
            else:
                return "bauh_api>=0.1,<0.2,{}".format('\nbauh_commons>=0.1,<0.2' if name != 'bauh_commons' else '')

        self.github_client.get_requirements.side_effect = get_requirements

        # test
        updates = self.manager.list_updates()
        self.assertIsNotNone(updates)
        self.assertEqual(1, len(updates))
        self.assertEqual(comps[ComponentType.APPLICATION]['bauh'], updates[0])
        self.assertTrue(updates[0].conflicts)
        self.assertEqual(1, len(updates[0].conflicts))
        self.assertIn(comps[ComponentType.LIBRARY]['bauh_commons'], updates[0].conflicts)

    def test_list_updates__it_should_return_a_gui_update_if_its_compatible_with_the_api_and_commons_updates(self):

        # setup
        comps = {
            ComponentType.APPLICATION:  {'bauh': Component('bauh', '0.1.0', '0.2.0', ComponentType.APPLICATION, [])},
            ComponentType.LIBRARY: {
                'bauh_api': Component('bauh_api', '0.1.2', '0.1.4', ComponentType.LIBRARY, []),
                'bauh_commons': Component('bauh_commons', '0.1.2', '0.1.6', ComponentType.LIBRARY, [])
            },
            ComponentType.GEM: {'bauh_snap': Component('bauh_snap', '0.1.0', '0.1.0', ComponentType.GEM, [])}
        }

        self.manager.list_components = MagicMock()
        self.manager.list_components.return_value = comps

        def get_requirements(name, version):
            return "bauh_api>=0.1,<0.2,{}".format('\nbauh_commons>=0.1,<0.2' if name != 'bauh_commons' else '')

        self.github_client.get_requirements.side_effect = get_requirements

        # test
        updates = self.manager.list_updates()
        self.assertIsNotNone(updates)
        self.assertEqual(3, len(updates))
        self.assertEqual(comps[ComponentType.LIBRARY]['bauh_api'], updates[0])
        self.assertEqual(comps[ComponentType.LIBRARY]['bauh_commons'], updates[1])
        self.assertEqual(comps[ComponentType.APPLICATION]['bauh'], updates[2])

        for up in updates:
            self.assertFalse(up.conflicts, up.name)

    def test_list_updates__it_should_return_a_gem_update_with_the_installed_api_as_a_conflict(self):
        # setup
        comps = {
            ComponentType.APPLICATION: {'bauh': Component('bauh', '0.1.0', '0.1.0', ComponentType.APPLICATION, [])},
            ComponentType.LIBRARY: {
                'bauh_api': Component('bauh_api', '0.1.0', '0.1.0', ComponentType.LIBRARY, []),
                'bauh_commons': Component('bauh_commons', '0.1.0', '0.1.0', ComponentType.LIBRARY, [])
            },
            ComponentType.GEM: {'bauh_snap': Component('bauh_snap', '0.1.0', '0.1.1', ComponentType.GEM, [])}
        }

        self.manager.list_components = MagicMock()
        self.manager.list_components.return_value = comps

        def get_requirements(name, version):
            if name == 'bauh_snap':
                return "bauh_api>=0.2\nbauh_commons>=0.1,<0.2"

            return "bauh_api>=0.1,<0.2,{}".format('\nbauh_commons>=0.1,<0.2' if name != 'bauh_commons' else '')

        self.github_client.get_requirements.side_effect = get_requirements

        # test
        updates = self.manager.list_updates()
        self.assertIsNotNone(updates)
        self.assertEqual(1, len(updates))
        self.assertEqual(comps[ComponentType.GEM]['bauh_snap'], updates[0])

        self.assertTrue(updates[0].conflicts)
        self.assertEqual(1, len(updates[0].conflicts))
        self.assertIn(comps[ComponentType.LIBRARY]['bauh_api'], updates[0].conflicts)

    def test_list_updates__it_should_return_a_gem_update_with_the_installed_commons_as_a_conflict(self):
        # setup
        comps = {
            ComponentType.APPLICATION: {'bauh': Component('bauh', '0.1.0', '0.1.0', ComponentType.APPLICATION, [])},
            ComponentType.LIBRARY: {
                'bauh_api': Component('bauh_api', '0.1.0', '0.1.0', ComponentType.LIBRARY, []),
                'bauh_commons': Component('bauh_commons', '0.1.0', '0.1.0', ComponentType.LIBRARY, [])
            },
            ComponentType.GEM: {'bauh_snap': Component('bauh_snap', '0.1.0', '0.1.1', ComponentType.GEM, [])}
        }

        self.manager.list_components = MagicMock()
        self.manager.list_components.return_value = comps

        def get_requirements(name, version):
            if name == 'bauh_snap':
                return "bauh_api>=0.1\nbauh_commons>=0.2"

            return "bauh_api>=0.1,<0.2,{}".format('\nbauh_commons>=0.1,<0.2' if name != 'bauh_commons' else '')

        self.github_client.get_requirements.side_effect = get_requirements

        # test
        updates = self.manager.list_updates()
        self.assertIsNotNone(updates)
        self.assertEqual(1, len(updates))
        self.assertEqual(comps[ComponentType.GEM]['bauh_snap'], updates[0])

        self.assertTrue(updates[0].conflicts)
        self.assertEqual(1, len(updates[0].conflicts))
        self.assertIn(comps[ComponentType.LIBRARY]['bauh_commons'], updates[0].conflicts)

    def test_list_updates__it_should_return_a_gem_update_with_an_api_update_as_a_conflict(self):
        # setup
        comps = {
            ComponentType.APPLICATION: {'bauh': Component('bauh', '0.1.0', '0.1.0', ComponentType.APPLICATION, [])},
            ComponentType.LIBRARY: {
                'bauh_api': Component('bauh_api', '0.1.0', '0.2.0', ComponentType.LIBRARY, []),
                'bauh_commons': Component('bauh_commons', '0.1.0', '0.1.0', ComponentType.LIBRARY, [])
            },
            ComponentType.GEM: {'bauh_snap': Component('bauh_snap', '0.1.0', '0.1.1', ComponentType.GEM, [])}
        }

        self.manager.list_components = MagicMock()
        self.manager.list_components.return_value = comps

        def get_requirements(name, version):
            if name == 'bauh_snap':
                return "bauh_api>=0.1,<0.2\nbauh_commons>=0.1"

            return "bauh_api>=0.2,<0.3,{}".format('\nbauh_commons>=0.1,<0.2' if name != 'bauh_commons' else '')

        self.github_client.get_requirements.side_effect = get_requirements

        # test
        updates = self.manager.list_updates()
        self.assertIsNotNone(updates)
        self.assertEqual(2, len(updates))
        self.assertEqual(comps[ComponentType.LIBRARY]['bauh_api'], updates[0])
        self.assertEqual(comps[ComponentType.GEM]['bauh_snap'], updates[1])

        self.assertTrue(updates[0].conflicts)
        self.assertEqual(1, len(updates[0].conflicts))
        self.assertIn(comps[ComponentType.GEM]['bauh_snap'], updates[0].conflicts)

        self.assertTrue(updates[1].conflicts)
        self.assertEqual(1, len(updates[1].conflicts))
        self.assertIn(comps[ComponentType.LIBRARY]['bauh_api'], updates[1].conflicts)

    def test_list_updates__it_should_return_a_gem_update_with_a_commons_update_as_a_conflict(self):
        # setup
        comps = {
            ComponentType.APPLICATION: {'bauh': Component('bauh', '0.1.0', '0.1.0', ComponentType.APPLICATION, [])},
            ComponentType.LIBRARY: {
                'bauh_api': Component('bauh_api', '0.1.0', '0.1.0', ComponentType.LIBRARY, []),
                'bauh_commons': Component('bauh_commons', '0.1.0', '0.2.0', ComponentType.LIBRARY, [])
            },
            ComponentType.GEM: {'bauh_snap': Component('bauh_snap', '0.1.0', '0.1.1', ComponentType.GEM, [])}
        }

        self.manager.list_components = MagicMock()
        self.manager.list_components.return_value = comps

        def get_requirements(name, version):
            if name == 'bauh_snap':
                return "bauh_api>=0.1,<0.2\nbauh_commons>=0.1, <0.2"

            return "bauh_api>=0.1,<0.2,{}".format('\nbauh_commons>=0.2,<0.3' if name != 'bauh_commons' else '')

        self.github_client.get_requirements.side_effect = get_requirements

        # test
        updates = self.manager.list_updates()
        self.assertIsNotNone(updates)
        self.assertEqual(2, len(updates))
        self.assertEqual(comps[ComponentType.LIBRARY]['bauh_commons'], updates[0])
        self.assertEqual(comps[ComponentType.GEM]['bauh_snap'], updates[1])

        self.assertTrue(updates[0].conflicts)
        self.assertEqual(1, len(updates[0].conflicts))
        self.assertIn(comps[ComponentType.GEM]['bauh_snap'], updates[0].conflicts)

        self.assertTrue(updates[1].conflicts)
        self.assertEqual(1, len(updates[1].conflicts))
        self.assertIn(comps[ComponentType.LIBRARY]['bauh_commons'], updates[1].conflicts)

    def test_list_updates__it_should_return_a_gem_update_if_its_compatible_with_the_installed_api_and_commons(self):
        # setup
        comps = {
            ComponentType.APPLICATION: {'bauh': Component('bauh', '0.1.0', '0.1.0', ComponentType.APPLICATION, [])},
            ComponentType.LIBRARY: {
                'bauh_api': Component('bauh_api', '0.1.5', '0.1.5', ComponentType.LIBRARY, []),
                'bauh_commons': Component('bauh_commons', '0.1.2', '0.1.2', ComponentType.LIBRARY, [])
            },
            ComponentType.GEM: {'bauh_snap': Component('bauh_snap', '0.1.0', '0.1.1', ComponentType.GEM, [])}
        }

        self.manager.list_components = MagicMock()
        self.manager.list_components.return_value = comps

        def get_requirements(name, version):
            return "bauh_api>=0.1,<0.2,{}".format('\nbauh_commons>=0.1,<0.2' if name != 'bauh_commons' else '')

        self.github_client.get_requirements.side_effect = get_requirements

        # test
        updates = self.manager.list_updates()
        self.assertIsNotNone(updates)
        self.assertEqual(1, len(updates))
        self.assertEqual(comps[ComponentType.GEM]['bauh_snap'], updates[0])
        self.assertFalse(updates[0].conflicts)

    def test_list_updates__it_should_return_a_gem_update_if_its_compatible_with_an_api_and_commons_update(self):
        # setup
        comps = {
            ComponentType.APPLICATION: {'bauh': Component('bauh', '0.1.0', '0.1.0', ComponentType.APPLICATION, [])},
            ComponentType.LIBRARY: {
                'bauh_api': Component('bauh_api', '0.1.5', '0.1.6', ComponentType.LIBRARY, []),
                'bauh_commons': Component('bauh_commons', '0.1.2', '0.1.7', ComponentType.LIBRARY, [])
            },
            ComponentType.GEM: {'bauh_snap': Component('bauh_snap', '0.1.0', '0.1.1', ComponentType.GEM, [])}
        }

        self.manager.list_components = MagicMock()
        self.manager.list_components.return_value = comps

        def get_requirements(name, version):
            return "bauh_api>=0.1,<0.2,{}".format('\nbauh_commons>=0.1,<0.2' if name != 'bauh_commons' else '')

        self.github_client.get_requirements.side_effect = get_requirements

        # test
        updates = self.manager.list_updates()
        self.assertIsNotNone(updates)
        self.assertEqual(3, len(updates))
        self.assertEqual(comps[ComponentType.LIBRARY]['bauh_api'], updates[0])
        self.assertEqual(comps[ComponentType.LIBRARY]['bauh_commons'], updates[1])
        self.assertEqual(comps[ComponentType.GEM]['bauh_snap'], updates[2])

        for up in updates:
            self.assertFalse(up.conflicts, up.name)

    def test_list_updates__it_should_return_one_of_the_gem_with_its_conflicts_set(self):
        # setup
        comps = {
            ComponentType.APPLICATION: {'bauh': Component('bauh', '0.1.0', '0.1.0', ComponentType.APPLICATION, [])},
            ComponentType.LIBRARY: {
                'bauh_api': Component('bauh_api', '0.1.1', '0.2.0', ComponentType.LIBRARY, []),
                'bauh_commons': Component('bauh_commons', '0.1.1', '0.1.6', ComponentType.LIBRARY, [])
            },
            ComponentType.GEM: {
                'bauh_snap': Component('bauh_snap', '0.1.0', '0.2.1', ComponentType.GEM, []),
                'bauh_flatpak': Component('bauh_flatpak', '0.1.0', '0.1.1', ComponentType.GEM, []),
            }
        }

        self.manager.list_components = MagicMock()
        self.manager.list_components.return_value = comps

        def get_requirements(name, version):
            if name == 'bauh_flatpak':
                return "bauh_api>=0.1,<0.2,\nbauh_commons>=0.1,<0.2"

            return "bauh_api>=0.2,<0.3,{}".format('\nbauh_commons>=0.1,<0.2' if name != 'bauh_commons' else '')

        self.github_client.get_requirements.side_effect = get_requirements

        # test
        updates = self.manager.list_updates()
        self.assertIsNotNone(updates)
        self.assertEqual(4, len(updates))
        self.assertEqual(comps[ComponentType.LIBRARY]['bauh_api'], updates[0])
        self.assertEqual(comps[ComponentType.LIBRARY]['bauh_commons'], updates[1])

        self.assertIn(comps[ComponentType.GEM]['bauh_snap'], updates)
        self.assertFalse(comps[ComponentType.GEM]['bauh_snap'].conflicts)

        self.assertIn(comps[ComponentType.GEM]['bauh_flatpak'], updates)
        self.assertEqual(1, len(comps[ComponentType.GEM]['bauh_flatpak'].conflicts))
        self.assertIn(comps[ComponentType.LIBRARY]['bauh_api'], comps[ComponentType.GEM]['bauh_flatpak'].conflicts)

        self.assertEqual(1, len(comps[ComponentType.LIBRARY]['bauh_api'].conflicts))
        self.assertIn(comps[ComponentType.GEM]['bauh_flatpak'], comps[ComponentType.LIBRARY]['bauh_api'].conflicts)

    def test_list_updates__it_should_return_updated_from_all_component_types_with_no_conflicts_set(self):
        # setup
        comps = {
            ComponentType.APPLICATION: {'bauh': Component('bauh', '0.1.0', '0.1.2', ComponentType.APPLICATION, [])},
            ComponentType.LIBRARY: {
                'bauh_api': Component('bauh_api', '0.1.1', '0.1.4', ComponentType.LIBRARY, []),
                'bauh_commons': Component('bauh_commons', '0.1.1', '0.1.6', ComponentType.LIBRARY, [])
            },
            ComponentType.GEM: {
                'bauh_snap': Component('bauh_snap', '0.1.0', '0.2.1', ComponentType.GEM, []),
                'bauh_flatpak': Component('bauh_flatpak', '0.1.0', '0.1.1', ComponentType.GEM, []),
            }
        }

        self.manager.list_components = MagicMock()
        self.manager.list_components.return_value = comps

        def get_requirements(name, version):
            return "bauh_api>=0.1,<0.2,{}".format('\nbauh_commons>=0.1,<0.2' if name != 'bauh_commons' else '')

        self.github_client.get_requirements.side_effect = get_requirements

        # test
        updates = self.manager.list_updates()
        self.assertIsNotNone(updates)
        self.assertEqual(5, len(updates))
        self.assertEqual(comps[ComponentType.LIBRARY]['bauh_api'], updates[0])
        self.assertEqual(comps[ComponentType.LIBRARY]['bauh_commons'], updates[1])
        self.assertEqual(comps[ComponentType.APPLICATION]['bauh'], updates[2])
        self.assertIn(comps[ComponentType.GEM]['bauh_snap'], updates)
        self.assertIn(comps[ComponentType.GEM]['bauh_flatpak'], updates)

        for up in updates:
            self.assertFalse(up.conflicts, up.name)
