# Changelog
All notable changes to this project will be documented in this file.


The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.6.2] 2019-09-
### Improvements
- Installed files of AUR packages available in the Info window
- Update notifications showing the number of updates by type as well
- Improving Arch distro checking

### Fixes
- Update-check daemon not showing notifications

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
