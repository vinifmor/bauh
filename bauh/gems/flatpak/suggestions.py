from bauh.api.abstract.model import SuggestionPriority

ALL = {
    'com.spotify.Client': SuggestionPriority.TOP,
    'com.skype.Client': SuggestionPriority.HIGH,
    'com.dropbox.Client': SuggestionPriority.MEDIUM,
    'us.zoom.Zoom': SuggestionPriority.MEDIUM,
    'org.telegram.desktop': SuggestionPriority.MEDIUM,
    'com.visualstudio.code': SuggestionPriority.LOW,
    'org.inkscape.Inkscape': SuggestionPriority.LOW,
    'org.libretro.RetroArch': SuggestionPriority.LOW,
    'org.kde.kdenlive': SuggestionPriority.LOW,
    'org.videolan.VLC': SuggestionPriority.LOW
}

