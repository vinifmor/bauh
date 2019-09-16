# Changelog
All notable changes to this project will be documented in this file.


The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.6.0]
### Features
- Theme / style selector via UI (environment variable / parameter BAUH_THEME (--theme) removed)
- New "Installed" button: quickly retrieves the installed packages without a full refresh

### Improvements:
- Reading installed Snaps now takes around 95% less time.
- Reading installed Flatpaks now takes around 45% less time.

### Fixes:
- cached Flatpak app current version


## [0.5.2] 2019-09-06
### Features
- New environment variable / parameter to set a custom QT theme for the application: BAUH_THEME (--theme)
### Fixes
- wrong management panel resizing for some scenarios
- bad application theme when fusion or breeze are not set as default QT theme / style

## [0.5.1] - 2019-08-12
### Improvements:
- suggestions are now retrieved asynchronously taking 45% less time.
- search response takes an average of 20% less time ( reaching 35% for several results )
- app boot takes 98% less time when snapd is installed, but disabled
- BAUH_TRAY (--tray) is not enabled by default (0).
### Fixes
- not showing correctly the latest flatpak app versions when bringing the search results
- flatpak client dependency