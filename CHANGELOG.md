# Changelog
All notable changes to this project will be documented in this file.


The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.7.1] 2019-10-25
### Features
- Snap:
    - if the **stable** channel is not available while an application is being installed, a popup is displayed allowing the user to choose a different one ( e.g: dbeaver-ce )

### Improvements
- 3 password attempts for root authentication
- not changing the table applied filters after a uninstall
- cleaning the progress bar substatus after each upgrade
- sorted categories
- AppImage:
    - showing an error popup when **AppImageLauncher** messes up with an application installation
- Flatpak:
    - Runtimes now are categorized as "runtime"
    - Formatting the API categories to the same format provided by the other packaging technologies
- AUR:
    - showing a "user-friendly" popup when there are integrity issues with the source-files of a building package
    - not waiting for the categories file to be retrieved from the cloud during application boot ( reduces boot time )
    - caching cloud categories to the disk so they can be used in scenarios when it is not possible to retrieve them ( e.g: internet is off )
    - mapping known search key words to the specific package name ( e.g:"google chrome" will become "google-chrome" )
- Snap:
    - not waiting for the categories file to be retrieved from the cloud during application boot ( reduces boot time )
    - caching cloud categories to the disk so they can be used in scenarios when it is not possible to retrieve them ( e.g: internet is off )
    - showing a warning popup when the Snap API is out
    - Snaps not treated as applications with be categorized as "runtime" at least
- minor thread improvements

### UI
- Screenshots panel:
    - "downloading" label replaced by a progress bar
    
### Fixes
- application not initializing when there is no internet connection
- not loading application icons after some filters are applied to the table results
- not reloading the available categories after asynchronous data is fetched
- not keeping the update toggle-button state after a filter is applied
- AUR:
    - update-checking for some scenarios
    - not respecting **ignorepkg** settings in **pacman.conf**
    - not able to handle **missing dependencies with symbols** ( e.g: libpng++ )
    - not able to work with **.xpm** icons
    - not mapping categories to the search results

## [0.7.0] 2019-10-18
### Features
- AppImage support ( see below )
- **Screenshots** button and panel
- **Categories** filter

### Improvements
- Flatpak:
    - History panel now shows formatted dates
    - Info available for not installed applications
- Snap:
    - Improved how the the application verification is done ( if a given Snap is an application )
- AUR:
    - Optional dependencies are not checked by default in their installation popup.
- History panel can now me maximized, minimized and allows to copy column content.
- It is possible to use custom tray icons via the environment variables: **BAUH_TRAY_DEFAULT_ICON_PATH** and **BAUH_TRAY_UPDATES_ICON_PATH** ( displayed when there are updates )
- Minor UI improvements

### Fixes
- cache thread lock that was eventually hanging the application
- Flatpak:
    - Runtimes update-checking for version 1.5.X
- Snap:
    - retrieving installed applications information for Ubuntu based distros
- Application icon replaced by the type icon in the Info, History and Screenshots panels due to unexpected Qt crashes
- minor UI fixes

