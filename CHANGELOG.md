# Changelog
All notable changes to this project will be documented in this file.


The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.4.3]
### Improvements
- new environment variable / argument to enable / disable the tray icon and update-check daemon: FPAKMAN_TRAY (--tray)
- search results sorting takes an average of 35% less time, reaching 60% in some scenarios
- app boot takes an average of 80% less time
- showing a warning popup after initialization when no Flatpak remotes are set
### Fixes:
- apps table not showing empty descriptions
- replacing default app icons by null icons
- i18n
### Comments:
- not adding Flatpak default remote (flathub) when initializing. It requires root actions, and will be addressed in a different way in future releases.

## [0.4.2] - 2019-07-28
### Improvements
- showing a warning dialog when the application starts and **snapd** is unavailable
### Fixes:
- [Snaps read index error](https://github.com/vinifmor/fpakman/issues/30)

## [0.4.1] - 2019-07-25
### Improvements
- retrieving some Snaps data (icon, description and confinement) through Ubuntu API instead of Snap Store
### Fixes:
- not showing app disk cached description when listing installed apps
- not updating disk cached data of installed apps

## [0.4.0] - 2019-07-25
### Features
- supporting snaps
- search filters by application type and updates
- "Refresh" option when right-clicking an installed snap application (see **Comments**)
- snap / flatpak usage can be enabled / disabled via this new environment variables and arguments: FPAKMAN_FLATPAK (--flatpak), FPAKMAN_SNAP (--snap)
### Improvements
- automatically shows all updates after refreshing
- more accurate search results.
- system notifications when an application is installed, removed or downgraded. Also when an error occurs.
- showing management panel when right-clicking the tray icon.
- "Updates" label replaced by an exclamation icon and moved to the right.
- new environments variables / arguments associated with performance: FPAKMAN_DOWNLOAD_ICONS (--download-icons), FPAKMAN_CHECK_PACKAGING_ONCE (--check-packaging-once)
- minor GUI improvements
### Comments
- currently snap daemon (2.40) automatically upgrades your installed applications in background. Although it's possible to check for new updates
programmatically, it requires root access and would mess up with the user experience if every 5 minutes the application asked for the password. But not to let the
user with empty hands, it was added a "Refresh" option when right-clicking an installed snap application. It will update the application if its not already updated by the daemon.

## [0.3.1] - 2019-07-13
### Improvements
- Console output now is optional and not shown by default
- Search bar is cleaned when 'Refresh' is clicked
- Full Flatpak database is not loaded during initialization: speeds up the process and reduces memory usage
- Applications data not available offline are now retrieved from Flathub API on demand and cached in memory and disk (only installed)
- In-memory cached data have an expiration time and are cleaned overtime to reduce memory usage
- Code was refactored to support other types of packaging in the future (e.g: snap)
- flatpak is not a requirement anymore
- the amount of columns of the applications table was reduced to improve the user experience
- new environment variables and arguments: FPAKMAN_ICON_EXPIRATION (--icon-exp), FPAKMAN_DISK_CACHE (--disk-cache)
- minor GUI improvements

### Fixes:
- flatpak 1.0.X: search is now retrieving the application name
- app crashes when there is no internet connection while initializing, downgrading or retrieving app history

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
