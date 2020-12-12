from unittest import TestCase

from bauh.gems.appimage.util import replace_desktop_entry_exec_command


class TestUtil(TestCase):

    def test_replace_desktop_entry_exec_command__only_one_exec_field_no_spaces_and_no_params(self):
        desktop_entry = """
        Name=MyApp
        Icon=MyApp
        Exec=myapp
        """

        res = replace_desktop_entry_exec_command(desktop_entry=desktop_entry,
                                                 appname='myapp',
                                                 file_path='/path/to/myapp.appimage')

        expected = """
        Name=MyApp
        Icon=MyApp
        Exec="/path/to/myapp.appimage"
        """

        self.assertEqual(expected, res)

    def test_replace_desktop_entry_exec_command__only_one_exec_field_command_with_different_cases(self):
        desktop_entry = """
        Name=MyApp
        Icon=MyApp
        Exec=MyApP
        """

        res = replace_desktop_entry_exec_command(desktop_entry=desktop_entry,
                                                 appname='myapp',
                                                 file_path='/path/to/myapp.appimage')

        expected = """
        Name=MyApp
        Icon=MyApp
        Exec="/path/to/myapp.appimage"
        """

        self.assertEqual(expected, res)

    def test_replace_desktop_entry_exec_command__only_one_exec_field_no_spaces_and_params(self):
        desktop_entry = """
        Name=MyApp
        Icon=MyApp
        Exec=myapp %f
        """

        res = replace_desktop_entry_exec_command(desktop_entry=desktop_entry,
                                                 appname='myapp',
                                                 file_path='/path/to/myapp.appimage')

        expected = """
        Name=MyApp
        Icon=MyApp
        Exec="/path/to/myapp.appimage" %f
        """

        self.assertEqual(expected, res)

    def test_replace_desktop_entry_exec_command__only_one_exec_field_no_line_jump_in_the_end(self):
        desktop_entry = """
        Name=MyApp
        Icon=MyApp
        Exec=myapp %f"""

        res = replace_desktop_entry_exec_command(desktop_entry=desktop_entry,
                                                 appname='myapp',
                                                 file_path='/path/to/myapp.appimage')

        expected = """
        Name=MyApp
        Icon=MyApp
        Exec="/path/to/myapp.appimage" %f"""

        self.assertEqual(expected, res)

    def test_replace_desktop_entry_exec_command__only_one_exec_field_with_spaces_and_params(self):
        desktop_entry = """
        Name=MyApp
        Icon=MyApp
        Exec =  myapp %f --a
        """

        res = replace_desktop_entry_exec_command(desktop_entry=desktop_entry,
                                                 appname='myapp',
                                                 file_path='/path/to/myapp.appimage')

        expected = """
        Name=MyApp
        Icon=MyApp
        Exec ="/path/to/myapp.appimage" %f --a
        """

        self.assertEqual(expected, res)

    def test_replace_desktop_entry_exec_command__param_with_the_same_app_name(self):
        desktop_entry = """
        Name=MyApp
        Icon=MyApp
        Exec=myapp %f --myapp
        """

        res = replace_desktop_entry_exec_command(desktop_entry=desktop_entry,
                                                 appname='myapp',
                                                 file_path='/path/to/myapp.appimage')

        expected = """
        Name=MyApp
        Icon=MyApp
        Exec="/path/to/myapp.appimage" %f --myapp
        """

        self.assertEqual(expected, res)

    def test_replace_desktop_entry_exec_command__evvar_with_same_app_name(self):
        desktop_entry = """
        Name=MyApp
        Icon=MyApp
        Exec=MYAPP=123 myapp
        """

        res = replace_desktop_entry_exec_command(desktop_entry=desktop_entry,
                                                 appname='myapp',
                                                 file_path='/path/to/myapp.appimage')

        expected = """
        Name=MyApp
        Icon=MyApp
        Exec=MYAPP=123 "/path/to/myapp.appimage"
        """

        self.assertEqual(expected, res)

    def test_replace_desktop_entry_exec_command__only_one_tryexec_field_with_spaces_and_params(self):
        desktop_entry = """
        Name=MyApp
        Icon=MyApp
        TryExec =  myapp %f --a
        """

        res = replace_desktop_entry_exec_command(desktop_entry=desktop_entry,
                                                 appname='myapp',
                                                 file_path='/path/to/myapp.appimage')

        expected = """
        Name=MyApp
        Icon=MyApp
        TryExec ="/path/to/myapp.appimage" %f --a
        """

        self.assertEqual(expected, res)

    def test_replace_desktop_entry_exec_command__exec_and_tryexec_fields(self):
        desktop_entry = """
        Name=MyApp
        Icon=MyApp
        TryExec =  myapp %f
        Exec=myapp --a
        Terminal=false
        """

        res = replace_desktop_entry_exec_command(desktop_entry=desktop_entry,
                                                 appname='myapp',
                                                 file_path='/path/to/myapp.appimage')

        expected = """
        Name=MyApp
        Icon=MyApp
        TryExec ="/path/to/myapp.appimage" %f
        Exec="/path/to/myapp.appimage" --a
        Terminal=false
        """

        self.assertEqual(expected, res)

    def test_replace_desktop_entry_exec_command__exec_and_tryexec_fields_with_envvars_and_params(self):
        desktop_entry = """
        Name=MyApp
        Icon=MyApp
        TryExec=__MY_VAR=1 myapp %f
        Exec=NEW_VAR=abc myapp --a
        Terminal=false
        """

        res = replace_desktop_entry_exec_command(desktop_entry=desktop_entry,
                                                 appname='myapp',
                                                 file_path='/path/to/myapp.appimage')

        expected = """
        Name=MyApp
        Icon=MyApp
        TryExec=__MY_VAR=1 "/path/to/myapp.appimage" %f
        Exec=NEW_VAR=abc "/path/to/myapp.appimage" --a
        Terminal=false
        """

        self.assertEqual(expected, res)

    def test_replace_desktop_entry_exec_command__rpcs3(self):
        desktop_entry = """
        [Desktop Entry]
Type=Application
Name=RPCS3
GenericName=PlayStation 3 Emulator
Comment=An open-source PlayStation 3 emulator/debugger written in C++.
Icon=rpcs3
TryExec=rpcs3
Exec=rpcs3 %f
Terminal=false
Categories=Game;Emulator;
Keywords=PS3;Playstation;

        """

        res = replace_desktop_entry_exec_command(desktop_entry=desktop_entry,
                                                 appname='rpcs3',
                                                 file_path='/path/to/rpcs3.appimage')

        expected = """
        [Desktop Entry]
Type=Application
Name=RPCS3
GenericName=PlayStation 3 Emulator
Comment=An open-source PlayStation 3 emulator/debugger written in C++.
Icon=rpcs3
TryExec="/path/to/rpcs3.appimage"
Exec="/path/to/rpcs3.appimage" %f
Terminal=false
Categories=Game;Emulator;
Keywords=PS3;Playstation;

        """

        self.assertEqual(expected, res)

    def test_replace_desktop_entry_exec_command__it_should_replace_the_command_by_the_file_path_if_the_appname_is_not_present(self):
        desktop_entry = """
        [Desktop Entry]
Name=GameHub
GenericName=GameHub
Comment=All your games in one place
Categories=Game;Amusement;
Keywords=Game;Hub;Steam;GOG;Humble;HumbleBundle;
Exec=com.github.tkashkin.gamehub
X-GNOME-Gettext-Domain=com.github.tkashkin.gamehub
Icon=/gamehub-0/logo.svg
Terminal=false
Type=Application
X-AppImage-Version=bionic-0.16.0-83-dev-0ca783e
        """

        res = replace_desktop_entry_exec_command(desktop_entry=desktop_entry,
                                                 appname='gamehub',
                                                 file_path='/path/to/gamehub.appimage')

        expected =  """
        [Desktop Entry]
Name=GameHub
GenericName=GameHub
Comment=All your games in one place
Categories=Game;Amusement;
Keywords=Game;Hub;Steam;GOG;Humble;HumbleBundle;
Exec="/path/to/gamehub.appimage"
X-GNOME-Gettext-Domain=com.github.tkashkin.gamehub
Icon=/gamehub-0/logo.svg
Terminal=false
Type=Application
X-AppImage-Version=bionic-0.16.0-83-dev-0ca783e
        """

        self.assertEqual(expected, res)
