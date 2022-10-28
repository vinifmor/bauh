from unittest import TestCase
from unittest.mock import Mock, patch

from bauh import __app_name__
from bauh.commons import system
from bauh.commons.system import USE_GLOBAL_INTERPRETER
from bauh.gems.debian.aptitude import Aptitude, map_package_name
from bauh.gems.debian.model import DebianPackage


class MapPackageNameTest(TestCase):

    def test__it_must_return_the_same_input_when_no_colon(self):
        self.assertEqual('my_package', map_package_name('my_package'))

    def test__it_must_return_the_only_the_word_before_the_first_colon(self):
        self.assertEqual('my_package', map_package_name('my_package:i386'))

    def test__it_must_return_a_name_with_colon_when_several_colons_are_present(self):
        self.assertEqual('my_package:i386', map_package_name('my_package:i386:amd64'))


class AptitudeTest(TestCase):

    def setUp(self):
        self.aptitude = Aptitude(Mock())

    @patch(f'{__app_name__}.gems.debian.aptitude.system.execute', return_value=(0, """
gimp-cbmplugs^<none>^1.2.2-1build1^Distro Developers <distro-devel-discuss@lists.distro.com>^universe/graphics^plugins for The GIMP to import/export Commodore 64 files
gimp-gmic^2.4.5-1.0^2.4.5-1.1^Distro Developers <distro-devel-discuss@lists.distro.com>^plugin^GREYC's Magic for Image Computing - GIMP Plugin
gimp-gutenprint^5.3.3-4^5.3.3-4^Distro Developers <distro-devel-discuss@lists.distro.com>^plugin^print plugin for the GIMP
gimp-help^<none>^<none>^<none>^^
    """))
    def test_search__must_return_installed_and_not_installed_packages_with_updates(self, execute: Mock):
        query = 'gimp'
        res = [p for p in self.aptitude.search(query=query)]

        execute.assert_called_once_with(f"aptitude search {query} -q -F '%p^%v^%V^%m^%s^%d' --disable-columns", shell=True)

        exp = [
            DebianPackage(name='gimp-cbmplugs', version='1.2.2-1build1', latest_version='1.2.2-1build1',
                          maintainer='Distro Developers',
                          description='plugins for The GIMP to import/export Commodore 64 files',
                          categories=('graphics',),
                          installed=False, update=False),
            DebianPackage(name='gimp-gmic', version='2.4.5-1.0', latest_version='2.4.5-1.1',
                          maintainer='Distro Developers',
                          description="GREYC's Magic for Image Computing - GIMP Plugin",
                          categories=('plugin',),
                          installed=True, update=True),
            DebianPackage(name='gimp-gutenprint', version='5.3.3-4', latest_version='5.3.3-4',
                          maintainer='Distro Developers',
                          description="print plugin for the GIMP",
                          categories=('plugin',),
                          installed=True, update=False),
        ]

        self.assertEqual([p.__dict__ for p in exp], [p.__dict__ for p in res])

    @patch(f'{__app_name__}.gems.debian.aptitude.system.execute', return_value=(0, """
Package: firefox                         
Version: 97.0+distro1+una
State: installed (95.0.1+distro1.1+una), upgrade available (97.0+distro1+una)
Automatically installed: no
Priority: optional
Section: web
Maintainer: Distro Dev <root@distro.com>
Architecture: amd64
Uncompressed Size: 236 M
PreDepends: distro-system-adjustments (>= 2021.12.16)
Breaks: firefox-dbg (< 95.0.1+distro1+una), firefox-dev (< 95.0.1+distro1+una), firefox-geckodriver (< 95.0.1+distro1+una), firefox-mozsymbols (< 95.0.1+distro1+una)
Replaces: firefox-dbg (< 95.0.1+distro1+una), firefox-dev (< 95.0.1+distro1+una), firefox-geckodriver (< 95.0.1+distro1+una), firefox-mozsymbols (< 95.0.1+distro1+una)
Provides: gnome-www-browser, www-browser
Description: The Firefox web browser
 The Mozilla Firefox Web Browser.

Package: gcc
Version: 4:9.3.0-1distro2
State: installed
Automatically installed: no
Priority: optional
Section: devel
Maintainer: Distro Developers <distro-devel-discuss@lists.distro.com>
Architecture: amd64
Uncompressed Size: 51,2 k
Depends: cpp (= 4:9.3.0-1distro2), gcc-9 (>= 9.3.0-3~)
Recommends: libc6-dev | libc-dev
Suggests: gcc-multilib, make, manpages-dev, autoconf, automake, libtool, flex, bison, gdb, gcc-doc
Conflicts: gcc-doc (< 1:2.95.3), gcc-doc:i386 (< 1:2.95.3), gcc:i386
Provides: c-compiler, gcc-x86-64-linux-gnu (= 4:9.3.0-1distro2), gcc:amd64 (= 4:9.3.0-1distro2)
Description: GNU C compiler
 This is the GNU C compiler, a fairly portable optimizing compiler for C. 
 
 This is a dependency package providing the default GNU C compiler.

"""))
    def test_show__all_attributes(self, execute: Mock):
        info = self.aptitude.show(('firefox', 'gcc'))
        execute.assert_called_once_with('aptitude show -q firefox gcc', shell=True,
                                        custom_env={**system.gen_env(global_interpreter=system.USE_GLOBAL_INTERPRETER,
                                                                     lang=''), 'LC_NUMERIC': ''})

        expected = {
            'firefox': {
                'version': '97.0+distro1+una',
                'state': ('installed (95.0.1+distro1.1+una)', 'upgrade available (97.0+distro1+una)'),
                'automatically installed': 'no',
                'priority': 'optional',
                'section': 'web',
                'maintainer': 'Distro Dev <root@distro.com>',
                'architecture': 'amd64',
                'uncompressed size': 236000000,
                'predepends': ('distro-system-adjustments (>= 2021.12.16)', ),
                'breaks': ('firefox-dbg (< 95.0.1+distro1+una)', 'firefox-dev (< 95.0.1+distro1+una)',
                           'firefox-geckodriver (< 95.0.1+distro1+una)', 'firefox-mozsymbols (< 95.0.1+distro1+una)'),
                'replaces': ('firefox-dbg (< 95.0.1+distro1+una)', 'firefox-dev (< 95.0.1+distro1+una)',
                             'firefox-geckodriver (< 95.0.1+distro1+una)', 'firefox-mozsymbols (< 95.0.1+distro1+una)'),
                'provides': ('gnome-www-browser', 'www-browser'),
                'description': 'The Firefox web browser'
            },
            'gcc': {
                'version': '4:9.3.0-1distro2',
                'state': ('installed', ),
                'automatically installed': 'no',
                'priority': 'optional',
                'section': 'devel',
                'maintainer': 'Distro Developers <distro-devel-discuss@lists.distro.com>',
                'architecture': 'amd64',
                'uncompressed size': 51200,
                'depends': ('cpp (= 4:9.3.0-1distro2)', 'gcc-9 (>= 9.3.0-3~)'),
                'recommends': ('libc6-dev | libc-dev', ),
                'suggests': ('gcc-multilib', 'make', 'manpages-dev', 'autoconf', 'automake',
                             'libtool', 'flex', 'bison', 'gdb', 'gcc-doc'),
                'conflicts': ('gcc-doc (< 1:2.95.3)', 'gcc-doc:i386 (< 1:2.95.3)', 'gcc:i386'),
                'provides': ('c-compiler', 'gcc-x86-64-linux-gnu (= 4:9.3.0-1distro2)', 'gcc:amd64 (= 4:9.3.0-1distro2)'),
                'description': 'GNU C compiler'
            }
        }

        self.assertEqual(expected, info)

    @patch(f'{__app_name__}.gems.debian.aptitude.system.execute', return_value=(0, """
        gir1.2-javascriptcoregtk-4.0^2.34.1-0distro0.20.04.1^2.34.4-0distro0.20.04.1^Distro Developers <distro-devel-discuss@lists.distro.com>^library^JavaScript engine library from WebKitGTK - GObject introspection data
        gir1.2-nm-1.0^1.22.10-1distro2.2^1.22.10-1distro2.3^Distro Developers <distro-devel-discuss@lists.distro.com>^library^GObject introspection data for the libnm library
        xwayland^2:1.20.13-1distro1~20.04.2^2:1.20.13-1distro1~20.04.2^Distro X-SWAT <distro-x@lists.distro.com>^X11^Xwayland X server
        """))
    def test_read_installed__with_updates_available(self, execute: Mock):
        returned = [p for p in self.aptitude.read_installed()]
        execute.assert_called_once()

        expected = [DebianPackage(name='gir1.2-javascriptcoregtk-4.0', version='2.34.1-0distro0.20.04.1',
                                  latest_version='2.34.4-0distro0.20.04.1',
                                  maintainer='Distro Developers', update=True, installed=True,
                                  categories=('library',),
                                  description='JavaScript engine library from WebKitGTK - GObject introspection data'),
                    DebianPackage(name='gir1.2-nm-1.0', version='1.22.10-1distro2.2',
                                  latest_version='1.22.10-1distro2.3',
                                  maintainer='Distro Developers', update=True, installed=True,
                                  categories=('library',),
                                  description='GObject introspection data for the libnm library'),
                    DebianPackage(name='xwayland', version='2:1.20.13-1distro1~20.04.2',
                                  latest_version='2:1.20.13-1distro1~20.04.2',
                                  maintainer='Distro X-SWAT', update=False, installed=True,
                                  categories=('X11',),
                                  description='Xwayland X server')
                    ]

        self.assertEqual([p.__dict__ for p in expected], [p.__dict__ for p in returned])

    def test_map_transaction_output__it_should_map_i386_packages(self):
        output = "\nThe following NEW packages will be installed:\n" \
                 " gcc-12-base:i386{a} [12.1.0-2distro~22.04] <+272 kB>  glib-networking:i386{a} [2.72.0-1] <+242 kB>\n" \
                "\nThe following packages will be REMOVED:\n" \
                 " celluloid{a} [0.21-linux+distro] <-1066 kB> libpcre3:i386{a} [2:8.39-13distro0.22.04.1] <-714 kB>"

        transaction = self.aptitude.map_transaction_output(output)
        to_install = {
            DebianPackage(name="gcc-12-base:i386",
                          version="12.1.0-2distro~22.04",
                          latest_version="12.1.0-2distro~22.04",
                          transaction_size=272000.0
                          ),
            DebianPackage(name="glib-networking:i386", version="2.72.0-1",
                          latest_version="2.72.0-1", transaction_size=242000.0)
        }
        self.assertEqual(to_install, {*transaction.to_install})

        to_remove = {
            DebianPackage(name="celluloid",
                          version="0.21-linux+distro",
                          latest_version="0.21-linux+distro",
                          transaction_size=-1066000.0
                          ),
            DebianPackage(name="libpcre3:i386", version="2:8.39-13distro0.22.04.1",
                          latest_version="2:8.39-13distro0.22.04.1", transaction_size=-714000.0)
        }

        self.assertEqual(to_remove, {*transaction.to_remove})
