from unittest import TestCase
from unittest.mock import patch, Mock, MagicMock

from bauh import __app_name__
from bauh.api.abstract.controller import UpgradeRequirement
from bauh.gems.arch.dependencies import DependenciesAnalyser
from bauh.gems.arch.model import ArchPackage
from bauh.gems.arch.updates import UpdatesSummarizer
from bauh.view.util.translation import I18n


class UpdatesSummarizerGetUpgradeRequirementsTest(TestCase):

    def setUp(self) -> None:
        self.aur_client = MagicMock()
        self.aur_client.read_index.return_value = set()
        self.deps_analyser = MagicMock()
        self._i18n = {"arch.info.conflicts with": "", "arch.update_summary.to_install.dep_conflict": "{} {}",
                      "arch.info.required by": "", "arch.info.depends on": ""}
        self.i18n = I18n(default_key='en_US', default_locale=self._i18n, current_key='en_US', current_locale=self._i18n)
        self.summarizer = UpdatesSummarizer(aur_client=self.aur_client,
                                            aur_supported=True,
                                            i18n=self.i18n,
                                            logger=Mock(),
                                            deps_analyser=self.deps_analyser,
                                            watcher=Mock())
        self.config_ = {"automatch_providers": True,
                        "prefer_repository_provider": True,
                        "check_dependency_breakage": True}

    @patch(f"{__app_name__}.gems.arch.updates.pacman")
    def test__should_not_return_installed_to_remove_when_conflict_with_installed_version_fails(self, pacman: Mock):
        """
        If the newest version o package A conflicts with an installed package named B, but the conflict expression
        doesn't match (e.g: A conflict expressions (B <= 0.7), B (0.8)) then B should not be marked as a package
        to be removed.
        """
        pkg_a = ArchPackage(name="A", version="1.0.0-1", latest_version="1.1.0-1", repository="community")

        pacman.map_provided.side_effect = [{"A": {"A"},  # remote provided
                                            "A=1.1.0": {"A"},
                                            "B": {"B"},
                                            "B=0.8": {"B"}
                                            },
                                           {"A": {"A"},  # provided
                                            "A=1.0.0": {"A"},
                                            "B": {"B"},
                                            "B=0.8": {"B"}
                                            }
                                           ]
        pacman.map_repositories.return_value = {"A": pkg_a.repository, "B": "community"}
        pacman.map_updates_data.return_value = {"A": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_a.latest_version,
                                                      'c': {"B<=0.7"},
                                                      'p': {"A": {"A"},
                                                            "A=1.1.0": {"A"}},
                                                      'd': set(),
                                                      'r': "community",
                                                      'des': pkg_a.name}}
        pacman.map_installed.return_value = {"A": pkg_a.version, "B": "0.8-1"}
        pacman.get_installed_size.return_value = {"A": 1, "B": 1}
        pacman.map_required_by.return_value = {"A": set()}

        self.deps_analyser.map_missing_deps.return_value = list()

        res = self.summarizer.summarize(pkgs=[pkg_a], root_password=None, arch_config=self.config_)
        for method in ('map_provided', 'map_repositories', 'map_updates_data', 'map_installed',
                       'get_installed_size', 'map_required_by'):
            getattr(pacman, method).assert_called()

        for method in ('map_missing_deps',):
            getattr(self.deps_analyser, method).assert_called()

        self.assertFalse(res.to_remove)
        self.assertFalse(res.to_install)
        self.assertEqual([UpgradeRequirement(pkg=pkg_a, required_size=1, extra_size=0)], res.to_upgrade)

    @patch(f"{__app_name__}.gems.arch.updates.pacman")
    def test__should_return_installed_to_remove_when_conflict_with_installed_version_matches(self, pacman: Mock):
        """
        If the newest version o package A conflicts with an installed package named B and the conflict expression
        matches (e.g: A conflict expressions (B <= 0.7), B (0.7)) then B should be marked as a package to be removed.
        """
        pkg_a = ArchPackage(name="A", version="1.0.0-1", latest_version="1.1.0-1", repository="community")

        pacman.map_provided.side_effect = [{"A": {"A"},  # remote provided
                                            "A==1.0.1": {"A"},
                                            "B": {"B"},
                                            "B=0.7": {"B"}
                                            },
                                           {"A": {"A"},  # provided
                                            "A=1.0.0": {"A"},
                                            "B": {"B"},
                                            "B=0.7": {"B"}
                                            },
                                           {"B": {"B"},  # provided to remove
                                            "B=0.7": {"B"}
                                            }
                                           ]
        pacman.map_repositories.return_value = {"A": pkg_a.repository, "B": "community"}
        pacman.map_updates_data.return_value = {"A": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_a.latest_version,
                                                      'c': {"B<=0.7"},
                                                      'p': {"A": {"A"},
                                                            "A=1.1.0": {"A"}},
                                                      'd': set(),
                                                      'r': "community",
                                                      'des': pkg_a.name}}
        pacman.map_installed.return_value = {"A": pkg_a.version, "B": "0.7-1"}
        pacman.get_installed_size.return_value = {"A": 1, "B": 1}
        pacman.map_required_by.return_value = {"A": set()}

        self.deps_analyser.map_missing_deps.return_value = list()
        self.deps_analyser.map_all_required_by.return_value = set()

        res = self.summarizer.summarize(pkgs=[pkg_a], root_password=None, arch_config=self.config_)

        for method in ('map_provided', 'map_repositories', 'map_updates_data', 'map_installed',
                       'get_installed_size', 'map_required_by'):
            getattr(pacman, method).assert_called()

        for method in ('map_missing_deps', 'map_all_required_by'):
            getattr(self.deps_analyser, method).assert_called()

        self.assertFalse(res.to_install)
        self.assertEqual([UpgradeRequirement(pkg=pkg_a, required_size=1, extra_size=0)], res.to_upgrade)

        pkg_b = ArchPackage(name="B", installed=True, i18n=self.i18n)
        self.assertEqual([UpgradeRequirement(pkg=pkg_b, reason=" 'A'", extra_size=1)], res.to_remove)

    @patch(f"{__app_name__}.gems.arch.updates.pacman")
    def test__should_return_installed_to_remove_when_conflict_with_installed_matches(self, pacman: Mock):
        """
        If the newest version o package A conflicts with an installed package named B,
        then B should be marked as a package to be removed.
        """
        pkg_a = ArchPackage(name="A", version="1.0.0-1", latest_version="1.1.0-1", repository="community")

        pacman.map_provided.side_effect = [{"A": {"A"},  # remote provided
                                            "A==1.0.1": {"A"},
                                            "B": {"B"},
                                            "B=0.7": {"B"}
                                            },
                                           {"A": {"A"},  # provided
                                            "A=1.0.0": {"A"},
                                            "B": {"B"},
                                            "B=0.7": {"B"}
                                            },
                                           {"B": {"B"},  # provided to remove
                                            "B=0.7": {"B"}
                                            }
                                           ]
        pacman.map_repositories.return_value = {"A": pkg_a.repository, "B": "community"}
        pacman.map_updates_data.return_value = {"A": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_a.latest_version,
                                                      'c': {"B"},
                                                      'p': {"A": {"A"},
                                                            "A=1.1.0": {"A"}},
                                                      'd': set(),
                                                      'r': "community",
                                                      'des': pkg_a.name}}
        pacman.map_installed.return_value = {"A": pkg_a.version, "B": "0.7-1"}
        pacman.get_installed_size.return_value = {"A": 1, "B": 1}
        pacman.map_required_by.return_value = {"A": set()}

        self.deps_analyser.map_missing_deps.return_value = list()
        self.deps_analyser.map_all_required_by.return_value = set()

        res = self.summarizer.summarize(pkgs=[pkg_a], root_password=None, arch_config=self.config_)

        for method in ('map_provided', 'map_repositories', 'map_updates_data', 'map_installed',
                       'get_installed_size', 'map_required_by'):
            getattr(pacman, method).assert_called()

        for method in ('map_missing_deps', 'map_all_required_by'):
            getattr(self.deps_analyser, method).assert_called()

        self.assertFalse(res.to_install)
        self.assertEqual([UpgradeRequirement(pkg=pkg_a, required_size=1, extra_size=0)], res.to_upgrade)

        pkg_b = ArchPackage(name="B", installed=True, i18n=self.i18n)
        self.assertEqual([UpgradeRequirement(pkg=pkg_b, reason=" 'A'", extra_size=1)], res.to_remove)

    @patch(f"{__app_name__}.gems.arch.updates.pacman")
    def test__should_not_return_installed_to_remove_when_conflict_with_is_self_conflict(self, pacman: Mock):
        """
        If the newest version o package A conflicts with itself, then A should not be marked as a package to be removed.
        """
        pkg_a = ArchPackage(name="A", version="1.0.0-1", latest_version="1.1.0-1", repository="community")

        pacman.map_provided.side_effect = [{"A": {"A"},  # remote provided
                                            "A=1.1.0": {"A"},
                                            "C": {"A"}
                                            },
                                           {"A": {"A"},  # provided
                                            "A=1.0.0": {"A"},
                                            "C": {"A"}
                                            }
                                           ]
        pacman.map_repositories.return_value = {"A": pkg_a.repository}
        pacman.map_updates_data.return_value = {"A": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_a.latest_version,
                                                      'c': {"A<=1.0.0"},
                                                      'p': {"A": {"A"},
                                                            "A=1.1.0": {"A"},
                                                            "C": {"A"}},
                                                      'd': set(),
                                                      'r': "community",
                                                      'des': pkg_a.name}}
        pacman.map_installed.return_value = {"A": pkg_a.version}
        pacman.get_installed_size.return_value = {"A": 1}
        pacman.map_required_by.return_value = {"A": set()}

        self.deps_analyser.map_missing_deps.return_value = list()

        res = self.summarizer.summarize(pkgs=[pkg_a], root_password=None, arch_config=self.config_)
        for method in ('map_provided', 'map_repositories', 'map_updates_data', 'map_installed',
                       'get_installed_size', 'map_required_by'):
            getattr(pacman, method).assert_called()

        self.assertFalse(res.to_remove)
        self.assertFalse(res.to_install)
        self.assertEqual([UpgradeRequirement(pkg=pkg_a, required_size=1, extra_size=0)], res.to_upgrade)

    @patch(f"{__app_name__}.gems.arch.updates.pacman")
    def test__should_not_return_installed_to_remove_when_conflict_with_provided_version_fails(self, pacman: Mock):
        """
        If the newest version o package A conflicts with a provided package C (by installed package B),
        but the conflict expression doesn't match (e.g: A conflict expressions (C <= 0.7), C (0.8))
        then B should not be marked as a package to be removed.
        """
        pkg_a = ArchPackage(name="A", version="1.0.0-1", latest_version="1.1.0-1", repository="community")

        pacman.map_provided.side_effect = [{"A": {"A"},  # remote provided
                                            "A=1.1.0": {"A"},
                                            "B": {"B", "C"},
                                            "B=0.8": {"B", "C"},
                                            "C": {"B"}
                                            },
                                           {"A": {"A"},  # provided
                                            "A=1.0.0": {"A"},
                                            "B": {"B", "C"},
                                            "B=0.8": {"B", "C"},
                                            "C": {"B"}
                                            }
                                           ]
        pacman.map_repositories.return_value = {"A": pkg_a.repository, "B": "community"}
        pacman.map_updates_data.return_value = {"A": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_a.latest_version,
                                                      'c': {"C<=0.7"},
                                                      'p': {"A": {"A"},
                                                            "A=1.1.0": {"A"}},
                                                      'd': set(),
                                                      'r': "community",
                                                      'des': pkg_a.name}}
        pacman.map_installed.return_value = {"A": pkg_a.version, "B": "0.8-1"}
        pacman.get_installed_size.return_value = {"A": 1, "B": 1}
        pacman.map_required_by.return_value = {"A": set()}

        self.deps_analyser.map_missing_deps.return_value = list()

        res = self.summarizer.summarize(pkgs=[pkg_a], root_password=None, arch_config=self.config_)
        for method in ('map_provided', 'map_repositories', 'map_updates_data', 'map_installed',
                       'get_installed_size', 'map_required_by'):
            getattr(pacman, method).assert_called()

        self.assertFalse(res.to_remove)
        self.assertFalse(res.to_install)
        self.assertEqual([UpgradeRequirement(pkg=pkg_a, required_size=1, extra_size=0)], res.to_upgrade)

    @patch(f"{__app_name__}.gems.arch.updates.pacman")
    def test__not_return_to_remove_when_conflict_with_provided_virtual_package_with_version_fails(self, pacman: Mock):
        """
        Scenario:
        - Package V (2.5.0)[update] -> conflicts: X<21.1.1, X-ABI-VIDEODRV_VERSION<25, X-ABI-VIDEODRV_VERSION>=26
        - Package X (21.1.5)[installed] -> provides: X-ABI-VIDEODRV_VERSION=25.2, X

        * X provides X-ABI-VIDEODRV_VERSION with a specific version (25.2)
        """
        pkg_a = ArchPackage(name="V", version="2.5.0-1", latest_version="2.6.0-1", repository="community")
        pacman.map_provided.side_effect = [{"V": {"V"},  # remote provided
                                            "V=2.5.0": {"V"},
                                            "X": {"X"},
                                            "X=21.1.5": {"X"},
                                            "X-ABI-VIDEODRV_VERSION=25.2": {"X"},
                                            "X-ABI-VIDEODRV_VERSION": {"X"}
                                            },
                                           {"V": {"V"},  # provided
                                            "V=2.5.0": {"V"},
                                            "X": {"X"},
                                            "X=21.1.5": {"X"},
                                            "X-ABI-VIDEODRV_VERSION=25.2": {"X"},
                                            "X-ABI-VIDEODRV_VERSION": {"X"}
                                            },
                                           ]
        pacman.map_repositories.return_value = {"V": pkg_a.repository, "X": "community"}
        pacman.map_updates_data.return_value = {"V": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_a.latest_version,
                                                      'c': {"X<21.1.1",
                                                            "X-ABI-VIDEODRV_VERSION<25",
                                                            "X-ABI-VIDEODRV_VERSION>=26"},
                                                      'p': {"V": {"V"},
                                                            "V=2.5.0": {"A"}},
                                                      'd': set(),
                                                      'r': "community",
                                                      'des': pkg_a.name}}
        pacman.map_installed.return_value = {"V": pkg_a.version, "X": "21.1.5-1"}
        pacman.get_installed_size.return_value = {"V": 1, "X": 1}
        pacman.map_required_by.return_value = {"V": set()}

        self.deps_analyser.map_missing_deps.return_value = list()

        res = self.summarizer.summarize(pkgs=[pkg_a], root_password=None, arch_config=self.config_)
        for method in ('map_provided', 'map_repositories', 'map_updates_data', 'map_installed',
                       'get_installed_size', 'map_required_by'):
            getattr(pacman, method).assert_called()

        self.assertFalse(res.to_remove)
        self.assertFalse(res.to_install)
        self.assertEqual([UpgradeRequirement(pkg=pkg_a, required_size=1, extra_size=0)], res.to_upgrade)

    @patch(f"{__app_name__}.gems.arch.updates.pacman")
    def test__return_installed_virtual_with_defined_version_to_remove_when_conflict_version_matches(self, pacman: Mock):
        """
        Scenario:
        - Package V (2.5.0)[update] -> conflicts: X<21.1.1, X-ABI-VIDEODRV_VERSION<25, X-ABI-VIDEODRV_VERSION>=26
        - Package X (21.1.5)[installed] -> provides: X-ABI-VIDEODRV_VERSION=26, X

        * X provides X-ABI-VIDEODRV_VERSION with a specific version (26)
        """
        pkg_a = ArchPackage(name="V", version="2.5.0-1", latest_version="2.6.0-1", repository="community")

        pacman.map_provided.side_effect = [{"V": {"V"},  # remote provided
                                            "V=2.5.0": {"V"},
                                            "X": {"X"},
                                            "X=21.1.5": {"X"},
                                            "X-ABI-VIDEODRV_VERSION=26": {"X"},
                                            "X-ABI-VIDEODRV_VERSION": {"X"}
                                            },
                                           {"V": {"V"},  # provided
                                            "V=2.5.0": {"V"},
                                            "X": {"X"},
                                            "X=21.1.5": {"X"},
                                            "X-ABI-VIDEODRV_VERSION=26": {"X"},
                                            "X-ABI-VIDEODRV_VERSION": {"X"}
                                            },
                                           {"X": {"X"},   # provided to remove
                                            "X=21.1.5": {"X"},
                                            "X-ABI-VIDEODRV_VERSION=26": {"X"},
                                            "X-ABI-VIDEODRV_VERSION": {"X"}
                                           }
                                           ]
        pacman.map_repositories.return_value = {"V": pkg_a.repository, "X": "community"}
        pacman.map_updates_data.return_value = {"V": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_a.latest_version,
                                                      'c': {"X<21.1.1",
                                                            "X-ABI-VIDEODRV_VERSION<25",
                                                            "X-ABI-VIDEODRV_VERSION>=26"},
                                                      'p': {"V": {"V"},
                                                            "V=2.5.0": {"A"}},
                                                      'd': set(),
                                                      'r': "community",
                                                      'des': pkg_a.name}}
        pacman.map_installed.return_value = {"V": pkg_a.version, "X": "21.1.5-1"}
        pacman.get_installed_size.return_value = {"V": 1, "X": 1}
        pacman.map_required_by.return_value = {"V": set()}

        self.deps_analyser.map_missing_deps.return_value = list()
        self.deps_analyser.map_all_required_by.return_value = set()

        res = self.summarizer.summarize(pkgs=[pkg_a], root_password=None, arch_config=self.config_)

        for method in ('map_provided', 'map_repositories', 'map_updates_data', 'map_installed',
                       'get_installed_size', 'map_required_by'):
            getattr(pacman, method).assert_called()

        for method in ('map_missing_deps', 'map_all_required_by'):
            getattr(self.deps_analyser, method).assert_called()

        self.assertFalse(res.to_install)
        self.assertEqual([UpgradeRequirement(pkg=pkg_a, required_size=1, extra_size=0)], res.to_upgrade)

        pkg_b = ArchPackage(name="X", installed=True, i18n=self.i18n)
        self.assertEqual([UpgradeRequirement(pkg=pkg_b, reason=" 'V'", extra_size=1)], res.to_remove)

    @patch(f"{__app_name__}.gems.arch.updates.pacman")
    def test__return_installed_virtual_with_defined_version_to_remove_when_conflict_matches__case_2(self, pacman: Mock):
        """
        This test case covers the same scenario as the above, but adds an additional provider for the same
        virtual package with a non-conflicting version

        Scenario:
        - Package V (2.5.0)[update] -> conflicts: X<21.1.1, X-ABI-VIDEODRV_VERSION<25, X-ABI-VIDEODRV_VERSION>=26
        - Package X (21.1.5)[installed] -> provides: X-ABI-VIDEODRV_VERSION=26, X
        - Package Z (2.0.0)[installed] -> provides: X-ABI-VIDEODRV_VERSION=25.2, Z

        * X provides X-ABI-VIDEODRV_VERSION with a specific version (26) [conflict]
        * Z provides X-ABI-VIDEODRV_VERSION with a specific version (25.2) [no conflict]
        """
        pkg_a = ArchPackage(name="V", version="2.5.0-1", latest_version="2.6.0-1", repository="community")

        pacman.map_provided.side_effect = [{"V": {"V"},  # remote provided
                                            "V=2.5.0": {"V"},
                                            "X": {"X"},
                                            "X=21.1.5": {"X"},
                                            "X-ABI-VIDEODRV_VERSION=26": {"X"},
                                            "Z": {"Z"},
                                            "Z=2.0.0": {"X"},
                                            "X-ABI-VIDEODRV_VERSION=25.2": {"Z"},
                                            "X-ABI-VIDEODRV_VERSION": {"X", "Z"},
                                            },
                                           {"V": {"V"},  # provided
                                            "V=2.5.0": {"V"},
                                            "X": {"X"},
                                            "X=21.1.5": {"X"},
                                            "X-ABI-VIDEODRV_VERSION=26": {"X"},
                                            "Z": {"Z"},
                                            "Z=2.0.0": {"X"},
                                            "X-ABI-VIDEODRV_VERSION=25.2": {"Z"},
                                            "X-ABI-VIDEODRV_VERSION": {"X", "Z"},
                                            },
                                           {"X": {"X"},  # provided to remove
                                            "X=21.1.5": {"X"},
                                            "X-ABI-VIDEODRV_VERSION=26": {"X"},
                                            "X-ABI-VIDEODRV_VERSION": {"X", "Z"}
                                            }
                                           ]
        pacman.map_repositories.return_value = {"V": pkg_a.repository, "X": "community"}
        pacman.map_updates_data.return_value = {"V": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_a.latest_version,
                                                      'c': {"X<21.1.1",
                                                            "X-ABI-VIDEODRV_VERSION<25",
                                                            "X-ABI-VIDEODRV_VERSION>=26"},
                                                      'p': {"V": {"V"},
                                                            "V=2.5.0": {"A"}},
                                                      'd': set(),
                                                      'r': "community",
                                                      'des': pkg_a.name}}
        pacman.map_installed.return_value = {"V": pkg_a.version, "X": "21.1.5-1", "Z": "2.0.0-1"}
        pacman.get_installed_size.return_value = {"V": 1, "X": 1, "Z": 1}
        pacman.map_required_by.return_value = {"V": set()}

        self.deps_analyser.map_missing_deps.return_value = list()
        self.deps_analyser.map_all_required_by.return_value = set()

        res = self.summarizer.summarize(pkgs=[pkg_a], root_password=None, arch_config=self.config_)

        for method in ('map_provided', 'map_repositories', 'map_updates_data', 'map_installed',
                       'get_installed_size', 'map_required_by'):
            getattr(pacman, method).assert_called()

        for method in ('map_missing_deps', 'map_all_required_by'):
            getattr(self.deps_analyser, method).assert_called()

        self.assertFalse(res.to_install)
        self.assertEqual([UpgradeRequirement(pkg=pkg_a, required_size=1, extra_size=0)], res.to_upgrade)

        pkg_b = ArchPackage(name="X", installed=True, i18n=self.i18n)
        self.assertEqual([UpgradeRequirement(pkg=pkg_b, reason=" 'V'", extra_size=1)], res.to_remove)

    @patch(f"{__app_name__}.gems.arch.updates.pacman")
    def test__should_return_installed_package_to_remove_when_conflict_with_provided_matches_version(self, pacman: Mock):
        """
        If the newest version o package A conflicts with a provided package C (by installed package B),
        and the conflict expression matches (e.g: A conflict expressions (C <= 0.7), C (0.7))
        then B should be marked as a package to be removed.
        """
        pkg_a = ArchPackage(name="A", version="1.0.0-1", latest_version="1.1.0-1", repository="community")

        pacman.map_provided.side_effect = [{"A": {"A"},  # remote provided
                                            "A=1.1.0": {"A"},
                                            "B": {"B", "C"},
                                            "B=0.8": {"B", "C"},
                                            "C": {"B"}
                                            },
                                           {"A": {"A"},  # provided
                                            "A=1.0.0": {"A"},
                                            "B": {"B", "C"},
                                            "B=0.7": {"B", "C"},
                                            "C": {"B"}
                                            },
                                           {"B": {"B"},  # provided to remove
                                            "B=0.7": {"B"}
                                            }
                                           ]
        pacman.map_repositories.return_value = {"A": pkg_a.repository, "B": "community"}
        pacman.map_updates_data.return_value = {"A": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_a.latest_version,
                                                      'c': {"C<=0.7"},
                                                      'p': {"A": {"A"},
                                                            "A=1.1.0": {"A"}},
                                                      'd': set(),
                                                      'r': "community",
                                                      'des': pkg_a.name}}
        pacman.map_installed.return_value = {"A": pkg_a.version, "B": "0.7-1"}
        pacman.get_installed_size.return_value = {"A": 1, "B": 1}
        pacman.map_required_by.return_value = {"A": set()}

        self.deps_analyser.map_missing_deps.return_value = list()
        self.deps_analyser.map_all_required_by.return_value = set()

        res = self.summarizer.summarize(pkgs=[pkg_a], root_password=None, arch_config=self.config_)

        for method in ('map_provided', 'map_repositories', 'map_updates_data', 'map_installed',
                       'get_installed_size', 'map_required_by'):
            getattr(pacman, method).assert_called()

        for method in ('map_missing_deps', 'map_all_required_by'):
            getattr(self.deps_analyser, method).assert_called()

        self.assertFalse(res.to_install)
        self.assertEqual([UpgradeRequirement(pkg=pkg_a, required_size=1, extra_size=0)], res.to_upgrade)

        pkg_b = ArchPackage(name="B", installed=True, i18n=self.i18n)
        self.assertEqual([UpgradeRequirement(pkg=pkg_b, reason=" 'A'", extra_size=1)], res.to_remove)

    @patch(f"{__app_name__}.gems.arch.updates.pacman")
    def test__should_return_installed_package_to_remove_when_conflict_with_provided_matches(self, pacman: Mock):
        """
        If the newest version o package A conflicts with a provided package C (by installed package B),
        then B should be marked as a package to be removed.
        """
        pkg_a = ArchPackage(name="A", version="1.0.0-1", latest_version="1.1.0-1", repository="community")

        pacman.map_provided.side_effect = [{"A": {"A"},  # remote provided
                                            "A=1.1.0": {"A"},
                                            "B": {"B", "C"},
                                            "B=0.8": {"B", "C"},
                                            "C": {"B"}
                                            },
                                           {"A": {"A"},  # provided
                                            "A=1.0.0": {"A"},
                                            "B": {"B", "C"},
                                            "B=0.7": {"B", "C"},
                                            "C": {"B"}
                                            },
                                           {"B": {"B"},  # provided to remove
                                            "B=0.7": {"B"}
                                            }
                                           ]
        pacman.map_repositories.return_value = {"A": pkg_a.repository, "B": "community"}
        pacman.map_updates_data.return_value = {"A": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_a.latest_version,
                                                      'c': {"C"},
                                                      'p': {"A": {"A"},
                                                            "A=1.1.0": {"A"}},
                                                      'd': set(),
                                                      'r': "community",
                                                      'des': pkg_a.name}}
        pacman.map_installed.return_value = {"A": pkg_a.version, "B": "0.7-1"}
        pacman.get_installed_size.return_value = {"A": 1, "B": 1}
        pacman.map_required_by.return_value = {"A": set()}

        self.deps_analyser.map_missing_deps.return_value = list()
        self.deps_analyser.map_all_required_by.return_value = set()

        res = self.summarizer.summarize(pkgs=[pkg_a], root_password=None, arch_config=self.config_)

        for method in ('map_provided', 'map_repositories', 'map_updates_data', 'map_installed',
                       'get_installed_size', 'map_required_by'):
            getattr(pacman, method).assert_called()

        for method in ('map_missing_deps', 'map_all_required_by'):
            getattr(self.deps_analyser, method).assert_called()

        self.assertFalse(res.to_install)
        self.assertEqual([UpgradeRequirement(pkg=pkg_a, required_size=1, extra_size=0)], res.to_upgrade)

        pkg_b = ArchPackage(name="B", installed=True, i18n=self.i18n)
        self.assertEqual([UpgradeRequirement(pkg=pkg_b, reason=" 'A'", extra_size=1)], res.to_remove)

    @patch(f"{__app_name__}.gems.arch.updates.pacman")
    def test__should_not_return_installed_to_remove_when_conflict_with_provider_is_self_conflict(self, pacman: Mock):
        """
        If the newest version o package A conflicts with a provided package C (by A itself),
        then A should not be marked as a package to be removed.
        """
        pkg_a = ArchPackage(name="A", version="1.0.0-1", latest_version="1.1.0-1", repository="community")

        pacman.map_provided.side_effect = [{"A": {"A"},  # remote provided
                                            "A=1.1.0": {"A"},
                                            "C": {"A"}
                                            },
                                           {"A": {"A"},  # provided
                                            "A=1.0.0": {"A"},
                                            "C": {"A"}
                                            }
                                           ]
        pacman.map_repositories.return_value = {"A": pkg_a.repository}
        pacman.map_updates_data.return_value = {"A": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_a.latest_version,
                                                      'c': {"C<=1.0.0"},
                                                      'p': {"A": {"A"},
                                                            "A=1.1.0": {"A"},
                                                            "C": {"A"}},
                                                      'd': set(),
                                                      'r': "community",
                                                      'des': pkg_a.name}}
        pacman.map_installed.return_value = {"A": pkg_a.version}
        pacman.get_installed_size.return_value = {"A": 1}
        pacman.map_required_by.return_value = {"A": set()}

        self.deps_analyser.map_missing_deps.return_value = list()

        res = self.summarizer.summarize(pkgs=[pkg_a], root_password=None, arch_config=self.config_)
        for method in ('map_provided', 'map_repositories', 'map_updates_data', 'map_installed',
                       'get_installed_size', 'map_required_by'):
            getattr(pacman, method).assert_called()

        self.assertFalse(res.to_remove)
        self.assertFalse(res.to_install)
        self.assertEqual([UpgradeRequirement(pkg=pkg_a, required_size=1, extra_size=0)], res.to_upgrade)

    @patch(f"{__app_name__}.gems.arch.updates.pacman")
    def test__return_as_cannot_upgrade_when_several_to_upgrade_conflict_with_each_other(self, pacman: Mock):
        """
        Consider package A and B are selected to be upgraded:

        If the newest version o package A conflicts with B, and newest version of B conflicts with A, then
        both should be returned as "cannot upgrade"
        """
        pkg_a = ArchPackage(name="A", version="1.0.0-1", latest_version="1.1.0-1", repository="community")
        pkg_b = ArchPackage(name="B", version="1.0.0-1", latest_version="1.1.0-1", repository="community")

        pacman.map_provided.side_effect = [{"A": {"A"},  # remote provided
                                            "A=1.1.0": {"A"},
                                            "B": {"B"},
                                            "B=1.1.0": {"B"}
                                            },
                                           {"A": {"A"},  # provided
                                            "A=1.0.0": {"A"},
                                            "B": {"B"},
                                            "B=1.0.0": {"B"},
                                            }
                                           ]
        pacman.map_repositories.return_value = {"A": pkg_a.repository, "B": pkg_b.repository}
        pacman.map_updates_data.return_value = {"A": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_a.latest_version,
                                                      'c': {"B"},
                                                      'p': {"A": {"A"},
                                                            "A=1.1.0": {"A"}},
                                                      'd': set(),
                                                      'r': pkg_a.repository,
                                                      'des': pkg_a.name},
                                                "B": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_b.latest_version,
                                                      'c': {"A"},
                                                      'p': {"B": {"B"},
                                                            "B=1.1.0": {"B"}},
                                                      'd': set(),
                                                      'r': pkg_a.repository,
                                                      'des': pkg_a.name}
                                                }
        pacman.map_installed.return_value = {"A": pkg_a.version, "B": pkg_b.version}
        self.deps_analyser.map_missing_deps.return_value = list()
        self.deps_analyser.map_all_required_by.return_value = set()

        res = self.summarizer.summarize(pkgs=[pkg_a, pkg_b], root_password=None, arch_config=self.config_)

        for method in ('map_provided', 'map_repositories', 'map_updates_data', 'map_installed'):
            getattr(pacman, method).assert_called()

        for method in ('map_missing_deps',):
            getattr(self.deps_analyser, method).assert_called()

        self.assertFalse(res.to_install)
        self.assertFalse(res.to_upgrade)
        self.assertEqual(2, len(res.cannot_upgrade))
        self.assertIn(UpgradeRequirement(pkg=pkg_a, reason=" 'B'"), res.cannot_upgrade)
        self.assertIn(UpgradeRequirement(pkg=pkg_b, reason=" 'A'"), res.cannot_upgrade)

    @patch(f"{__app_name__}.gems.arch.updates.pacman")
    def test__return_as_cannot_upgrade_when_several_to_upgrade_conflict_with_provided_by_each_other(self, pacman: Mock):
        """
        Consider package A and B are selected to be upgraded:

        If the newest version o package A conflicts with C (provided by B), and newest version of B
        conflicts with D (provided by A), then both should be returned as "cannot upgrade"
        """
        pkg_a = ArchPackage(name="A", version="1.0.0-1", latest_version="1.1.0-1", repository="community")
        pkg_b = ArchPackage(name="B", version="1.0.0-1", latest_version="1.1.0-1", repository="community")

        pacman.map_provided.side_effect = [{"A": {"A"},  # remote provided
                                            "A=1.1.0": {"A"},
                                            "B": {"B"},
                                            "B=1.1.0": {"B"}
                                            },
                                           {"A": {"A"},  # provided
                                            "A=1.0.0": {"A"},
                                            "B": {"B"},
                                            "B=1.0.0": {"B"},
                                            }
                                           ]
        pacman.map_repositories.return_value = {"A": pkg_a.repository, "B": pkg_b.repository}
        pacman.map_updates_data.return_value = {"A": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_a.latest_version,
                                                      'c': {"C"},
                                                      'p': {"A": {"A"},
                                                            "A=1.1.0": {"A"},
                                                            "D": {"A"}},
                                                      'd': set(),
                                                      'r': pkg_a.repository,
                                                      'des': pkg_a.name},
                                                "B": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_b.latest_version,
                                                      'c': {"D"},
                                                      'p': {"B": {"B"},
                                                            "B=1.1.0": {"B"},
                                                            "C": {"B"}},
                                                      'd': set(),
                                                      'r': pkg_a.repository,
                                                      'des': pkg_a.name}
                                                }
        pacman.map_installed.return_value = {"A": pkg_a.version, "B": pkg_b.version}
        self.deps_analyser.map_missing_deps.return_value = list()
        self.deps_analyser.map_all_required_by.return_value = set()

        res = self.summarizer.summarize(pkgs=[pkg_a, pkg_b], root_password=None, arch_config=self.config_)

        for method in ('map_provided', 'map_repositories', 'map_updates_data', 'map_installed'):
            getattr(pacman, method).assert_called()

        for method in ('map_missing_deps',):
            getattr(self.deps_analyser, method).assert_called()

        self.assertFalse(res.to_install)
        self.assertFalse(res.to_upgrade)
        self.assertEqual(2, len(res.cannot_upgrade))
        self.assertIn(UpgradeRequirement(pkg=pkg_a, reason=" 'B'"), res.cannot_upgrade)
        self.assertIn(UpgradeRequirement(pkg=pkg_b, reason=" 'A'"), res.cannot_upgrade)

    @patch(f"{__app_name__}.gems.arch.updates.pacman")
    def test__return_as_to_remove_when_a_package_to_upgrade_conflicts_with_another(self, pacman: Mock):
        """
        Consider package A and B are selected to be upgraded:

        If the newest version o package A conflicts with B, then B should be marked as 'to_remove'
        """
        pkg_a = ArchPackage(name="A", version="1.0.0-1", latest_version="1.1.0-1", repository="community")
        pkg_b = ArchPackage(name="B", version="1.0.0-1", latest_version="1.1.0-1", repository="community")

        pacman.map_provided.side_effect = [{"A": {"A"},  # remote provided
                                            "A=1.1.0": {"A"},
                                            "B": {"B"},
                                            "B=1.1.0": {"B"}
                                            },
                                           {"A": {"A"},  # provided
                                            "A=1.0.0": {"A"},
                                            "B": {"B"},
                                            "B=1.0.0": {"B"},
                                            }
                                           ]
        pacman.map_repositories.return_value = {"A": pkg_a.repository, "B": pkg_b.repository}
        pacman.map_updates_data.return_value = {"A": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_a.latest_version,
                                                      'c': {"B"},
                                                      'p': {"A": {"A"},
                                                            "A=1.1.0": {"A"}},
                                                      'd': set(),
                                                      'r': pkg_a.repository,
                                                      'des': pkg_a.name},
                                                "B": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_b.latest_version,
                                                      'c': set(),
                                                      'p': {"B": {"B"},
                                                            "B=1.1.0": {"B"}},
                                                      'd': set(),
                                                      'r': pkg_a.repository,
                                                      'des': pkg_a.name}
                                                }
        pacman.map_installed.return_value = {"A": pkg_a.version, "B": pkg_b.version}
        pacman.get_installed_size.return_value = {"A": 1, "B": 1}
        pacman.map_required_by.return_value = {"A": set(), "B": set()}

        self.deps_analyser.map_missing_deps.return_value = list()
        self.deps_analyser.map_all_required_by.return_value = set()

        res = self.summarizer.summarize(pkgs=[pkg_a, pkg_b], root_password=None, arch_config=self.config_)

        for method in ('map_provided', 'map_repositories', 'map_updates_data', 'map_installed',
                       'get_installed_size', 'map_required_by'):
            getattr(pacman, method).assert_called()

        for method in ('map_missing_deps', 'map_all_required_by'):
            getattr(self.deps_analyser, method).assert_called()

        self.assertFalse(res.cannot_upgrade)
        self.assertFalse(res.to_install)
        self.assertEqual([UpgradeRequirement(pkg=pkg_a, required_size=1, extra_size=0)], res.to_upgrade)
        self.assertEqual([UpgradeRequirement(pkg=pkg_b, reason=" 'A'", extra_size=1)], res.to_remove)

    @patch(f"{__app_name__}.gems.arch.updates.pacman")
    def test__return_as_to_remove_when_a_package_to_upgrade_conflicts_with_provided_by_another(self, pacman: Mock):
        """
        Consider package A and B are selected to be upgraded:

        If the newest version o package A conflicts with C (provided by B), then B should be marked as 'to_remove'
        """
        pkg_a = ArchPackage(name="A", version="1.0.0-1", latest_version="1.1.0-1", repository="community")
        pkg_b = ArchPackage(name="B", version="1.0.0-1", latest_version="1.1.0-1", repository="community")

        pacman.map_provided.side_effect = [{"A": {"A"},  # remote provided
                                            "A=1.1.0": {"A"},
                                            "B": {"B"},
                                            "B=1.1.0": {"B"},
                                            "C": {"B"}
                                            },
                                           {"A": {"A"},  # provided
                                            "A=1.0.0": {"A"},
                                            "B": {"B"},
                                            "B=1.0.0": {"B"},
                                            "C": {"B"}
                                            }
                                           ]
        pacman.map_repositories.return_value = {"A": pkg_a.repository, "B": pkg_b.repository}
        pacman.map_updates_data.return_value = {"A": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_a.latest_version,
                                                      'c': {"C"},
                                                      'p': {"A": {"A"},
                                                            "A=1.1.0": {"A"}},
                                                      'd': set(),
                                                      'r': pkg_a.repository,
                                                      'des': pkg_a.name},
                                                "B": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_b.latest_version,
                                                      'c': set(),
                                                      'p': {"B": {"B"},
                                                            "B=1.1.0": {"B"},
                                                            "C": {"B"}},
                                                      'd': set(),
                                                      'r': pkg_a.repository,
                                                      'des': pkg_a.name}
                                                }
        pacman.map_installed.return_value = {"A": pkg_a.version, "B": pkg_b.version}
        pacman.get_installed_size.return_value = {"A": 1, "B": 1}
        pacman.map_required_by.return_value = {"A": set(), "B": set()}

        self.deps_analyser.map_missing_deps.return_value = list()
        self.deps_analyser.map_all_required_by.return_value = set()

        res = self.summarizer.summarize(pkgs=[pkg_a, pkg_b], root_password=None, arch_config=self.config_)

        for method in ('map_provided', 'map_repositories', 'map_updates_data', 'map_installed',
                       'get_installed_size', 'map_required_by'):
            getattr(pacman, method).assert_called()

        for method in ('map_missing_deps', 'map_all_required_by'):
            getattr(self.deps_analyser, method).assert_called()

        self.assertFalse(res.cannot_upgrade)
        self.assertFalse(res.to_install)
        self.assertEqual([UpgradeRequirement(pkg=pkg_a, required_size=1, extra_size=0)], res.to_upgrade)
        self.assertEqual([UpgradeRequirement(pkg=pkg_b, reason=" 'A'", extra_size=1)], res.to_remove)

    @patch(f"{__app_name__}.gems.arch.updates.pacman")
    def test__return_as_to_remove_when_a_package_to_upgrade_conflicts_with_provided_version_by_another(self, pacman: Mock):
        """
        Consider package A and B are selected to be upgraded:

        If the newest version o package A conflicts with specific version of C (provided by B),
        then B should be marked as 'to_remove'
        """
        pkg_a = ArchPackage(name="A", version="1.0.0-1", latest_version="1.1.0-1", repository="community")
        pkg_b = ArchPackage(name="B", version="1.0.0-1", latest_version="1.1.0-1", repository="community")

        pacman.map_provided.side_effect = [{"A": {"A"},  # remote provided
                                            "A=1.1.0": {"A"},
                                            "B": {"B"},
                                            "B=1.1.0": {"B"},
                                            "C": {"B"}
                                            },
                                           {"A": {"A"},  # provided
                                            "A=1.0.0": {"A"},
                                            "B": {"B"},
                                            "B=1.0.0": {"B"},
                                            "C": {"B"}
                                            }
                                           ]
        pacman.map_repositories.return_value = {"A": pkg_a.repository, "B": pkg_b.repository}
        pacman.map_updates_data.return_value = {"A": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_a.latest_version,
                                                      'c': {"C<=1.1.0"},
                                                      'p': {"A": {"A"},
                                                            "A=1.1.0": {"A"}},
                                                      'd': set(),
                                                      'r': pkg_a.repository,
                                                      'des': pkg_a.name},
                                                "B": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_b.latest_version,
                                                      'c': set(),
                                                      'p': {"B": {"B"},
                                                            "B=1.1.0": {"B"},
                                                            "C": {"B"}},
                                                      'd': set(),
                                                      'r': pkg_a.repository,
                                                      'des': pkg_a.name}
                                                }
        pacman.map_installed.return_value = {"A": pkg_a.version, "B": pkg_b.version}
        pacman.get_installed_size.return_value = {"A": 1, "B": 1}
        pacman.map_required_by.return_value = {"A": set(), "B": set()}

        self.deps_analyser.map_missing_deps.return_value = list()
        self.deps_analyser.map_all_required_by.return_value = set()

        res = self.summarizer.summarize(pkgs=[pkg_a, pkg_b], root_password=None, arch_config=self.config_)

        for method in ('map_provided', 'map_repositories', 'map_updates_data', 'map_installed',
                       'get_installed_size', 'map_required_by'):
            getattr(pacman, method).assert_called()

        for method in ('map_missing_deps', 'map_all_required_by'):
            getattr(self.deps_analyser, method).assert_called()

        self.assertFalse(res.cannot_upgrade)
        self.assertFalse(res.to_install)
        self.assertEqual([UpgradeRequirement(pkg=pkg_a, required_size=1, extra_size=0)], res.to_upgrade)
        self.assertEqual([UpgradeRequirement(pkg=pkg_b, reason=" 'A'", extra_size=1)], res.to_remove)

    @patch(f"{__app_name__}.gems.arch.dependencies.pacman")
    @patch(f"{__app_name__}.gems.arch.updates.pacman")
    def test__return_as_cannot_upgrade_when_several_packages_to_install_conflict_with_each_other(self, *mocks: Mock):
        """
        Consider package A and B are selected to be upgraded:

        If the newest version o package A requires a new package C that conflicts D (new dependency of B),
        and D conflicts with C, then A and B should be marked as 'cannot upgrade'.
        """
        pkg_a = ArchPackage(name="A", version="1.0.0-1", latest_version="1.1.0-1", repository="community")
        pkg_b = ArchPackage(name="B", version="1.0.0-1", latest_version="1.1.0-1", repository="community")

        pacman, pacman_dependencies = mocks[0], mocks[1]
        pacman.map_provided.side_effect = [{"A": {"A"},  # remote provided
                                            "A=1.1.0": {"A"},
                                            "B": {"B"},
                                            "B=1.1.0": {"B"},
                                            "C": {"C"},
                                            "D": {"D"}
                                            },
                                           {"A": {"A"},  # provided
                                            "A=1.0.0": {"A"},
                                            "B": {"B"},
                                            "B=1.0.0": {"B"},
                                            }
                                           ]
        pacman.map_repositories.return_value = {c: "community" for c in ("A", "B", "C", "D")}
        pacman.map_updates_data.side_effect = [{"A": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_a.latest_version,
                                                      'c': set(),
                                                      'p': {"A": {"A"},
                                                            "A=1.1.0": {"A"}},
                                                      'd': {"C"},
                                                      'r': pkg_a.repository,
                                                      'des': "A"},
                                                "B": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_b.latest_version,
                                                      'c': set(),
                                                      'p': {"B": {"B"},
                                                            "B=1.1.0": {"B"}},
                                                      'd': {"D"},
                                                      'r': pkg_a.repository,
                                                      'des': "B"}
                                                },
                                               {"C": {'ds': 1,
                                                      's': 1,
                                                      'v': "1.1.0-1",
                                                      'c': {"D"},
                                                      'p': {"C": {"C"},
                                                            "C=1.1.0": {"C"}},
                                                      'd': set(),
                                                      'r': "community",
                                                      'des': "C"},
                                                "D": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_b.latest_version,
                                                      'c': {"C"},
                                                      'p': {"D": {"D"},
                                                            "D=1.1.0": {"D"}},
                                                      'd': set(),
                                                      'r': "community",
                                                      'des': "D"}
                                                }]
        pacman_dependencies.map_updates_data.return_value = {"C": {'ds': 1,
                                                                   's': 1,
                                                                   'v': "1.1.0-1",
                                                                   'c': {"D"},
                                                                   'p': {"C": {"C"},
                                                                         "C=1.1.0": {"C"}},
                                                                   'd': set(),
                                                                   'r': "community",
                                                                   'des': "C"},
                                                             "D": {'ds': 1,
                                                                   's': 1,
                                                                   'v': pkg_b.latest_version,
                                                                   'c': {"C"},
                                                                   'p': {"D": {"D"},
                                                                         "D=1.1.0": {"D"}},
                                                                   'd': set(),
                                                                   'r': "community",
                                                                   'des': "D"}
                                                             }
        pacman.map_installed.return_value = {"A": pkg_a.version, "B": pkg_b.version}
        pacman.map_required_by.return_value = {c: set() for c in ("A", "B", "C", "D")}
        self.deps_analyser = DependenciesAnalyser(aur_client=self.aur_client, i18n=self.i18n, logger=Mock())
        self.summarizer.deps_analyser = self.deps_analyser

        res = self.summarizer.summarize(pkgs=[pkg_a, pkg_b], root_password=None, arch_config=self.config_)

        for method in ('map_provided', 'map_repositories', 'map_updates_data', 'map_installed'):
            getattr(pacman, method).assert_called()

        pacman_dependencies.map_updates_data.assert_called()

        self.assertFalse(res.to_install)
        self.assertFalse(res.to_upgrade)
        self.assertEqual(2, len(res.cannot_upgrade))
        self.assertIn(UpgradeRequirement(pkg=pkg_a, reason="'C' 'D'"), res.cannot_upgrade)
        self.assertIn(UpgradeRequirement(pkg=pkg_b, reason="'C' 'D'"), res.cannot_upgrade)

    @patch(f"{__app_name__}.gems.arch.dependencies.pacman")
    @patch(f"{__app_name__}.gems.arch.updates.pacman")
    def test__return_as_cannot_upgrade_when_packages_to_install_conflict_with_version_of_each_other(self, *mocks: Mock):
        """
        Consider package A and B are selected to be upgraded:

        If the newest version o package A requires a new package C that conflicts with D's version
        (new dependency of B), and D conflicts with C's version, then A and B should be marked as 'cannot upgrade'.
        """
        pkg_a = ArchPackage(name="A", version="1.0.0-1", latest_version="1.1.0-1", repository="community")
        pkg_b = ArchPackage(name="B", version="1.0.0-1", latest_version="1.1.0-1", repository="community")

        pacman, pacman_dependencies = mocks[0], mocks[1]
        pacman.map_provided.side_effect = [{"A": {"A"},  # remote provided
                                            "A=1.1.0": {"A"},
                                            "B": {"B"},
                                            "B=1.1.0": {"B"},
                                            "C": {"C"},
                                            "D": {"D"}
                                            },
                                           {"A": {"A"},  # provided
                                            "A=1.0.0": {"A"},
                                            "B": {"B"},
                                            "B=1.0.0": {"B"},
                                            }
                                           ]
        pacman.map_repositories.return_value = {c: "community" for c in ("A", "B", "C", "D")}
        pacman.map_updates_data.side_effect = [{"A": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_a.latest_version,
                                                      'c': set(),
                                                      'p': {"A": {"A"},
                                                            "A=1.1.0": {"A"}},
                                                      'd': {"C"},
                                                      'r': pkg_a.repository,
                                                      'des': "A"},
                                                "B": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_b.latest_version,
                                                      'c': set(),
                                                      'p': {"B": {"B"},
                                                            "B=1.1.0": {"B"}},
                                                      'd': {"D"},
                                                      'r': pkg_a.repository,
                                                      'des': "B"}
                                                },
                                               {"C": {'ds': 1,
                                                      's': 1,
                                                      'v': "1.1.0-1",
                                                      'c': {"D<=1.1.0"},
                                                      'p': {"C": {"C"},
                                                            "C=1.1.0": {"C"}},
                                                      'd': set(),
                                                      'r': "community",
                                                      'des': "C"},
                                                "D": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_b.latest_version,
                                                      'c': {"C<=1.1.0"},
                                                      'p': {"D": {"D"},
                                                            "D=1.1.0": {"D"}},
                                                      'd': set(),
                                                      'r': "community",
                                                      'des': "D"}
                                                }]
        pacman_dependencies.map_updates_data.return_value = {"C": {'ds': 1,
                                                                   's': 1,
                                                                   'v': "1.1.0-1",
                                                                   'c': {"D<=1.1.0"},
                                                                   'p': {"C": {"C"},
                                                                         "C=1.1.0": {"C"}},
                                                                   'd': set(),
                                                                   'r': "community",
                                                                   'des': "C"},
                                                             "D": {'ds': 1,
                                                                   's': 1,
                                                                   'v': pkg_b.latest_version,
                                                                   'c': {"C<=1.1.0"},
                                                                   'p': {"D": {"D"},
                                                                         "D=1.1.0": {"D"}},
                                                                   'd': set(),
                                                                   'r': "community",
                                                                   'des': "D"}
                                                             }
        pacman.map_installed.return_value = {"A": pkg_a.version, "B": pkg_b.version}
        pacman.map_required_by.return_value = {c: set() for c in ("A", "B", "C", "D")}
        self.deps_analyser = DependenciesAnalyser(aur_client=self.aur_client, i18n=self.i18n, logger=Mock())
        self.summarizer.deps_analyser = self.deps_analyser

        res = self.summarizer.summarize(pkgs=[pkg_a, pkg_b], root_password=None, arch_config=self.config_)

        for method in ('map_provided', 'map_repositories', 'map_updates_data', 'map_installed'):
            getattr(pacman, method).assert_called()

        pacman_dependencies.map_updates_data.assert_called()

        self.assertFalse(res.to_install)
        self.assertFalse(res.to_upgrade)
        self.assertEqual(2, len(res.cannot_upgrade))
        self.assertIn(UpgradeRequirement(pkg=pkg_a, reason="'C' 'D'"), res.cannot_upgrade)
        self.assertIn(UpgradeRequirement(pkg=pkg_b, reason="'C' 'D'"), res.cannot_upgrade)

    @patch(f"{__app_name__}.gems.arch.dependencies.pacman")
    @patch(f"{__app_name__}.gems.arch.updates.pacman")
    def test__return_as_to_remove_when_to_update_conflicts_with_to_install(self, *mocks: Mock):
        """
        Consider package A and B are selected to be upgraded:

        If the newest version o package A requires a new package C that conflicts with B,
        then B should be marked as "to_remove"
        """
        pkg_a = ArchPackage(name="A", version="1.0.0-1", latest_version="1.1.0-1", repository="community")
        pkg_b = ArchPackage(name="B", version="1.0.0-1", latest_version="1.1.0-1", repository="community")

        pacman, pacman_dependencies = mocks[0], mocks[1]
        pacman.map_provided.side_effect = [{"A": {"A"},  # remote provided
                                            "A=1.1.0": {"A"},
                                            "B": {"B"},
                                            "B=1.1.0": {"B"},
                                            "C": {"C"}
                                            },
                                           {"A": {"A"},  # provided
                                            "A=1.0.0": {"A"},
                                            "B": {"B"},
                                            "B=1.0.0": {"B"},
                                            }
                                           ]
        pacman.map_repositories.return_value = {c: "community" for c in ("A", "B", "C")}
        pacman.map_updates_data.side_effect = [{"A": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_a.latest_version,
                                                      'c': set(),
                                                      'p': {"A": {"A"},
                                                            "A=1.1.0": {"A"}},
                                                      'd': {"C"},
                                                      'r': pkg_a.repository,
                                                      'des': "A"},
                                                "B": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_b.latest_version,
                                                      'c': set(),
                                                      'p': {"B": {"B"},
                                                            "B=1.1.0": {"B"}},
                                                      'd': set(),
                                                      'r': pkg_a.repository,
                                                      'des': "B"}
                                                },
                                               {"C": {'ds': 1,
                                                      's': 1,
                                                      'v': "1.1.0-1",
                                                      'c': {"B"},
                                                      'p': {"C": {"C"},
                                                            "C=1.1.0": {"C"}},
                                                      'd': set(),
                                                      'r': "community",
                                                      'des': "C"}
                                                }
                                               ]
        pacman_dependencies.map_updates_data.return_value = {"C": {'ds': 1,
                                                                   's': 1,
                                                                   'v': "1.1.0-1",
                                                                   'c': {"B"},
                                                                   'p': {"C": {"C"},
                                                                         "C=1.1.0": {"C"}},
                                                                   'd': set(),
                                                                   'r': "community",
                                                                   'des': "C"}
                                                             }
        pacman.map_installed.return_value = {"A": pkg_a.version, "B": pkg_b.version}
        pacman.map_required_by.return_value = {c: set() for c in ("A", "B", "C")}
        pacman.get_installed_size.return_value = {"A": 1, "B": 1, "C": 1}
        self.deps_analyser = DependenciesAnalyser(aur_client=self.aur_client, i18n=self.i18n, logger=Mock())
        self.summarizer.deps_analyser = self.deps_analyser

        res = self.summarizer.summarize(pkgs=[pkg_a, pkg_b], root_password=None, arch_config=self.config_)

        for method in ('map_provided', 'map_repositories', 'map_updates_data', 'map_installed', 'get_installed_size',
                       'map_required_by'):
            getattr(pacman, method).assert_called()

        pacman_dependencies.map_updates_data.assert_called()

        self.assertFalse(res.cannot_upgrade)

        pkg_c = ArchPackage(name="C", version="1.0.0-1", latest_version="1.1.0-1", repository="community")
        self.assertEqual([UpgradeRequirement(pkg=pkg_c, required_size=1, extra_size=1, reason=": A")], res.to_install)
        self.assertEqual([UpgradeRequirement(pkg=pkg_a, required_size=1, extra_size=0)], res.to_upgrade)
        self.assertEqual([UpgradeRequirement(pkg=pkg_b, extra_size=1, reason=" 'C'")], res.to_remove)

    @patch(f"{__app_name__}.gems.arch.dependencies.pacman")
    @patch(f"{__app_name__}.gems.arch.updates.pacman")
    def test__return_as_to_remove_when_to_update_conflicts_with_specific_version_of_install(self, *mocks: Mock):
        """
        Consider package A and B are selected to be upgraded:

        If the newest version o package A requires a new package C that conflicts with latest version of B,
        then B should be marked as 'to_remove'.
        """
        pkg_a = ArchPackage(name="A", version="1.0.0-1", latest_version="1.1.0-1", repository="community")
        pkg_b = ArchPackage(name="B", version="1.0.0-1", latest_version="1.1.0-1", repository="community")

        pacman, pacman_dependencies = mocks[0], mocks[1]
        pacman.map_provided.side_effect = [{"A": {"A"},  # remote provided
                                            "A=1.1.0": {"A"},
                                            "B": {"B"},
                                            "B=1.1.0": {"B"},
                                            "C": {"C"}
                                            },
                                           {"A": {"A"},  # provided
                                            "A=1.0.0": {"A"},
                                            "B": {"B"},
                                            "B=1.0.0": {"B"},
                                            }
                                           ]
        pacman.map_repositories.return_value = {c: "community" for c in ("A", "B", "C")}
        pacman.map_updates_data.side_effect = [{"A": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_a.latest_version,
                                                      'c': set(),
                                                      'p': {"A": {"A"},
                                                            "A=1.1.0": {"A"}},
                                                      'd': {"C"},
                                                      'r': pkg_a.repository,
                                                      'des': "A"},
                                                "B": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_b.latest_version,
                                                      'c': set(),
                                                      'p': {"B": {"B"},
                                                            "B=1.1.0": {"B"}},
                                                      'd': set(),
                                                      'r': pkg_a.repository,
                                                      'des': "B"}
                                                },
                                               {"C": {'ds': 1,
                                                      's': 1,
                                                      'v': "1.1.0-1",
                                                      'c': {"B<=1.1.0"},
                                                      'p': {"C": {"C"},
                                                            "C=1.1.0": {"C"}},
                                                      'd': set(),
                                                      'r': "community",
                                                      'des': "C"}
                                                }
                                               ]
        pacman_dependencies.map_updates_data.return_value = {"C": {'ds': 1,
                                                                   's': 1,
                                                                   'v': "1.1.0-1",
                                                                   'c': {"B<=1.1.0"},
                                                                   'p': {"C": {"C"},
                                                                         "C=1.1.0": {"C"}},
                                                                   'd': set(),
                                                                   'r': "community",
                                                                   'des': "C"}
                                                             }
        pacman.map_installed.return_value = {"A": pkg_a.version, "B": pkg_b.version}
        pacman.map_required_by.return_value = {c: set() for c in ("A", "B", "C")}
        pacman.get_installed_size.return_value = {"A": 1, "B": 1, "C": 1}
        self.deps_analyser = DependenciesAnalyser(aur_client=self.aur_client, i18n=self.i18n, logger=Mock())
        self.summarizer.deps_analyser = self.deps_analyser

        res = self.summarizer.summarize(pkgs=[pkg_a, pkg_b], root_password=None, arch_config=self.config_)

        for method in ('map_provided', 'map_repositories', 'map_updates_data', 'map_installed', 'get_installed_size',
                       'map_required_by'):
            getattr(pacman, method).assert_called()

        pacman_dependencies.map_updates_data.assert_called()

        self.assertFalse(res.cannot_upgrade)

        pkg_c = ArchPackage(name="C", version="1.0.0-1", latest_version="1.1.0-1", repository="community")
        self.assertEqual([UpgradeRequirement(pkg=pkg_c, required_size=1, extra_size=1, reason=": A")], res.to_install)
        self.assertEqual([UpgradeRequirement(pkg=pkg_a, required_size=1, extra_size=0)], res.to_upgrade)
        self.assertEqual([UpgradeRequirement(pkg=pkg_b, extra_size=1, reason=" 'C'")], res.to_remove)

    @patch(f"{__app_name__}.gems.arch.dependencies.pacman")
    @patch(f"{__app_name__}.gems.arch.updates.pacman")
    def test__return_as_to_remove_when_to_update_conflicts_with_to_install_and_it_has_deps(self, *mocks: Mock):
        """
        Consider package A and B are selected to be upgraded:

        If the newest version o package A requires a new package C that conflicts with B,
        then B should be marked as "to_remove" and its dependents as well (package 'D').
        """
        pkg_a = ArchPackage(name="A", version="1.0.0-1", latest_version="1.1.0-1", repository="community")
        pkg_b = ArchPackage(name="B", version="1.0.0-1", latest_version="1.1.0-1", repository="community")

        pacman, pacman_dependencies = mocks[0], mocks[1]
        pacman.map_provided.side_effect = [{"A": {"A"},  # remote provided
                                            "A=1.1.0": {"A"},
                                            "B": {"B"},
                                            "B=1.1.0": {"B"},
                                            "C": {"C"}
                                            },
                                           {"A": {"A"},  # provided
                                            "A=1.0.0": {"A"},
                                            "B": {"B"},
                                            "B=1.0.0": {"B"},
                                            "D": {"D"},
                                            "D=0.7.0": {"D"}
                                            },
                                           {"B": {"B"},  # provided to remove
                                            "B=1.0.0": {"B"},
                                            "D": {"D"},
                                            "D=0.7.0": {"D"}
                                            }
                                           ]
        pacman.map_repositories.return_value = {c: "community" for c in ("A", "B", "C", "D")}
        pacman.map_updates_data.side_effect = [{"A": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_a.latest_version,
                                                      'c': set(),
                                                      'p': {"A": {"A"},
                                                            "A=1.1.0": {"A"}},
                                                      'd': {"C"},
                                                      'r': pkg_a.repository,
                                                      'des': "A"},
                                                "B": {'ds': 1,
                                                      's': 1,
                                                      'v': pkg_b.latest_version,
                                                      'c': set(),
                                                      'p': {"B": {"B"},
                                                            "B=1.1.0": {"B"}},
                                                      'd': set(),
                                                      'r': pkg_a.repository,
                                                      'des': "B"}
                                                },
                                               {"C": {'ds': 1,
                                                      's': 1,
                                                      'v': "1.1.0-1",
                                                      'c': {"B"},
                                                      'p': {"C": {"C"},
                                                            "C=1.1.0": {"C"}},
                                                      'd': set(),
                                                      'r': "community",
                                                      'des': "C"}
                                                }
                                               ]
        pacman_dependencies.map_updates_data.return_value = {"C": {'ds': 1,
                                                                   's': 1,
                                                                   'v': "1.1.0-1",
                                                                   'c': {"B"},
                                                                   'p': {"C": {"C"},
                                                                         "C=1.1.0": {"C"}},
                                                                   'd': set(),
                                                                   'r': "community",
                                                                   'des': "C"}
                                                             }
        pacman_dependencies.map_required_by.return_value = {"B": {"D"}}

        pacman.map_installed.return_value = {"A": pkg_a.version, "B": pkg_b.version, "D": "0.7.0"}
        pacman.map_required_by.return_value = {**{c: set() for c in ("A", "C", "D")}, "B": {"D"}}
        pacman.map_required_dependencies.return_value = {"D": {"B"}}
        pacman.get_installed_size.return_value = {"A": 1, "B": 1, "C": 1, "D": 1}

        self.deps_analyser = DependenciesAnalyser(aur_client=self.aur_client, i18n=self.i18n, logger=Mock())
        self.summarizer.deps_analyser = self.deps_analyser

        res = self.summarizer.summarize(pkgs=[pkg_a, pkg_b], root_password=None, arch_config=self.config_)

        for method in ('map_provided', 'map_repositories', 'map_updates_data', 'map_installed', 'get_installed_size',
                       'map_required_by', 'map_required_dependencies'):
            getattr(pacman, method).assert_called()

        for method in ('map_updates_data', 'map_required_by'):
            getattr(pacman_dependencies, method).assert_called()

        self.assertFalse(res.cannot_upgrade)

        self.assertEqual([UpgradeRequirement(pkg=pkg_a, required_size=1, extra_size=0)], res.to_upgrade)

        pkg_c = ArchPackage(name="C", version="1.0.0-1", latest_version="1.1.0-1", repository="community")
        self.assertEqual([UpgradeRequirement(pkg=pkg_c, required_size=1, extra_size=1, reason=": A")], res.to_install)

        self.assertEqual(2, len(res.to_remove))
        self.assertIn(UpgradeRequirement(pkg=pkg_b, extra_size=1, reason=" 'C'"), res.to_remove)

        pkg_d = ArchPackage(name="D", repository="community", version="0.7.0-1", latest_version="0.7.0-1")
        self.assertIn(UpgradeRequirement(pkg=pkg_d, extra_size=1, reason=" 'B=1.0.0'"), res.to_remove)
