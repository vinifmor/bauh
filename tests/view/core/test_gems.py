import importlib
import logging
import sys
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

import bauh.gems
from bauh.view.core import gems


class LoadManagersTest(TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.gem_dir = self.root / 'gems' / '_loader_test'
        self.gem_dir.mkdir(parents=True)
        (self.gem_dir / '__init__.py').touch()
        self.module_name = 'bauh.gems._loader_test.controller'
        self.addCleanup(self._clear_modules)

        for target in (
                patch.object(gems, 'ROOT_DIR', str(self.root)),
                patch.object(bauh.gems, '__path__', [str(self.root / 'gems')]),
                patch.object(gems, 'read_forbidden_gems', return_value=iter(()))):
            target.start()
            self.addCleanup(target.stop)

        self.manager_class = Mock()
        self.manager_class.return_value.is_default_enabled.return_value = True
        finder = patch.object(gems, 'find_manager', return_value=self.manager_class)
        self.find_manager = finder.start()
        self.addCleanup(finder.stop)

    def _clear_modules(self):
        sys.modules.pop(self.module_name, None)
        sys.modules.pop('bauh.gems._loader_test', None)
        if hasattr(bauh.gems, '_loader_test'):
            del bauh.gems._loader_test
        importlib.invalidate_caches()

    def _load(self, enabled=None):
        return gems.load_managers(locale=None, context=Mock(), config={'gems': enabled},
                                  default_locale=None, logger=logging.getLogger(__name__))

    def test_loads_controller_and_uses_default_enabled_state(self):
        (self.gem_dir / 'controller.py').write_text('loaded = True\n')

        managers = self._load()

        self.assertEqual([self.manager_class.return_value], managers)
        self.assertTrue(sys.modules[self.module_name].loaded)
        self.find_manager.assert_called_once_with(sys.modules[self.module_name])
        managers[0].set_enabled.assert_called_once_with(True)

    def test_reuses_imported_controller_without_executing_it_again(self):
        (self.gem_dir / 'controller.py').write_text(
            "executions = globals().get('executions', 0) + 1\n")

        self._load()
        self._load()

        self.assertEqual(1, sys.modules[self.module_name].executions)
        self.assertEqual(2, self.manager_class.call_count)

    def test_skips_package_without_controller(self):
        self.assertEqual([], self._load())
        self.find_manager.assert_not_called()

    def test_does_not_import_forbidden_controller(self):
        (self.gem_dir / 'controller.py').write_text('raise RuntimeError("must not import")\n')

        with patch.object(gems, 'read_forbidden_gems', return_value=iter(('_loader_test',))):
            self.assertEqual([], self._load())

        self.assertNotIn(self.module_name, sys.modules)
        self.find_manager.assert_not_called()

    def test_explicit_configuration_disables_unselected_manager(self):
        (self.gem_dir / 'controller.py').touch()

        managers = self._load(enabled=[])

        managers[0].set_enabled.assert_called_once_with(False)
