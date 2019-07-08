# Changelog
All notable changes to this project will be documented in this file.


The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.3.1]
### Improvements
- Console output now is optional and now shown by default.
- Full Flatpak database is not loaded during initialization (management panel is quickly available for the user)
- Applications data that must be retrieved from Flathub API are now retrieved on demand and cached
- Cache cleaners (for icons and API data) to improve memory usage.
- New environment variable and argument: FPAKMAN_ICON_EXPIRATION ('--icon-exp')
- Code was refactored to support other types of packaging

## [0.3.0] - 2019-07-02
### Features
- Applications search
- Now when you right-click a selected application you can:
    - retrieve its information
    - retrieve its commit history
    - downgrade
    - install and uninstall it
- "About" window available when right-clicking the tray icon.

### Improvements
- Performance and memory usage
- Adding tooltips to toolbar buttons
- "Update ?" column renamed to "Upgrade ?"
- Management panel title renamed
- Showing runtime apps when no app is available
- Allowing to specify a custom app translation with the environment variable **FPAKMAN_LOCALE**
- Adding expiration time for cached app data. Default to 1 hour. The environment variable **FPAKMAN_CACHE_EXPIRATION** can change this value.
- Now the application accepts arguments related to environment variables as well. Check 'README.md'.
- Minor GUI improvements
- Notifying only new updates
- New icon
- Progress bar

## [0.2.1] - 2019-06-24
### Features
- Showing the number of apps and runtime updates available
### Fixes
- Retrieving information for the same AppId from different branches.

## [0.2.0] - 2019-06-18
### Features
- Management panel shows update commands streams
- Management panel status label is "orange" now

### Fixes
- Application name is not properly showing for Flatpak 1.2.X

## [0.1.0] - 2019-06-14
### Features
- System tray icon.
- Applications management window.
- Support for the following locales: PT, EN, ES.
- System notification for new updates.
- Update applications.
