from unittest import TestCase

from bauh.gems.flatpak.worker import FlatpakAsyncDataLoader


class FlatpakAsyncDataLoaderTest(TestCase):

    def test_format_category(self):
        self.assertEqual('irc client', FlatpakAsyncDataLoader.format_category('IRCClient'))
        self.assertEqual('text editor', FlatpakAsyncDataLoader.format_category('TextEditor'))
        self.assertEqual('text editor', FlatpakAsyncDataLoader.format_category('Text Editor'))
        self.assertEqual('text editor', FlatpakAsyncDataLoader.format_category('text editor'))
        self.assertEqual('text editor', FlatpakAsyncDataLoader.format_category('Text editor'))
        self.assertEqual('text editor', FlatpakAsyncDataLoader.format_category('text Editor'))
        self.assertEqual('text editor', FlatpakAsyncDataLoader.format_category('textEditor'))
        self.assertEqual('ide', FlatpakAsyncDataLoader.format_category('IDE'))
        self.assertEqual('faster irc client', FlatpakAsyncDataLoader.format_category('Faster IRCClient'))
        self.assertEqual('3d graphics', FlatpakAsyncDataLoader.format_category('3DGraphics'))
        self.assertEqual('32d graphics', FlatpakAsyncDataLoader.format_category('32DGraphics'))
        self.assertEqual('d32 graphics', FlatpakAsyncDataLoader.format_category('D32Graphics'))
