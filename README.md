**bauh** (ba-oo), formerly known as **fpakman**, is a graphical interface for managing your Linux software (packages/applications). It currently supports: AppImage, ArchLinux repositories/AUR, Flatpak, Snap and Web applications.

Key features
- A management panel where you can: search, install, uninstall, upgrade, downgrade and launch you applications (more actions are available...)
- Tray mode: it launches attached to the system tray and publishes notifications when there are software updates available
- System backup: it integrates with [Timeshift](https://github.com/teejee2008/timeshift) to provide a simple and safe backup process before applying changes to your system.
- Custom themes: it's possible to customize the tool's style/appearance. More at [Custom themes](#custom_themes) 


<p align="center">
    <img src="https://raw.githubusercontent.com/vinifmor/bauh-files/master/pictures/panel-themes.gif">
</p>


## Index
1.  [Installation](#installation)
    - [Ubuntu-based distros (20.04)](#inst_ubuntu)
    - [Arch-based distros](#inst_arch)
2.  [Isolated installation](#inst_iso)
3.  [Desktop entry / menu shortcut](#desk_entry)
4.  [Autostart: tray mode](#autostart)
5.  [Distribution](#dist)
6.  [Supported types](#types)
    - [AppImage](#type_appimage)
    - [Arch packages/AUR](#type_arch)
    - [Flatpak](#type_flatpak)
    - [Snap](#type_snap)
    - [Native Web applications](#type_web)
7.  [General settings](#settings)
8.  [Cache and logs](#cache_logs)
9.  [Custom themes](#custom_themes)
10. [Tray icons](#tray_icons)
11. [CLI (Command Line Interface)](#cli)
12. [Improving performance](#performance)
13. [bauh-files](#bauh_files)
14. [Code structure](#code)
15. [Roadmap](#roadmap)
16. [Social media](#social)
17. [Contributing](https://github.com/vinifmor/bauh/blob/master/CONTRIBUTING.md)

 

### Installation


#### <a name="inst_ubuntu">Ubuntu-based distros (20.04)</a>

##### Required dependencies

`sudo apt-get install python3 python3-pip python3-yaml python3-dateutil python3-pyqt5 python3-packaging python3-requests`

##### Installing bauh

`sudo pip3 install bauh`

##### Optional dependencies (they should be installed with apt-get/apt)

- `timeshift`: system backups
- `aria2`: multi-threaded downloads
- `axel`: multi-threaded downloads alternative
- `libappindicator3-1`: tray-mode
- `wget`, `sqlite3`, `fuse`: AppImage support
- `flatpak`: Flatpaks support
- `snapd`: Snaps support
- `python3-lxml`, `python3-bs4`: Web apps support
- `python3-venv`: [isolated installation](#inst_iso)

##### Updating bauh

Method 1

`sudo pip3 install bauh --upgrade`

Method 2

```
sudo pip3 uninstall bauh
sudo pip3 install bauh
```

##### Uninstalling bauh

```
bauh --reset  # removes cache and configurations files from HOME
sudo pip3 uninstall bauh
```


#### <a name="inst_arch">Arch-based distros</a>

##### Using yay

`yay -S bauh`


##### Using git

```
git clone  https://aur.archlinux.org/bauh.git
cd bauh
makepkg -si
```

##### Optional dependencies

- `timeshift`: system backups
- `aria2`: multi-threaded downloads
- `axel`: multi-threaded downloads alternative
- `libappindicator-gtk2`: tray-mode (GTK2 desktop environments)
- `libappindicator-gtk3`: tray-mode (GTK3 desktop environments) 
- `wget`, `sqlite`, `fuse2`, `fuse3`: AppImage support
- `flatpak`: Flatpaks support
- `snapd`: Snaps support
- `python-lxml`, `python-beautifulsoup4`: Web apps support
- `python-venv`: [isolated installation](#inst_iso)


##### Uninstalling bauh
```
bauh --reset  # removes cache and configurations files from HOME
pacman -R bauh
```


#### <a name="inst_iso">Isolated installation</a>

If you prefer an isolated installation from the system libraries, type the following commands:

```
python3 -m venv bauh_env       # creates an isolated environment inside the directory called "bauh_env"
bauh_env/bin/pip install bauh  # installs bauh in the isolated environment
bauh_env/bin/bauh              # launches bauh. For the tray-mode: bauh_env/bin/bauh-tray
```


Updating bauh

```
bauh_env/bin/pip install bauh --upgrade
```

Uninstalling bauh

```
bauh_env/bin/bauh --reset  # removes cache and configurations files from HOME
rm -rf bauh_env` (just remove the directory)
```


#### <a name="desk_entry">Desktop entry / menu shortcut</a>

To create a shortcut for bauh on your desktop menu:

- Copy the files from [bauh/desktop](https://github.com/vinifmor/bauh/tree/readme/bauh/desktop) to `~/.local/share/applications`
- Replace the `Exec` field on theses files by the bauh binary path. e.g: `Exec=/usr/bin/bauh` (or `bauh_env/bin/bauh`)
- Copy [logo.svg](https://github.com/vinifmor/bauh/blob/readme/bauh/view/resources/img/logo.svg) to `/usr/share/icons/hicolor/scalable/apps` as `bauh.svg`


#### <a name="autostart">Autostart: tray mode</a>

In order to initialize bauh with the system, use your Desktop Environment settings to register it as a startup application / script (**bauh-tray**). Or
create a file named **bauh.desktop** in **~/.config/autostart** with the content below:

```
[Desktop Entry]
Type=Application
Name=bauh (tray)
Exec=/path/to/bauh-tray
```


#### <a name="dist">Distribution</a>

bauh is officially distributed through [PyPi](https://pypi.org/project/bauh) and AUR ([bauh](https://aur.archlinux.org/packages/bauh) / [bauh-staging](https://aur.archlinux.org/packages/bauh-staging))


#### <a name="types">Supported types</a>


##### <a name="type_appimage">AppImage</a>

- Supported sources: [AppImageHub](https://appimage.github.io) (applications with no releases published to GitHub are not available)
- All available application names can be found at [apps.txt](https://github.com/vinifmor/bauh-files/blob/master/appimage/apps.txt)
- **Only x86_64 AppImage files are available through the search mechanism at the moment**
- Crashes may happen during an AppImage installation if [AppImageLauncher](https://github.com/TheAssassin/AppImageLauncher) is installed. It is recommended to uninstall it and reboot your system before trying to install an application.
- Extra actions
    - `Install AppImage file`: allows to install a external AppImage file
    - `Upgrade file`: allows to upgrade a manually installed AppImage file
    - `Update database`: manually synchronize the AppImage database

- Installed applications are store at `~/.local/share/bauh/appimage/installed`
- Desktop entries (menu shortcuts) of the installed applications are stored at **~/.local/share/applications** (name pattern: `bauh_appimage_appname.desktop`)
- Symlinks are created at **~/.local/bin**. They have the same name of the application (if the name already exists, it will be created as 'app_name-appimage'. e.g: `rpcs3-appimage`)
- Downloaded database files are stored at **~/.cache/bauh/appimage** as **apps.db** and **releases.db**
- Databases are updated during the initialization process if they are considered outdated
- Applications with ignored updates are defined at **~/.config/bauh/appimage/updates_ignored.txt**
- The configuration file is located at **~/.config/bauh/appimage.yml** and it allows the following customizations:
```
database:
  expiration: 60  # defines the period (in minutes) in which the database will be considered up to date during the initialization process. Use 0 if you always want to update it. Default: 60.
suggestions:
    expiration: 24  # defines the period (in hours) in which the suggestions stored in disc will be considered up to date. Use 0 if you always want to update them. Default: 24.
```


##### <a name="type_arch">Arch packages/AUR<a>

- Only available for Arch-based systems
- It handles conflicts, missing / optional packages installations, and several providers scenarios
- [rebuild-detector](https://github.com/maximbaz/rebuild-detector) integration (AUR only)
- Automatically makes simple package compilation improvements (for AUR packages):

    a) if `MAKEFLAGS` is not set in `/etc/makepkg.conf`,
    then a copy of `/etc/makepkg.conf` will be generated at `~/.config/bauh/arch/makepkg.conf` defining MAKEFLAGS to work with
    the number of your machine processors (`-j${nproc}`).

    b) same as previous, but related to `COMPRESSXZ` and `COMPRESSZST` definitions (if '--threads=0' is not defined)
    
    c) `ccache` will be added to `BUILDENV` if it is installed on the system and already not defined 
    
    d) set the device processors to performance mode

    Obs: For more information about them, have a look at [Makepkg](https://wiki.archlinux.org/index.php/Makepkg)

- Extra actions
    - `Synchronize packages database`: synchronizes the database against the configured mirrors (`sudo pacman -Syy`)
    - `Refresh mirrors`: allows the user to define multiple mirrors locations and sort by the fastest (`sudo pacman-mirrors -c country1,country2 && sudo pacman-mirrors --fasttrack 5 && sudo pacman -Syy`)
    - `Quick system upgrade`: it executes a default pacman upgrade (`pacman -Syyu --noconfirm`)
    - `Clean cache`: it cleans the pacman cache directory (default: `/var/cache/pacman/pkg`)
    - `Mark PKGBUILD as editable`: it marks a given PKGBUILD of a package as editable (a popup with the PKGBUILD will be displayed before upgrading/downgrading this package). Action only available when the configuration property `edit_aur_pkgbuild` is not `false`.
    - `Unmark PKGBUILD as editable`: reverts the action described above. Action only available when the configuration property `edit_aur_pkgbuild` is not `false`.
    - `Allow reinstallation check`: it allows to check if a given AUR packages requires to be rebuilt
    - `Ignore reinstallation check`: it does not to check if a given AUR packages requires to be rebuilt
    - `Check Snaps support`: checks if the Snapd services are properly enabled.

- If you have AUR added as a repository on you pacman configuration, make sure to disable bauh's support (through the settings described below)
- AUR package compilation may require additional installed packages to properly work. Some of them are defined on the field `optdepends` of the [PKGBUILD](https://aur.archlinux.org/cgit/aur.git/tree/PKGBUILD?h=bauh) 
- **Repository packages currently do not support the following actions: Downgrade and History**
- If some of your installed packages are not categorized, open a PullRequest to the **bauh-files** repository changing [categories.txt](https://github.com/vinifmor/bauh-files/blob/master/arch/categories.txt)
- During bauh initialization a full AUR normalized index is saved at `~/.cache/bauh/arch/aur/index.txt`
- Installed AUR packages have their PKGBUILD files cached at `~/.cache/bauh/arch/installed/$pkgname`
- Packages with ignored updates are defined at `~/.config/bauh/arch/updates_ignored.txt`
- The configuration file is located at `~/.config/bauh/arch.yml` and it allows the following customizations:
```
aur:  true # allows to manage AUR packages. Default: true
repositories: true  # allows to manage packages from the configured repositories. Default: true
optimize: true  # if 'false': disables the auto-compilation improvements
sync_databases: true # package databases synchronization once a day before the first package installation/upgrade/downgrade
sync_databases_startup: true  # package databases synchronization once a day during startup
clean_cached: true  # defines if old cached versions should be removed from the disk cache during a package uninstallation
refresh_mirrors_startup: false # if the package mirrors should be refreshed during startup
mirrors_sort_limit: 5  # defines the maximum number of mirrors that will be used for speed sorting. Use 0 for no limit or leave it blank to disable sorting. 
repositories_mthread_download: false  # enable multi-threaded download for repository packages if aria2/axel is installed (otherwise pacman will download the packages). Default: false
automatch_providers: true  # if a possible provider for a given package dependency exactly matches its name, it will be chosen instead of asking for the user to decide (false). Default: true.
edit_aur_pkgbuild: false  # if the AUR PKGBUILD file should be displayed for edition before the make process. true (PKGBUILD will always be displayed for edition), false (PKGBUILD never will be displayed), null (a popup will ask if the user want to edit the PKGBUILD). Default: false.
aur_build_dir: null  # defines a custom build directory for AUR packages (a null value will point to /tmp/bauh/arch (non-root user) or /tmp/bauh_root/arch (root user)). Default: null.
aur_remove_build_dir: true  # it defines if a package's generated build directory should be removed after the operation is finished (installation, upgrading, ...). Options: true, false (default: true).
aur_build_only_chosen : true  # some AUR packages have a common file definition declaring several packages to be built. When this property is 'true' only the package the user select to install will be built (unless its name is different from those declared in the PKGBUILD base). With a 'null' value a popup asking if the user wants to build all of them will be displayed. 'false' will build and install all packages. Default: true.
aur_idx_exp: 1  # It defines the period (in HOURS) for the AUR index stored in disc to be considered up to date during the initialization process. Use 0 so that it is always updated. Default: 1. (P.S: this index is always updated when a package is installed/upgraded)
check_dependency_breakage: true # if, during the verification of the update requirements, specific versions of dependencies must also be checked. Example: package A depends on version 1.0 of B. If A and B were selected to upgrade, and B would be upgrade to 2.0, then B would be excluded from the transaction. Default: true.
suggest_unneeded_uninstall: false  # if the dependencies apparently no longer necessary associated with the uninstalled packages should be suggested for uninstallation. When this property is enabled it automatically disables the property 'suggest_optdep_uninstall'. Default: false (to prevent new users from making mistakes)
suggest_optdep_uninstall: false  # if the optional dependencies associated with uninstalled packages should be suggested for uninstallation. Only the optional dependencies that are not dependencies of other packages will be suggested. Default: false (to prevent new users from making mistakes)
categories_exp: 24  # It defines the expiration time (in HOURS) of the packages categories mapping file stored in disc. Use 0 so that it is always updated during initialization.
aur_rebuild_detector: true # it checks if packages built with old library versions require to be rebuilt. If a package needs to be rebuilt, it will be marked for update ('rebuild-detector' must be installed). Default: true.
```


##### <a name="type_flatpak">Flatpak</a>

- Applications with ignored updates are defined at `~/.config/bauh/flatpak/updates_ignored.txt`
- The configuration file is located at `~/.config/bauh/flatpak.yml` and it allows the following customizations:
```
installation_level: null # defines a default installation level: user or system. (the popup will not be displayed if a value is defined)
```


#### <a name="type_snap">Snap</a>

- Make sure **snapd** is properly installed and enabled on your system: https://snapcraft.io/docs/installing-snapd 
- Extra actions: 
    - `Refresh`: tries to update the current Snap application revision
    - `Change channel`: allows to change the Snap application channel
- The configuration file is located at `~/.config/bauh/snap.yml` and it allows the following customizations:
```
install_channel: false  # it allows to select an available channel during the application installation. Default: false
categories_exp: 24  # It defines the expiration time (in HOURS) of the Snaps categories mapping file stored in disc. Use 0 so that it is always updated during initialization.
```


#### <a name="type_web">Native Web applications</a>
- It allows the installation of Web applications by typing their addresses/URLs on the search bar

<p align="center">
    <img src="https://raw.githubusercontent.com/vinifmor/bauh-files/master/pictures/web/url_search.gif">
</p>


- It offers the possibility to customize the generated app the way you want:

<p align="center">
    <img src="https://raw.githubusercontent.com/vinifmor/bauh-files/master/pictures/web/options.png">
</p>


- It provides some suggestions coming with predefined settings, and they also can be find by their names. They are
defined at [suggestions.yml](https://raw.githubusercontent.com/vinifmor/bauh-files/master/web/env/v1/suggestions.yml), and downloaded during the application usage.

<p align="center">
    <img src="https://raw.githubusercontent.com/vinifmor/bauh-files/master/pictures/web/suggestions.gif">
</p>


- It relies on [NodeJS](https://nodejs.org/en/), [Electron](https://electronjs.org/) and [nativefier](https://github.com/jiahaog/nativefier) to do all the magic, but you do not need them installed on your system. An isolated installation environment
will be generated at **~/.local/share/bauh/web/env**.
- It supports DRM protected content through a custom Electron implementation provided by [castLabs](https://github.com/castlabs/electron-releases). nativefier handles the switch between the official Electron and the custom.
- The isolated environment is created based on the settings defined in [environment.yml](https://raw.githubusercontent.com/vinifmor/bauh-files/master/web/env/v1/environment.yml)
 (downloaded during runtime).
- Some applications require Javascript fixes to properly work. If there is a known fix, bauh will download the file from [fix](https://github.com/vinifmor/bauh-files/tree/master/web/fix) and
attach it to the generated app.
- The installed applications are located at `~/.local/share/bauh/installed`.
- A desktop entry / menu shortcut will be generated for the installed applications at `~/.local/share/application`
- If the Tray Mode **Start Minimized** is defined during the installation setup, a desktop entry will be also generated at `~/.config/autostart`
allowing the application to launch automatically after the system's boot attached to the tray.

<p align="center">
    <img src="https://raw.githubusercontent.com/vinifmor/bauh-files/master/pictures/web/tray.gif">
</p>


- Extra actions
    - `Clean installation environment`: removes all the installation environment folders (it does not remove installed apps)
 
- The configuration file is located at `~/.config/bauh/web.yml` and it allows the following customizations:

```
environment:
  electron:
    version: null  # set a custom Electron version here (e.g: '6.1.4')
  system: false  # set it to 'true' if you want to use the nativefier version globally installed on your system 
  cache_exp: 24 # defines the period (in HOURS) in which the stored environment settings are considered valid. Use 0 so that they are always updated. Default: 24.

suggestions:
    cache_exp: 24  # defines the period (in HOURS) in which suggestions stored on the disk are considered up to date during the initialization process. Use 0 so that they are always updated. Default: 24.
```


#### <a name="settings">General settings</a>

##### Parameters

You can change some application settings via environment variables or arguments (type ```bauh --help``` to get more information).
- `--tray`: if bauh should be launched attaching itself to the system tray.
- `--settings`: it displays only the settings window.
- `--reset`: it cleans all configurations and cached data stored in the HOME directory.
- `--logs`: it enables logs (for debugging purposes).
- `--offline`: it assumes the internet connection is off.


##### Configuration file (**~/.config/bauh/config.yml**)

```
download:
  icons: true # allows bauh to download the applications icons when they are not saved on the disk
  multithreaded: true  # allows bauh to use a multithreaded download client installed on the system to download applications source files faster
  multithreaded_client: null  # defines the multi-threaded download tool to be used. If null, the default installed tool will be used (priority: aria2 > axel). Possible tools/values: aria2, axel
gems: null  # defines the enabled applications types managed by bauh (a null value means "all available")
locale: null  # defines a different translation for bauh (a null value will retrieve the system's default locale)
store_root_password: true  # if the root password should be asked only once
memory_cache:
  data_expiration: 3600 # the interval in SECONDS that data cached in memory will live
  icon_expiration: 300  # the interval in SECONDS that icons cached in memory will live
suggestions:
  by_type: 10  # the maximum number of application suggestions that must be retrieved per type
  enabled: true  # if suggestions must be displayed when no application is installed
system:
  notifications: true  # if system popup should be displayed for some events. e.g: when there are updates, bauh will display a system popup
  single_dependency_checking: false  # if bauh should check only once if for the available technologies on the system.
ui:
  qt_style: fusion  # defines the Qt style. A null value will map to 'fusion' as well.
  table:
    max_displayed: 50  # defines the maximum number of displayed applications on the table. Use 0 for no limit.
  tray:  # system tray settings
    default_icon: null  # defines a path to a custom icon
    updates_icon: null  # defines a path to a custom icon indicating updates
  hdpi: true  # enables HDPI rendering improvements. Use 'false' to disable them if you think the interface looks strange
  auto_scale: false # activates Qt auto screen scale factor (QT_AUTO_SCREEN_SCALE_FACTOR). It fixes scaling issues for some desktop environments (like Gnome)
  scale_factor: 1.0  # defines the interface display scaling factor (Qt). Raise the value to raise the interface size. The settings window display this value as a percentage (e.g: 1.0 -> 100%).
  theme: defines the path to the theme/stylesheet file with a .qss extension (e.g: /path/to/my/theme.qss). For themes provided by bauh, only a string key is needed (e.g: light). Default: light
  system_theme: merges the system's theme/stylesheet with bauh's. Default: false.
updates:
  check_interval: 30  # the updates checking interval in SECONDS
  ask_for_reboot: true  # if a dialog asking for a system reboot should be displayed after a successful upgrade
disk:
    trim:
        after_upgrade: false # it trims the disk after a successful packages upgrade (`fstrim -a -v`). 'true' will automatically perform the trim and 'null' will display a confirmation dialog
backup:
    enabled: true  # generate timeshift snapshots before an action (if timeshift is installed on the system)
    mode: 'incremental' # incremental=generates a new snapshot based on another pre-exising one. 'only_one'=deletes all pre-existing snapshots and generates a fresh one.
    install: null  # defines if the backup should be performed before installing a package. Allowed values: null (a dialog will be displayed asking if a snapshot should be generated), true: generates the backup without asking. false: disables the backup for this operation
    uninstall: null  # defines if the backup should be performed before uninstalling a package. Allowed values: null (a dialog will be displayed asking if a snapshot should be generated), true: generates the backup without asking. false: disables the backup for this operation
    upgrade: null  # defines if the backup should be performed before upgrading a package. Allowed values: null (a dialog will be displayed asking if a snapshot should be generated), true: generates the backup without asking. false: disables the backup for this operation
    downgrade: null  # defines if the backup should be performed before downgrading a package. Allowed values: null (a dialog will be displayed asking if a snapshot should be generated), true: generates the backup without asking. false: disables the backup for this operation
    type: rsync  # defines the Timeshift backup mode -> 'rsync' (default) or 'btrfs'
boot:
    load_apps: true  # if the installed applications or suggestions should be loaded on the management panel after the initialization process. Default: true.
```

#### <a name="cache_logs">Cache and Logs</a>
- Installation logs and temporary files are saved at `/tmp/bauh` (or `/tmp/bauh_root` if you launch it as root)
- Some data about your installed applications are stored in `~/.cache/bauh` to load them faster


#### <a name="custom_themes">Custom themes</a>
- Custom themes can be provided by adding their files at `~/.local/share/bauh/themes` (sub-folders are allowed). 
- Themes are composed by 2 required and 1 optional files sharing the same name:
    - `my_theme.qss`: file with the qss rules. Full example: [light.qss](https://raw.githubusercontent.com/vinifmor/bauh/qss/bauh/view/resources/style/light/light.qss)
    - `my_theme.meta`: file defining the theme's data. Full example: [light.meta](https://raw.githubusercontent.com/vinifmor/bauh/qss/bauh/view/resources/style/light/light.meta) 
        - available fields:
            - `name`: name that will be displayed on the interface. It supports translations by adding additional `name` fields with brackets and the language code (e.g: `name[es]=Mi tema`)
            - `description`: theme's description that will be displayed on the interface. It supports translations like `name` (e.g: description[es] = Mi tema).
            - `version`: theme's version. It just works as information at the moment. (e.g: 1.0)
            - `root_theme`: optional attribute that points to a theme that must be loaded before the theme. It supports the bauh's default theme keys (e.g: default, light, ...) or a file path (e.g: `/path/to/root/file.qss`).
            - `abstract`: optional boolean attribute (true/false) that should only be used by themes that are not complete on their own and just work as a base (root) for other themes. Abstract themes are not displayed on the interface. Full example: [default.qss](https://raw.githubusercontent.com/vinifmor/bauh/qss/bauh/view/resources/style/default/default.qss) 
    - `my_theme.vars`: optional file defining `key=value` pairs of variables that will be available for the .qss file (can be referenced through the symbol **@**. e.g `@my_var`). Full example: [light.vars](https://raw.githubusercontent.com/vinifmor/bauh/qss/bauh/view/resources/style/light/light.vars)
        - common theme variables available: 
            - `style_dir`: path to the .qss file directory. Example: @style_dir/my_icon.svg
            - `images`: path to bauh's icons directory (gem icons are not available through this variable). Example: @images/logo.svg


#### <a name="tray_icons">Tray icons</a>

Priority: 
  1) Icon paths defined in **~/.config/bauh/config.yml**
  2) Icons from the system with the following names: `bauh_tray_default` and `bauh_tray_updates`
  3) Own packaged icons

  
#### <a name="cli">CLI (Command Line Interface)</a>

- For now it only allows checking for software updates (`bauh-cli updates`).
- To verify the available commands: `bauh-cli --help`. 
- To list the command parameters: `bauh-cli [command] --help`. (e.g: `bauh-cli updates --help`)


#### <a name="performance">Improving performance</a>

- Disable the application types you do not want to deal with
- If you don't care about restarting the app every time a new supported package technology is installed, enable `single_dependency_checking`. This can reduce the application response time, since it won't need to recheck if the required technologies are available on your system every time a given action is executed.
- If you don't mind to see the applications icons, you can disable them via `download: icons: false`. The application may have a slight response improvement, since it will reduce the IO and parallelism within it.
- For a faster initialization process, consider raising the values of settings properties associated with disk caching and the property `boot.load_apps` to `false`.


#### <a name="bauh_files">[bauh-files](https://github.com/vinifmor/bauh-files)</a>

It is a separate repository with some files downloaded during runtime.


#### <a name="code">Code structure</a>

- `view`: code associated with the graphical interface
- `gems`: code responsible to work with the different packaging technologies (every submodule deals with one or more types)
- `api`: code abstractions representing the main actions that a user can do with Linux packages (search, install, ...). These abstractions are implemented by the `gems`, and
the `view` code is only attached to them (it does not know how the `gems` handle these actions)
- `commons`: common code used by `gems` and `view`

#### <a name="roadmap">Roadmap</a>
- Support for other packaging technologies
- Separate modules for each packaging technology
- Memory and performance improvements
- Improve user experience

#### <a name="social">Social media</a>
- Twitter: [@bauh4linux](https://twitter.com/bauh4linux).
