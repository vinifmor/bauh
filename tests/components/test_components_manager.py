from unittest import TestCase
from unittest.mock import MagicMock

from bauh_api.abstract.component import Component, ComponentType

from bauh.components.manager import PythonComponentsManager


class PythonComponentsManagerTest(TestCase):

    def setUp(self):
        self.github_client = MagicMock()
        self.manager = PythonComponentsManager(self.github_client, MagicMock())

    def test_list_updates__it_should_return_only_an_api_update_when_its_available(self):

        # setup
        comps = {
            ComponentType.APPLICATION:  {'bauh': Component(name='bauh', version='0.1.0', new_version='0.1.0', type=ComponentType.APPLICATION)},
            ComponentType.LIBRARY: {
                'bauh_api': Component(name='bauh_api', version='0.1.0', new_version='0.1.1', type=ComponentType.LIBRARY),
                'bauh_commons': Component(name='bauh_commons', version='0.1.0', new_version='0.1.0', type=ComponentType.LIBRARY)
            },
            ComponentType.GEM: {'bauh_snap': Component(name='bauh_snap', version='0.1.0', new_version='0.1.0', type=ComponentType.GEM)}
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

    def test_list_updates__it_should_return_only_a_commons_update_when_its_available(self):

        # setup
        comps = {
            ComponentType.APPLICATION:  {'bauh': Component(name='bauh', version='0.1.0', new_version='0.1.0', type=ComponentType.APPLICATION)},
            ComponentType.LIBRARY: {
                'bauh_api': Component(name='bauh_api', version='0.1.0', new_version='0.1.0', type=ComponentType.LIBRARY),
                'bauh_commons': Component(name='bauh_commons', version='0.1.0', new_version='0.1.1', type=ComponentType.LIBRARY)
            },
            ComponentType.GEM: {'bauh_snap': Component(name='bauh_snap', version='0.1.0', new_version='0.1.0', type=ComponentType.GEM)}
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

    def test_list_updates__it_should_not_return_an_api_update_if_its_not_compatible_with_the_installed_components(self):

        # setup
        comps = {
            ComponentType.APPLICATION:  {'bauh': Component(name='bauh', version='0.1.0', new_version='0.1.0', type=ComponentType.APPLICATION)},
            ComponentType.LIBRARY: {
                'bauh_api': Component(name='bauh_api', version='0.1.0', new_version='0.2.0', type=ComponentType.LIBRARY),
                'bauh_commons': Component(name='bauh_commons', version='0.1.0', new_version='0.1.0', type=ComponentType.LIBRARY)
            },
            ComponentType.GEM: {'bauh_snap': Component(name='bauh_snap', version='0.1.0', new_version='0.1.0', type=ComponentType.GEM)}
        }

        self.manager.list_components = MagicMock()
        self.manager.list_components.return_value = comps

        def get_requirements(name, version):
            return "bauh_api>=0.1,<0.2,{}".format('\nbauh_commons>=0.1,<0.2' if name != 'bauh_commons' else '')

        self.github_client.get_requirements.side_effect = get_requirements

        # test
        updates = self.manager.list_updates()
        self.assertFalse(updates)

    def test_list_updates__it_should_not_return_a_gui_update_if_its_not_compatible_with_the_installed_api(self):

        # setup
        comps = {
            ComponentType.APPLICATION:  {'bauh': Component(name='bauh', version='0.1.0', new_version='0.2.0', type=ComponentType.APPLICATION)},
            ComponentType.LIBRARY: {
                'bauh_api': Component(name='bauh_api', version='0.1.0', new_version='0.1.0', type=ComponentType.LIBRARY),
                'bauh_commons': Component(name='bauh_commons', version='0.1.0', new_version='0.1.0', type=ComponentType.LIBRARY)
            },
            ComponentType.GEM: {'bauh_snap': Component(name='bauh_snap', version='0.1.0', new_version='0.1.0', type=ComponentType.GEM)}
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
        self.assertFalse(updates)

    def test_list_updates__it_should_not_return_a_gui_update_if_its_not_compatible_with_the_installed_commons(self):

        # setup
        comps = {
            ComponentType.APPLICATION:  {'bauh': Component(name='bauh', version='0.1.0', new_version='0.2.0', type=ComponentType.APPLICATION)},
            ComponentType.LIBRARY: {
                'bauh_api': Component(name='bauh_api', version='0.1.0', new_version='0.1.0', type=ComponentType.LIBRARY),
                'bauh_commons': Component(name='bauh_commons', version='0.1.0', new_version='0.1.0', type=ComponentType.LIBRARY)
            },
            ComponentType.GEM: {'bauh_snap': Component(name='bauh_snap', version='0.1.0', new_version='0.1.0', type=ComponentType.GEM)}
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
        self.assertFalse(updates)

    def test_list_updates__it_should_return_a_gui_update_if_its_compatible_with_the_api_and_commons_updates(self):

        # setup
        comps = {
            ComponentType.APPLICATION:  {'bauh': Component(name='bauh', version='0.1.0', new_version='0.2.0', type=ComponentType.APPLICATION)},
            ComponentType.LIBRARY: {
                'bauh_api': Component(name='bauh_api', version='0.1.2', new_version='0.1.4', type=ComponentType.LIBRARY),
                'bauh_commons': Component(name='bauh_commons', version='0.1.2', new_version='0.1.6', type=ComponentType.LIBRARY)
            },
            ComponentType.GEM: {'bauh_snap': Component(name='bauh_snap', version='0.1.0', new_version='0.1.0', type=ComponentType.GEM)}
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

    def test_list_updates__it_should_not_return_a_gem_update_if_its_not_compatible_with_the_installed_api(self):
        # setup
        comps = {
            ComponentType.APPLICATION: {
                'bauh': Component(name='bauh', version='0.1.0', new_version='0.1.0', type=ComponentType.APPLICATION)},
            ComponentType.LIBRARY: {
                'bauh_api': Component(name='bauh_api', version='0.1.0', new_version='0.1.0', type=ComponentType.LIBRARY),
                'bauh_commons': Component(name='bauh_commons', version='0.1.0', new_version='0.1.0', type=ComponentType.LIBRARY)
            },
            ComponentType.GEM: {
                'bauh_snap': Component(name='bauh_snap', version='0.1.0', new_version='0.1.1', type=ComponentType.GEM)}
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
        self.assertFalse(updates)

    def test_list_updates__it_should_not_return_a_gem_update_if_its_not_compatible_with_the_installed_commons(self):
        # setup
        comps = {
            ComponentType.APPLICATION: {
                'bauh': Component(name='bauh', version='0.1.0', new_version='0.1.0', type=ComponentType.APPLICATION)},
            ComponentType.LIBRARY: {
                'bauh_api': Component(name='bauh_api', version='0.1.0', new_version='0.1.0', type=ComponentType.LIBRARY),
                'bauh_commons': Component(name='bauh_commons', version='0.1.0', new_version='0.1.0', type=ComponentType.LIBRARY)
            },
            ComponentType.GEM: {
                'bauh_snap': Component(name='bauh_snap', version='0.1.0', new_version='0.1.1', type=ComponentType.GEM)}
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
        self.assertFalse(updates)

    def test_list_updates__it_should_not_return_a_gem_update_if_its_not_compatible_with_an_api_update(self):
        # setup
        comps = {
            ComponentType.APPLICATION: {
                'bauh': Component(name='bauh', version='0.1.0', new_version='0.1.0', type=ComponentType.APPLICATION)},
            ComponentType.LIBRARY: {
                'bauh_api': Component(name='bauh_api', version='0.1.0', new_version='0.2.0', type=ComponentType.LIBRARY),
                'bauh_commons': Component(name='bauh_commons', version='0.1.0', new_version='0.1.0', type=ComponentType.LIBRARY)
            },
            ComponentType.GEM: {
                'bauh_snap': Component(name='bauh_snap', version='0.1.0', new_version='0.1.1', type=ComponentType.GEM)}
        }

        self.manager.list_components = MagicMock()
        self.manager.list_components.return_value = comps

        def get_requirements(name, version):
            return "bauh_api>=0.1,<0.2,{}".format('\nbauh_commons>=0.1,<0.2' if name != 'bauh_commons' else '')

        self.github_client.get_requirements.side_effect = get_requirements

        # test
        updates = self.manager.list_updates()
        self.assertFalse(updates)

    def test_list_updates__it_should_not_return_a_gem_update_if_its_not_compatible_with_a_commons_update(self):
        # setup
        comps = {
            ComponentType.APPLICATION: {
                'bauh': Component(name='bauh', version='0.1.0', new_version='0.1.0', type=ComponentType.APPLICATION)},
            ComponentType.LIBRARY: {
                'bauh_api': Component(name='bauh_api', version='0.1.0', new_version='0.1.0', type=ComponentType.LIBRARY),
                'bauh_commons': Component(name='bauh_commons', version='0.1.0', new_version='0.2.0', type=ComponentType.LIBRARY)
            },
            ComponentType.GEM: {
                'bauh_snap': Component(name='bauh_snap', version='0.1.0', new_version='0.1.1', type=ComponentType.GEM)}
        }

        self.manager.list_components = MagicMock()
        self.manager.list_components.return_value = comps

        def get_requirements(name, version):
            return "bauh_api>=0.1,<0.2,{}".format('\nbauh_commons>=0.1,<0.2' if name != 'bauh_commons' else '')

        self.github_client.get_requirements.side_effect = get_requirements

        # test
        updates = self.manager.list_updates()
        self.assertFalse(updates)

    def test_list_updates__it_should_return_a_gem_update_if_its_compatible_with_the_installed_api_and_commons(self):
        # setup
        comps = {
            ComponentType.APPLICATION: {
                'bauh': Component(name='bauh', version='0.1.0', new_version='0.1.0', type=ComponentType.APPLICATION)},
            ComponentType.LIBRARY: {
                'bauh_api': Component(name='bauh_api', version='0.1.5', new_version='0.1.5', type=ComponentType.LIBRARY),
                'bauh_commons': Component(name='bauh_commons', version='0.1.0', new_version='0.1.0', type=ComponentType.LIBRARY)
            },
            ComponentType.GEM: {
                'bauh_snap': Component(name='bauh_snap', version='0.1.0', new_version='0.1.1', type=ComponentType.GEM)}
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

    def test_list_updates__it_should_return_a_gem_update_if_its_compatible_with_an_api_and_commons_update(self):
        # setup
        comps = {
            ComponentType.APPLICATION: {
                'bauh': Component(name='bauh', version='0.1.0', new_version='0.1.0', type=ComponentType.APPLICATION)},
            ComponentType.LIBRARY: {
                'bauh_api': Component(name='bauh_api', version='0.1.1', new_version='0.1.5', type=ComponentType.LIBRARY),
                'bauh_commons': Component(name='bauh_commons', version='0.1.1', new_version='0.1.6', type=ComponentType.LIBRARY)
            },
            ComponentType.GEM: {
                'bauh_snap': Component(name='bauh_snap', version='0.1.0', new_version='0.1.1', type=ComponentType.GEM)}
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

    def test_list_updates__it_should_not_return_when_one_of_the_gems_are_not_compatible_with_the_api_update(self):
        # setup
        comps = {
            ComponentType.APPLICATION: {
                'bauh': Component(name='bauh', version='0.1.0', new_version='0.1.0', type=ComponentType.APPLICATION)},
            ComponentType.LIBRARY: {
                'bauh_api': Component(name='bauh_api', version='0.1.1', new_version='0.2.0',
                                      type=ComponentType.LIBRARY),
                'bauh_commons': Component(name='bauh_commons', version='0.1.1', new_version='0.1.6', type=ComponentType.LIBRARY)
            },
            ComponentType.GEM: {
                'bauh_snap': Component(name='bauh_snap', version='0.1.0', new_version='0.2.1', type=ComponentType.GEM),
                'bauh_flatpak': Component(name='bauh_flatpak', version='0.1.0', new_version='0.1.1', type=ComponentType.GEM)
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
        self.assertFalse(updates)

    def test_list_updates__it_should_not_return_when_one_of_the_gems_are_not_compatible_with_the_commons_update(self):
        # setup
        comps = {
            ComponentType.APPLICATION: {
                'bauh': Component(name='bauh', version='0.1.0', new_version='0.1.0', type=ComponentType.APPLICATION)},
            ComponentType.LIBRARY: {
                'bauh_api': Component(name='bauh_api', version='0.1.1', new_version='0.1.3',
                                      type=ComponentType.LIBRARY),
                'bauh_commons': Component(name='bauh_commons', version='0.1.1', new_version='0.1.5', type=ComponentType.LIBRARY)
            },
            ComponentType.GEM: {
                'bauh_snap': Component(name='bauh_snap', version='0.1.0', new_version='0.2.1', type=ComponentType.GEM),
                'bauh_flatpak': Component(name='bauh_flatpak', version='0.1.0', new_version='0.1.1', type=ComponentType.GEM)
            }
        }

        self.manager.list_components = MagicMock()
        self.manager.list_components.return_value = comps

        def get_requirements(name, version):
            if name == 'bauh_flatpak':
                return "bauh_api>=0.1,<0.2,\nbauh_commons>=0.1,<0.1.5"

            return "bauh_api>=0.1,<0.2,{}".format('\nbauh_commons>=0.1,<0.2' if name != 'bauh_commons' else '')

        self.github_client.get_requirements.side_effect = get_requirements

        # test
        updates = self.manager.list_updates()
        self.assertFalse(updates)

    def test_list_updates__it_should_return_updates_for_all_component_types(self):
        # setup
        comps = {
            ComponentType.APPLICATION: {
                'bauh': Component(name='bauh', version='0.1.0', new_version='0.1.3', type=ComponentType.APPLICATION)},
            ComponentType.LIBRARY: {
                'bauh_api': Component(name='bauh_api', version='0.1.1', new_version='0.1.9', type=ComponentType.LIBRARY),
                'bauh_commons': Component(name='bauh_commons', version='0.1.1', new_version='0.1.9', type=ComponentType.LIBRARY)
            },
            ComponentType.GEM: {
                'bauh_snap': Component(name='bauh_snap', version='0.1.0', new_version='0.1.1', type=ComponentType.GEM),
                'bauh_flatpak': Component(name='bauh_flatpak', version='0.1.1', new_version='0.1.6', type=ComponentType.GEM)
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
