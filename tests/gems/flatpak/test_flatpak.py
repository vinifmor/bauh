from unittest import TestCase
from unittest.mock import patch, Mock

from bauh import __app_name__
from bauh.gems.flatpak import flatpak, VERSION_1_2


class FlatpakTest(TestCase):

    @patch(f'{__app_name__}.gems.flatpak.flatpak.SimpleProcess')
    @patch(f'{__app_name__}.gems.flatpak.flatpak.ProcessHandler.handle_simple', return_value=(True, """
    Looking for updates...
    
    \tID\tArch\tBranch\tRemote\tDownload
    1.\t \torg.xpto.Xnote\tx86_64\tstable\tflathub\t< 4.3 MB
    
    """))
    def test_map_update_download_size__for_flatpak_1_2(self, SimpleProcess: Mock, handle_simple: Mock):
        download_size = flatpak.map_update_download_size(app_ids={'org.xpto.Xnote'}, installation='user', version=VERSION_1_2)
        SimpleProcess.assert_called_once()
        handle_simple.assert_called_once()

        self.assertEqual({'org.xpto.Xnote': 4300000}, download_size)
