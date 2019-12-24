# Changelog
All notable changes to this project will be documented in this file.


The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.8.0] 2019-12-24
### Features
- Native Web applications support:
    - if an URL is typed in the search bar, a native web application result will be displayed in the results table.
    - bauh relies on [NodeJS](https://nodejs.org/en/), [Electron](https://electronjs.org/) and [nativefier](https://github.com/jiahaog/nativefier) to install the Web applications, but there is no need to have them installed on your system. Bauh will create its own installation environment with these technologies in **~/.local/share/bauh/web/env**.
    - suggestions are retrieved from [suggestions.txt](https://github.com/vinifmor/bauh-files/blob/master/web/suggestions.yml)
    - requires only **python-beautifulsoup4** and **python-lxml** to be enabled
- **Suggestions** button: it shows some application suggestions 

### Improvements
- configuration file **~/.config/bauh/config.json** renamed to **~/.config/bauh/config.yml**
- some parameters and environment variables were moved to the configuration file ( **~/.config/bauh/config.yml** )
```
disk_cache:  # old '--disk_cache'
  enabled: true
download:
  icons: true # old '--download-icons'
  multithreaded: true  # old '--download-mthread'
gems: null 
locale: null  # old '--locale'
memory_cache:
  data_expiration: 3600 # old '--cache-exp'
  icon_expiration: 300  # old '--icon-exp'
suggestions:
  by_type: 10  # new -> defines the max number of suggestions by package type
  enabled: true  # old '--sugs'
system:
  notifications: true  # old '--system-notifications'
  single_dependency_checking: false  # old '---check-packaging-once'
ui:
  style: null  
  table:
    max_displayed: 50  # old '--max-displayed'
  tray:
    default_icon: null  # old environment variable 'BAUH_TRAY_DEFAULT_ICON_PATH'
    updates_icon: null  # old environment variable 'BAUH_TRAY_UPDATES_ICON_PATH'
updates:
  check_interval: 30  # old '--check-interval'

```
- The default update checking interval is now 30 seconds
- New tray icons loading priority: 
    1) Icon paths defined in **~/.config/bauh/config.yml**
    2) Icons from the system with the following names: `bauh_tray_default` and `bauh_tray_updates`
    3) Own packaged icons
- Now bauh considers the default system icon for the notifications and panel. If there is none, then it will use its own.
- AppImage:
    - cleaning the downloaded database files when **--reset** is passed as parameter
    - environment variables **BAUH_APPIMAGE_DB_UPDATER** and **BAUH_APPIMAGE_DB_UPDATER_TIME** dropped in favor of the new configuration file located at **~/.config/bauh/appimage.yml**
    - suggestions are now retrieved from [suggestions.txt](https://github.com/vinifmor/bauh-files/blob/master/appimage/suggestions.txt)
- AUR:
    - The AUR indexer daemon is not running every 20 minutes anymore. It will only run during the boot, and will generate the optimized index
    at **/tmp/bauh/arch/aur.txt**. This new behavior does not harm the current experience, and reduces memory usage. More information about this behavior in [README](https://github.com/vinifmor/bauh/blob/master/README.md).
    - Environment variable **BAUH_ARCH_AUR_INDEX_UPDATER** dropped in favor of the behavior described above.
    - Environment variables **BAUH_ARCH_OPTIMIZE** and **BAUH_ARCH_CHECK_SUBDEPS** dropped in favor of the new configuration file located at **~/.config/bauh/arch.yml**
    - suggestions are now retrieved from [suggestions.txt](https://github.com/vinifmor/bauh-files/blob/master/aur/suggestions.txt)  
- Flatpak:
    - suggestions are now retrieved from [suggestions.txt](https://github.com/vinifmor/bauh-files/blob/master/flatpak/suggestions.txt)
- Snap:
    - suggestions are now retrieved from [suggestions.txt](https://github.com/vinifmor/bauh-files/blob/master/snap/suggestions.txt)
  
- Minor memory improvements
- Minor UI improvements

### Fixes
- AUR:
    - an exception happens when retrieving matches from the cached AUR index
    - not using the optimized compilation settings if the custom makepkg file is not found during the installation process
- minor fixes

## [0.7.5] 2019-12-20
### Fixes
- Fix missing i18n keys when there are no mapped translations for the system's default locale [#40](https://github.com/vinifmor/bauh/issues/40)
- Tray icon is not updating its status after an application is uninstalled

## [0.7.4] 2019-12-09
### Improvements
- AUR
    - retrieving and displaying all transitive required dependencies ( it can be disabled via the new environment variable **BAUH_ARCH_CHECK_SUBDEPS=0** )
    - displaying **makedepends** and **checkdepends** in the info window
    - Some AUR labels have been changed to not confuse the user
- **--clean** param renamed to **--reset**
- Minor UI improvements

### Fixes
- AUR
    - not finding some dependencies declared as files instead of the package names (e.g: dolphin-emu-git )
    - replaces the term **mirror** by **repository**
    

## [0.7.3] 2019-11-29
### Improvements
- Not breaking the application when a i18n (translation) key was not found
- Adding all english (**en**) i18n keys to help people with the application translation
- AppImage
    - AppImage updater daemon replaced by a default Python thread to reduce memory usage
- AUR
    - The optimized **makepkg.conf** file is now generated at **~/.config/bauh/arch/makepkg.conf** and passed as a parameter during package builds to not provoke the auto-merge of **/etc/makepkg.conf** and the old generated **~/.makepkg.conf**.
    (P.S: if your **~/.makepkg.conf** was generated by bauh, consider deleting it as it will be useless for bauh now and may impact your other Arch compilation tools). Behavior discussed in [#30](https://github.com/vinifmor/bauh/issues/30).
    - Removing an unnecessary **prepare** step executed during dependency checking reducing the packages installation time. Also this step was preventing some packages to install due to its repeated execution ( e.g: xdman )
    - Now AUR packages are enabled by default, but a warning is displayed in the installation dialog
    - New package suggestions
- Caching Snap and Flatpak suggestions [#23](https://github.com/vinifmor/bauh/issues/23)
- i18n:
    - Catalan contributions by [fitojb](https://github.com/fitojb)
    - German contributions by [JonasLoos](https://github.com/JonasLoos)
    - Italian contributions by [albanobattistella](https://github.com/albanobattistella)
- minor UI improvements
    
### Features
- New command line argument to clean the configuration and cache files: `--clean`   
     
### Fixes
- Flatpak
    - Ignoring no related updates ( there are some scenarios the updates are not listed due to warnings / suggestions related to some specific runtimes if the param **--no-related** is not informed )
    
### UI
- AUR
    - Textual dependencies replaced by read-only checkboxes on Required Dependencies confirmation dialog
    - Optional Dependencies installation dialog now has a type icon beside the dependency name

## [0.7.2] 2019-11-01
### Improvements
- Snap
    - not showing **License** in the info window if it defined as **unset**
- Flatpak:
    - "Remotes not set" warning informing to the user that Flatpak support can be disabled  
- showing suggestions if the user changes the application types available and there are no applications installed    
- i18n: spanish contributions by [fitojb](https://github.com/fitojb)
- minor labels improvements

### UI
- Displaying a **verified** green icon next to a verified publisher's name

### Fixes
- Snap
    - The application crashes due to Snap API checking when snap is not installed ( introduced in **0.7.1** )
    

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