### AppImage support
- Search, install, uninstall, downgrade, launch and retrieve the applications history
- Supported sources: [AppImageHub](https://appimage.github.io) ( **applications with no releases published to GitHub are currently not available** )
- Adds desktop entries ( menu shortcuts ) for the installed applications ( **~/.local/share/applications**)

## [0.6.4] 2019-10-13
### Fixes
- Flatpak update-checking for version 1.5.X

## [0.6.3] 2019-10-11
### Fixes
- AUR update check for some scenarios
- table not showing some update versions due to a strange Python String comparison behavior ( e.g: the string version '0.1.90' is being handled as higher than '0.1.120' )

## [0.6.2] 2019-10-02
### Improvements
- Update notifications showing the number of updates by type as well ( if they are from more than one packaging type )
- Snap:
    - **Installed** info field split into **version** and **size**
- AUR:
    - Installed files available in the Info window
    - Improving Arch distro checking

### Fixes
- Update-check daemon not showing notifications
- Not retrieving the system default locale to translate the application texts
- Not updating translations when the default locale is different from 'en'
- Installed button available after a recent installation if a new search is done
- Flatpak:
    - error when retrieving information ( Flatpak 1.0.X )
- Snap:
    - apps with commands different from their names do not launch
- AUR:
    - not ignoring downgrade warnings for different locales

## [0.6.1] 2019-09-26
### Improvements
- Better warning presentation when there are several messages
- Better AUR update check handling
- "Show" button available for all information fields

### Fixes
- Error when retrieving suggestions
- snapd health check when snapd.service is available
- AUR: not showing all optional dependencies ( Info )


## [0.6.0] 2019-09-25
### Features
- Supporting **AUR** packages ( see below )
- Now it is possible to enable / disable the packaging technologies via graphical interface using the **Application types** action in the lower **Settings** button
- Environment variables / parameters **BAUH_FLATPAK (--flatpak)** and **BAUH_SNAP (--snap)** removed in favor of the feature above
- Qt style / theme combo selector ( environment variable / parameter **BAUH_THEME (--theme)** removed )
- New **Launch button**: can launch application packages
- New **Installed button**: quickly retrieves the installed packages without a full refresh ( available after a search )
- Publisher / maintainer column in the packages table
- **Extra actions** button located in right lower corner
- Package "Name" filter field ( above the packages table )
- Showing the number of packages being shown by the total found in the right lower corner
- **Show button** for large fields in the **Info** window

### Improvements
- Reading installed Snaps now takes around 95% less time
- Reading Snap suggestions now takes around 75% less time
- Reading installed Flatpaks now takes around 45% less time
- "snap" and "snapd" installation check response time reduced
- Refreshing only the associated package type after a successful operation (uninstall, downgrade, ...) ( **installation** has a different treatment. See below )
- Only the installed package is displayed after a successful installation
- Progress bar status can now be controlled by the software manager (gem) while an operation is being executed
- Flatpak: showing runtime branches as versions when they are not available
- better internet offline handling
- installation logs are saved at **/tmp/bauh/logs/install**
- Environment variable / parameter **BAUH_UPDATE_NOTIFICATION** renamed to **BAUH_SYSTEM_NOTIFICATIONS** and now works for any system notification
- Environment variable / parameter **BAUH_DOWNLOAD_MULTITHREAD**: if source files should be downloaded using multi-threads (not supported by all **gems**).
- Environment variables / parameter **BAUH_MAX_DISPLAYED**: controls the maximum number of displayed apps ( default to 50 )
- Environment variables / parameter **BAUH_LOGS**: activates console logging.
- small UI improvements

### UI Changes
- **Upgrade selected** and **Refresh** buttons now have text labels and new colors
- Updates warning icon removed
- Progress bar height reduced
- Packaging type checkbox filters replaced by a combo box (single select)
- Search bar resized

### Fixes
- flatpak: cached app current version
- flatpak: update notification for runtimes with the same name
- flatpak: some warnings are treated as errors after downgrading
- disk loader not filling all requested cached data from the disk
- Ubuntu root password check
- [Ubuntu 19.04 pip3 install issue](https://github.com/vinifmor/bauh/issues/3)

### AUR support (**arch gem**):
- Search, install, uninstall, downgrade, retrieve history and launch packages
- Faster source files downloads improving installation speed ( see **README.md** for more information )
- Automatically improves package compilations ( see **README.md** for more information )

### Code
- Code was internally modularized as: **api** (conceptual classes used to create custom software managers or **gems**), **gems** (software managers), **commons** (common classes shared among the **view** and **gems**), **view** (UI code)
- **api** allows custom operations so the **gems** can provide actions that the current GUI does not support (Snap "refresh" was refactored as a custom operation)

### Comments
- the application settings are stored in **~/.config/bauh/config.json**


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
