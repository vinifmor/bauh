# Changelog
All notable changes to this project will be documented in this file.


The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.6.0] 2019-09-
### Features
- Supporting AUR packages (install, uninstall, search, info, downgrade and history)
- Now it is possible to enable / disable the packaging technologies via graphical interface using the "Application types" action in the lower "Settings" menu
- Qt style / theme combo selector ( environment variable / parameter BAUH_THEME (--theme) removed )
- New "Launch" button: can launch application packages
- New "Installed" button: quickly retrieves the installed packages without a full refresh ( available after a search )
- Publisher / maintainer column in the packages table
- "Application settings" button located in right lower corner
- Package "Name" filter field (above the packages table)
- Showing the number of packages being shown by the total found

### Improvements:
- Reading installed Snaps now takes around 95% less time
- Reading installed Flatpaks now takes around 45% less time
- Refreshing only the associated package type after a successful operation (install, uninstall, downgrade, ...)
- Progress bar status can now be controlled by the software manager while an operation is being executed
- Flatpak: showing runtime branches as versions when they are not available

### UI Changes
- "Upgrade selected" and "Refresh" buttons now have text labels and new colors
- Updates warning icon removed
- Progress bar height reduced
- Packaging type checkbox filters replaced by a combo box (single select)
- Search bar resized

### Fixes:
- cached Flatpak app current version

### Code
- Code was internally modularized as: "api" (conceptual classes used to create custom software managers), "gems" (software managers), "commons" (common classes shared between the UI and "gems")
- "gems" modules requires only "api" (no UI code)
- "api" allows custom operations, so the "gems" can provide actions that the current GUI does not know (Snap "refresh" was refactored as a custom operation)


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