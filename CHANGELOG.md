# Changelog
All notable changes to this project will be documented in this file.


The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.9.5] 2020-06-07
### Features
- new custom action (**+**) to open the system backups (snapshots). It is just a shortcut to Timeshift.
    <p align="center">
        <img src="https://raw.githubusercontent.com/vinifmor/bauh/staging/pictures/releases/0.9.5/backup_action.png">
    </p>

### Improvements
- Arch
    - new **automatch_providers** settings: bauh will automatically choose which provider will be used for a package dependency when both names are equal (enabled by default).
    <p align="center">
        <img src="https://raw.githubusercontent.com/vinifmor/bauh/staging/pictures/releases/0.9.5/arch_providers.png">
    </p>

- UI
    - not limiting the name filter size
    - rendering package icons with no full paths declared
    - refreshing custom actions (**+**) after installing/uninstalling/downgrading/upgrading packages
    - minor improvements
- download clients parameters

### Fixes
- regressions (from **0.9.4**)
    - resetting the main configuration when tray mode is active [#118](https://github.com/vinifmor/bauh/issues/118)
    - bauh-cli crashing
    - tray mode not publishing update notifications
    - Arch: not checking if **pacman-mirrors** is available before starting to download repository packages (when multi-threaded download is enabled) [#117](https://github.com/vinifmor/bauh/issues/117)
- Arch
    - uninstall: not checking if there are other installed providers for the target package
    - not recursively asking for dependencies providers when installing / upgrading / downgrading
    - not displaying "removing" substatus during the upgrade process
- UI
    - table overwrite effect when updating its content

### i18n contributions

- Turkish (tr): [tulliana](https://github.com/tulliana)


## [0.9.4] 2020-05-29

### Features
- Ignore updates: now it is possible to ignore updates from software packages through their actions button (**+**). Supported types: Arch packages, Flatpaks and AppImages

    <p align="center">
        <img src="https://raw.githubusercontent.com/vinifmor/bauh/staging/pictures/releases/0.9.4/ignore_updates.png">
    </p>
    <p align="center">
        <img src="https://raw.githubusercontent.com/vinifmor/bauh/staging/pictures/releases/0.9.4/revert_ignored_updates.png">
    </p>
- Packages with ignored updates have their versions displayed with a brown shade
    <p align="center">
        <img src="https://raw.githubusercontent.com/vinifmor/bauh/staging/pictures/releases/0.9.4/version_ignored_updates.png">
    </p>
- It is possible to filter all you packages with updates ignored through the new category **Updates ignored**
    <p align="center">
        <img src="https://raw.githubusercontent.com/vinifmor/bauh/staging/pictures/releases/0.9.4/updates_ignored_category.png">
    </p>
    
- Arch
	- supporting multi-threaded download for repository packages (enabled by default)
    <p align="center">
        <img src="https://raw.githubusercontent.com/vinifmor/bauh/staging/pictures/releases/0.9.4/arch_repo_mthread.png">
    </p>

- Settings
    - [axel](https://github.com/axel-download-accelerator/axel) added as an alternative multi-threaded download tool. The download tool can be defined through the new field **Multi-threaded download tool** on the settings window **Advanced** tab (check **Default** for bauh to decide which one to use)
    <p align="center">
        <img src="https://raw.githubusercontent.com/vinifmor/bauh/staging/pictures/releases/0.9.4/mthread_tool.png">
    </p>



### Improvements
- Arch
    - faster caching data process during initialization
    - i18n
- AppImage
    - Categories are now translated on the Info window
    
- UI
    - only centralizing the apps table after the initialization process
    - defining a minimum width and height based on the screen size
    - info window now has a height limit, a lower bar with Back and Close buttons, and is scrollable
    - minor changes
- Downloads
    - retrieving the downloading file sizes asynchronously

### Fixes
- Flatpak
    - not displaying application updates on the search results
- Arch
    - crashing while reading the installed packages when the internet is unstable

- initialization dialog hangs when there is no task to wait for [#112](https://github.com/vinifmor/bauh/issues/112)
- not caching data of installed packages with no signatures and unknown repositories


## [0.9.3] 2020-05-12
### Features
- new **restore** action to restore all bauh settings and cache through the 'custom actions' button (**+**). It is equivalent to the command `bauh --reset`.

### Improvements
- some custom actions not related to installed packages state will not refresh the table after succeeded

### Fixes
- Arch
    - "clean cache" operation was not working in some scenarios
    - upgrading progress when conflicting files are detected
    - not detecting some installed "not-signed" repository packages
    - not properly caching data of installed dependencies
- UI
    - some fields in the table are overlapped by others when maximized [#107](https://github.com/vinifmor/bauh/issues/107)
    
- upgrade: crashing when there are packages to be displayed on the summary window that cannot upgrade
- settings: crashing when an empty Qt style is detected or defined [#104](https://github.com/vinifmor/bauh/issues/104)


### Recommendations
- Arch-based distro users: clean the bauh's Arch cache after upgrading to this release so it will remap all installed packages during the next initialization. 3 possible ways to do it:

    - type on the command line: `rm -rf ~/.cache/bauh/arch/installed` (it will reset only the Arch cache)
    - type on the command line: `bauh --reset` (it will reset all caches and settings)
    - click on the new **Restore** custom action on the UI (it will reset all caches and settings)


## [0.9.2] 2020-05-04
### Features
- UI
    - it is possible to view details of some initialization tasks by clicking on their icons
    <p align="center">
        <img src="https://raw.githubusercontent.com/vinifmor/bauh/staging/pictures/releases/0.9.2/prepare_icon.png">
    </p>
    <p align="center">
        <img src="https://raw.githubusercontent.com/vinifmor/bauh/staging/pictures/releases/0.9.2/prepare_output.png">
    </p>
    
### Improvements
- Backup
    - new **type** field on settings to specify the Timeshift backup mode: **RSYNC** or **BTRFS**
    <p align="center">
        <img src="https://raw.githubusercontent.com/vinifmor/bauh/staging/pictures/releases/0.9.2/backup_mode.png">
    </p>
- Trim
    - the dialog is now displayed before the upgrading process (but the operation is only executed after a successful upgrade)
- Settings
    - new option to disable the reboot dialog after a successful upgrade (`updates.ask_for_reboot`)
    <p align="center">
        <img src="https://raw.githubusercontent.com/vinifmor/bauh/staging/pictures/releases/0.9.2/ask_reboot.png">
    </p>
- Arch
    - able to handle upgrade scenarios when a package wants to overwrite files of another installed package
    <p align="center">
        <img src="https://raw.githubusercontent.com/vinifmor/bauh/staging/pictures/releases/0.9.2/files_conflict.png">
    </p>
    - displaying more upgrade substatus
    
### Fixes
- Arch
    - file not found error while organizing the data of installed packages [#101](https://github.com/vinifmor/bauh/issues/101)    
- Settings
    - crashing when an unknown Qt style is set [#69](https://github.com/vinifmor/bauh/issues/69)
    
### UI
- icons, buttons and colors changes

<p align="center">
    <img src="https://raw.githubusercontent.com/vinifmor/bauh/staging/pictures/releases/0.9.2/color_design.png">
</p>

- more unnecessary **x** buttons were removed from dialogs
- "click" cursor set for most "clickable" components
- minor improvements
    
### i18n contributors
- Turkish (tr): [tuliana](https://github.com/tulliana)
- Russian (ru): [mountain-biker85](https://github.com/mountain-biker85)

#### Code changes (PullRequest): [#103](https://github.com/vinifmor/bauh/pull/103/files)


## [0.9.1] 2020-04-24
### Features
- Tray
    - displaying a notification when there is a new bauh release
- Arch
    - allowing to uninstall no longer needed packages after a package uninstall [#87](https://github.com/vinifmor/bauh/issues/87)
    
### Improvements
- Internet availability checking code
- Arch
    - displaying if an AUR package was successfully upgraded on the details output [#89](https://github.com/vinifmor/bauh/issues/89)
- Settings
    - **disk.trim_after_update** has changed to **disk.trim.after_upgrade** and accepts 3 possible values: **false** (No): disabled, **true** (Yes): automatically trims, **null** (Ask): displays a confirmation dialog

### Fixes
- Arch
    - not stopping the upgrade process if a transaction error happens
    - search not displaying installed packages that are no longer available on the databases ( e.g: indicator-application )
    - wrong upgrade substatus in some scenarios
    - wrong dialog titles
- AppImage
    - not detecting some updates ( e.g: RPCS3 )
    
### UI
- Changed the main toolbar buttons and custom actions button ('+') styles
- Changed some colors
- Removed the **x** button from some dialogs
    
## [0.9.0] - 2020-04-15
### Features
- Backup
    - Timeshift integration ( if available on the system ): it can generate snapshots before installing, uninstalling, upgrading...
    - you can enable / disable this feature via the settings file or UI.

- UI
    - new initialization dialog showing tasks that need to be done before use
    - new custom actions button ( displays specific action available for each packaging provider )

- Arch
    - supporting packages from configured repositories ( search, install, upgrade and info. **History and downgrade are not supported yet** )
    - custom actions ( available through the new custom actions button )
        - **synchronize packages database**: synchronizes the databases against the configured mirrors
        - **refresh mirrors**: allows the user to define multiple mirrors locations and sort by the fastest
        - **quick system upgrade**: it executes a default pacman upgrade ( `pacman -Syyu --noconfirm` )
        - **clean cache**: it cleans the pacman cache diretory ( default: `/var/cache/pacman/pkg` )
     - mirrors refreshing on startup ( **disabled by default**. Can be enabled on settings -> **refresh_mirrors_startup** )
     - new settings to enable / disable AUR and repository packages management: `aur` and `repositories`
     - uninstall: allowing to remove all transitive dependencies
     - able to handle the installation of dependencies with multiple providers
     - multi-threaded downloads ( using aria2c ) are **not supported yet** for repository packages

- AppImage
    - Custom actions
        - **Install AppImage file**: allows to install a external AppImage file
        - **Upgrade file**: allows to upgrade a manually installed AppImage file
- Web
    - Custom actions
        - **Clean installation environment** custom action: removes all the installation environment folders ( it does not remove installed apps )
    
- CLI mode:
    - a beginning for the command line mode (`bauh-cli`). Only **list updates** command is available for now ( `bauh-cli updates` ) [#54](https://github.com/vinifmor/bauh/issues/54)

- Core
    - allowing to trim the disk after all upgrades are applied ( **disabled by default**. It can be enabled on settings, Make sure your SSD supports TRIM before enabling this option. )
    - new warning dialog informing when there is a new bauh update / release available      
    
### Improvements
- Core
    - root password is asked only once ( can be disabled through the new settings property `store_root_password` )
    - upgrade logs are now generated at **/tmp/bauh/logs/upgrade**
    - new upgrade model: now all packages selected to upgrade are handled at once by the underlying gem
    
- Arch
    - dependency checking algorithm
        - faster for scenarios involving several packages ( taking =~ 95% less time )
        - faster for AUR installations ( taking an average of 23% less time )
    - the AUR compilation optimizations now include setting the device processors to **performance** mode
    - if the pacman database is locked, a dialog is displayed requesting if the database should be unlocked to proceed with the ongoing action
    - displaying missing repository dependencies sizes
    - dialog design when the package cannot be uninstalled due to required packages
    - removing old cached versions from the disk cache when uninstalling a package ( can be disabled on settings -> **clean_cached** )
    - database synchronization on startup ( **enabled by default**. Can be disabled on settings -> **sync_databases_startup** )
    - single pacman call to install repository dependencies
    - improved conflict checking algorithm
    - overall speed improvements
    - code refactoring
- UI
    - the name filter now delays 2 seconds before being applied
    - upgrades: upgrade order and required dialogs were merged in a **single summary dialog**
    - displaying the upgrade size ( Flatpak, AppImage and Arch )
    - time to determine the selected packages to upgrade takes less time
    - table update performance
    - tray
        - treated as an application apart and not sharing the memory with the management panel ( first step to reduce its memory usage )
        - sorting types on update notification 
    
### Fixes
- table not displaying all updates when the "updates filter" is clicked several times
- installation logs written to the wrong temp directory
- crashes when Python is not able to retrieve the default locale [#84](https://github.com/vinifmor/bauh/issues/84)
- Arch / AUR:
    - sorting algorithm was providing wrong results for some cases
    - not caching data about packages with no desktop entry files
    - error output when it was not able to optimize the **makepkg.conf** [#84](https://github.com/vinifmor/bauh/issues/84)
    - error when building AUR packages with **.tar.zst** extensions

### Settings
- Default
    - **pre_dependency_checking** dropped ( now is always enabled )
    - **sort_packages** dropped ( now the gems decide if it makes sense to sort the packages )
    - **disk_cache** dropped ( now is always enabled )
- Arch / AUR:
    - **transitive_checking** dropped ( now is always enabled )
    - **simple_checking** dropped ( now is always disabled )
    
### Params / Environment Variables
- param **--show-panel** dropped
- env vars **BAUH_TRAY** and **BAUH_LOGS** dropped ( the equivalent parameters remain )
- new parameter `--settings`: opens only the settings panel
- now to open the tray use only the parameter `--tray` instead of `--tray=1`
- now to activate the logs use only the parameter `--logs` instead of `--logs=1`
- adding mutual exclusion to some parameters (`--settings`, `--tray`, `--reset`)

### i18n contributions
- Russian (ru): [mountain-biker85](https://github.com/mountain-biker85)

    
## [0.8.5] - 2020-03-11
### Fixes
- Web
    - not able to inject javascript fixes ( WhatsApp Web not working) [#74](https://github.com/vinifmor/bauh/issues/74)
    - not informing StartupWMClass on generated desktop entries ( prevents Gnome to link the Favorite shortcut with the app instance [#76](https://github.com/vinifmor/bauh/issues/76) )
    - some installed apps were not being displayed as installed in the search results
- UI
    - categories filter being displayed during ongoing actions
    - settings: not matching the default system locale with the available options

### Improvements
- AUR
    - preventing the dependencies checking algorithm to add duplicates
- UI
    - error handling when it is not possible to load icon files

### i18n additions / fixes
- Russian ( ru )
    - [leoneii](https://github.com/leoneii) - PRs:  [#66](https://github.com/vinifmor/bauh/pull/66), [#67](https://github.com/vinifmor/bauh/pull/67), [#68](https://github.com/vinifmor/bauh/pull/68)
    - [mountain-biker85](https://github.com/mountain-biker85) - PRs: [#70](https://github.com/vinifmor/bauh/pull/70), [#71](https://github.com/vinifmor/bauh/pull/71), [#72](https://github.com/vinifmor/bauh/pull/72)
- German ( de )
    - [EduardDopler](https://github.com/EduardDopler) - PRs: [#78](https://github.com/vinifmor/bauh/pull/78)

## [0.8.4] - 2020-02-21
### Improvements
- UI
    - treating multiple lines on the application's description displayed on the table
- AUR
    - generating the semantic search map on demand instead of storing it in memory
- Russian translations by: 
    - [leoneii](https://github.com/leoneii) -  PRs: [#61](https://github.com/vinifmor/bauh/pull/61) [#63](https://github.com/vinifmor/bauh/pull/63)
    - [mountain-biker85](https://github.com/mountain-biker85) - PRs: [#62](https://github.com/vinifmor/bauh/pull/62) [#64](https://github.com/vinifmor/bauh/pull/64)
### Fixes
- Snap
    - not able to launch applications on some distros ( e.g: OpenSuse ) [#58](https://github.com/vinifmor/bauh/issues/58)
- AUR
    - package name tooltip was displaying only the repository ( table row )
- UI
    - not displaying some priority search results at the top of the table


## [0.8.3] - 2020-02-13
### Improvements
- New update lifecycle:
    - now every package manager must provide all requirements before upgrading all selected packages ( can be disabled through the settings file **~/.config/bauh/config.yml** or the UI )
    - now every package manager must provide the best upgrade order for all the selected packages ( can be disabled through the settings file **~/.config/bauh/config.yml** or the UI )
- AUR
    - allowing the user to bypass checksum errors when installing / upgrading / downgrading packages
    - improved how missing dependencies are checked when installing a new package ( the old way was not identifying some missing dependencies of **anbox-git** ). It is possible to use the old algorithm by setting **simple_checking** to **true** in **~/.config/bauh/arch.yml**. More information at [README](https://github.com/vinifmor/bauh/#aur--arch-).
    - checking architecture dependencies (x86_64, i686)
    - architecture dependencies are displayed on the info window as well
    - optimizations to speed up zst packages building
    - showing a warning message when trying to install / update / downgrade a package with the root user
- UI:
    - **Settings** available as a tray action as well
    - minor improvements
- the temp dir used now has a different name if you launch bauh as the root user to avoid permissioning issues ( **/tmp/bauh_root** )

### Fixes
- AUR:
    - not able to downgrade some packages with multiple equal versions on their release history
- Web:
    - not able to launch applications for the root user
    - not able to upgrade the environment's NodeJS version
- handling internet timeout errors
- minor fixes
    

## [0.8.2] - 2020-01-31
### Features
- New **Settings** panel ( displayed when the lower **Settings** button is clicked ). It allows to change all settings.

### Improvements
- Flatpak
    - configuration file ( **flatpak.yml** ) will be created during the initialization ( on **0.8.1** it would only be created during the first app installation )
- AUR
    - the custom **makepkg.conf** generated at **~/.config/bauh/arch** will enable **ccache** if available on the system
    - downgrading time reduced due to the fix described in ***Fixes***
    - package databases synchronization once a day ( or every device reboot ) before the first package installation / upgrade / downgrade. This behavior can be disabled on **~/.config/arch.yml** / or the new settings panel
    ```
    sync_databases: true  # enabled by default
    ```
- Configuration ( **~/.config/bauh/config.yml** )
    - new property **hdpi** allowing to disable HDPI improvements
    ```
    ui:
        hdpi: true # enabled by default
    ```
  - new property **auto_scale** activates Qt auto screen scale factor ( **QT_AUTO_SCREEN_SCALE_FACTOR** ). It fixes scaling issues 
    for some desktop environments ( like Gnome ) [#1](https://github.com/vinifmor/bauh/issues/1)
    ```
     ui:
        auto_scale: false  # disabled by default
    ```
### Fixes
- AUR
    - not treating **makedepends** as a list during dependency checking ( **anbox-git** installation was crashing )
    - not considering the package name itself as **provided** during dependency checking ( **anbox-git** installation was crashing )
    - not pre-downloading some source files ( e.g: from **anbox-image** )
    - not able to install packages based on other packages ( package name != package base ). e.g: **anbox-modules-dkms-git** > **anbox-git**
    - downgrade: pre-downloading sources from the latest version instead of the older
- Flatpak
    - downgrade: displaying "No Internet connection" when an error happens during commits reading
    - Flatpak < 1.5: an exception happens when trying to retrieve the information from partials
- UI:
    - **About** window icons scaling
    - Toolbar buttons get hidden [#5](https://github.com/vinifmor/bauh/issues/5)
    - not displaying icons retrieved from a HTTP redirect
    - minor bug fixes
    
### UI
- **Style selector** and **Application types** menu action moved to the new **Settings panel**
- **About** menu action split from the **Settings** menu as a new button
- The file chooser component now has a clean button alongside

## [0.8.1] 2020-01-14
### Features
- Flatpak
    - allow the user to choose the application installation level: **user** or **system** [#47](https://github.com/vinifmor/bauh/issues/47)
    - able to deal with user and system applications / runtimes [#47](https://github.com/vinifmor/bauh/issues/47)
    - able to list partial updates for Flatpak >= 1.4
    - new configuration file located at **~/.config/bauh/flatpak.yml** ( it allows to define a default installation level )
    
### Improvements
- All icons are now SVG files
- HDPI support improvements ( by [octopusSD](https://github.com/octopusSD) )
- Flatpak
    - the application name tooltip now displays the installation level. e.g: **gedit ( system )**
    - info window displaying the installation level
    - "remote not set" warning dropped in favor of the new behavior: automatically adds Flathub as the default remote at the user level
- Snap
    - snapd checking routine refactored
- Web
    - not using HTTP sessions anymore to perform the searches. It seems to avoid URLs not being found after an internet drop event
    - supporting JPEG images as custom icons
- UI
    - widgets visibility settings: the main widgets now should always be visible ( e.g: toolbar buttons )
    - scaling
    
### Fixes
- missing categories i18n [#48](https://github.com/vinifmor/bauh/issues/48)
- Flatpak:
    - updating application dependencies during updating and downgrading
- Web:
    - not handling HTTP connection issues
- not passing the Home path as a String for subprocesses ( an exception happens for Python 3.5 )
- UI:
    - not verifying if an icon path is a file
    - minor fixes

### UI
- Default **Type** icon removed from the Type filter to make the design more consistent

## [0.8.0] 2019-12-24
### Features
- Native Web applications support:
    - if an URL is typed on the search bar, a native web application result will be displayed on the table.
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
