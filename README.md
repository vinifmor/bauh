<p align="center">
    <img src="https://raw.githubusercontent.com/vinifmor/bauh/staging/bauh/view/resources/img/logo.svg?sanitize=true" width="128" height="128">
</p>


**bauh** (ba-oo), formerly known as **fpakman**, is a graphical interface for managing your Linux packages/applications. It currently supports
the following formats: AppImage, Arch (repositories/AUR), Flatpak, Snap and native Web applications.

Key features:
- A management panel where you can: search, install, uninstall, upgrade, downgrade, launch, ignore updates and retrieve releases history from software packages.
- Tray mode: it launches attached to the system tray and publishes notifications when there are software updates available
- System backup: it integrates with **Timeshift** to provide a simple and safe backup process before applying changes to your system.


This project has an official Twitter account (**@bauh4linux**) so people can stay on top of its news.


To contribute have a look at [CONTRIBUTING.md](https://github.com/vinifmor/bauh/blob/master/CONTRIBUTING.md)

<p align="center">
    <img src="https://raw.githubusercontent.com/vinifmor/bauh-files/master/pictures/panel.png">
</p>


### Developed with
- Python3 and Qt5

### Basic requirements

#### Debian-based distros
- **python3.5** or above
- **pip3**
- **python3-requests**
- **python-yaml**
- **python3-pyqt5.qtsvg**
- **libqt5svg5**
- **qt5dxcb-plugin**
- **libappindicator3** (for the **tray mode** in GTK3 desktop environments)
- **timeshift** (optional: to allow system backups)
- **python3-venv** (only for [Manual installation](https://github.com/vinifmor/bauh/tree/wgem#manual-installation))

#### Arch-based distros
- **python**
- **python-requests**
- **python-pip**
- **python-pyqt5**
- **python-pyqt5-sip**
- **python-yaml**
- **qt5-svg**
- **libappindicator-gtk3** (for the **tray mode** in GTK3 desktop environments)
- **timeshift** (optional: to allow system backups)

The other requirements depend on which type of packages you want to manage (see [Gems](https://github.com/vinifmor/bauh/tree/wgem#gems--package-technology-support-)).

### Distribution

**AUR**

As [**bauh**](https://aur.archlinux.org/packages/bauh) package. There is also a staging version ([**bauh-staging**](https://aur.archlinux.org/packages/bauh-staging)) but is intended for testing and may not work properly.

[**PyPi**](https://pypi.org/project/bauh)

```pip3 install bauh ```

It may require **sudo**, but prefer the **Manual installation** described below to not mess up with your system libraries.


### Manual installation
- If you prefer a manual and isolated installation, open your favorite terminal application and type the following commands:

```
python3 -m venv bauh_env (creates a virtualenv in a folder called "bauh_env")
bauh_env/bin/pip install bauh (installs bauh in the isolated environment)
bauh_env/bin/bauh  (launches bauh)

# P.S: if you want to launch it attached to your system tray, replace the last command by: bauh_env/bin/bauh-tray
```

- To update your isolated bauh to the latest version:
```
bauh_env/bin/pip install bauh --upgrade
```
P.S: if the command above does not work. Try: `bauh_env/bin/pip uninstall bauh -y && bauh_env/bin/pip install bauh`

- To uninstall it just remove the **bauh_env** folder

- To create a shortcut/desktop entry for it on your system's menu (assuming you created the isolated environment on your home folder using Python 3.7):
    - Copy the files from **bauh/desktop** to **~/.local/share/applications** (just replace the **Exec** field by: `Exec=/home/$USER/bauh_env/bin/bauh`)
    - Copy **logo.svg** from **bauh/view/resources/img** to **/usr/share/icons/hicolor/scalable/apps** as **bauh.svg**
    - P.S: If the shortcut is not working, try to replace the **$USER** var by your user name.

### Autostart
In order to initialize bauh when the system starts, use your Desktop Environment settings to register it as a startup application / script (**bauh-tray**). Or
create a file named **bauh.desktop** in **~/.config/autostart** with the content below:
```
[Desktop Entry]
Type=Application
Name=bauh (tray)
Exec=/path/to/bauh-tray
```

### Uninstallation
Before uninstalling bauh via your package manager, consider executing `bauh --reset` to remove its configuration and cached files stored on your **HOME** folder.


### Gems (package technology support)
#### Flatpak (flatpak)

- Supported actions: search, install, uninstall, downgrade, launch, history and ignore updates
- Applications with ignored updates are defined at **~/.config/bauh/flatpak/updates_ignored.txt**
- The configuration file is located at **~/.config/bauh/flatpak.yml** and it allows the following customizations:
```
installation_level: null # defines a default installation level: user or system. (the popup will not be displayed if a value is defined)
```

- Required dependencies:
    - Any distro: **flatpak**

#### Snap (snap)

- Supported actions: search, install, uninstall, launch, downgrade
- Custom actions: 
    - refresh: tries to update the current Snap application revision
    - change channel: allows to change the Snap application channel
- The configuration file is located at **~/.config/bauh/snap.yml** and it allows the following customizations:
```
install_channel: false  # it allows to select an available channel during the application installation. Default: false
```
- Required dependencies:
    - Any distro: **snapd** ( it must be enabled after its installation. Details at https://snapcraft.io/docs/installing-snapd )

#### AppImage (appimage)

- Supported actions: search, install, uninstall, downgrade, launch, history and ignore updates
- **Only x86_64 AppImage files are available through the search mechanism at the moment**
- Crashes may happen during an AppImage installation if **AppImageLauncher** is installed. It is recommended to uninstall it and reboot your system before trying to install an application.
- Custom actions
    - **Install AppImage file**: allows to install a external AppImage file
    - **Upgrade file**: allows to upgrade a manually installed AppImage file
- Supported sources: [AppImageHub](https://appimage.github.io) (**applications with no releases published to GitHub are currently not available**)
- Installed applications are store at **~/.local/share/bauh/appimage/installed**
- Desktop entries ( menu shortcuts ) of the installed applications are stored at **~/.local/share/applications**
- Symlinks are created at **~/.local/bin**. They have the same name of the application (if the name already exists, it will be created as 'app_name-appimage'. e.g: 'rpcs3-appimage')
- Downloaded database files are stored at **~/.local/share/bauh/appimage** as **apps.db** and **releases.db**
- Databases are always updated when bauh starts
- Databases updater daemon running every 20 minutes (it can be customized via the configuration file described below)
- All supported application names can be found at [apps.txt](https://github.com/vinifmor/bauh-files/blob/master/appimage/apps.txt)
- Applications with ignored updates are defined at **~/.config/bauh/appimage/updates_ignored.txt**
- The configuration file is located at **~/.config/bauh/appimage.yml** and it allows the following customizations:
```
db_updater:
  enabled: true  # if 'false': disables the daemon database updater (bauh will not be able to see if there are updates for your already installed AppImages)
  interval: 1200  # the databases update interval in SECONDS (1200 == 20 minutes)
```
- Required dependencies
    - Arch-based systems: **sqlite**, **wget** (or **aria2**/**axel** for faster multi-threaded downloads)
    - Debian-based systems: **sqlite3**, **wget** (or **aria2**/**axel** for faster multi-threaded downloads)
    - [**fuse**](https://github.com/libfuse/libfuse) may be required to run AppImages on your system
    - P.S: **aria2/axel will only be used if multi-threaded downloads are enabled**

#### Arch (arch -> Repositories/AUR)
- Only available for **Arch-based systems**
- Repository packages supported actions: search, install, uninstall, launch and ignore updates
- AUR packages supported actions: search, install, uninstall, downgrade, launch, history and ignore updates
- It handles conflicts, missing / optional packages installations, and several providers scenarios
- Automatically makes simple package compilation improvements:

    a) if **MAKEFLAGS** is not set in **/etc/makepkg.conf**,
    then a copy of **/etc/makepkg.conf** will be generated at **~/.config/bauh/arch/makepkg.conf** defining MAKEFLAGS to work with
    the number of your machine processors (**-j${nproc}**).

    b) same as previous, but related to **COMPRESSXZ** and **COMPRESSZST** definitions (if '--threads=0' is not defined)
    
    c) **ccache** will be added to **BUILDENV** if it is installed on the system and already not defined 
    
    d) set the device processors to performance mode

    Obs: For more information about them, have a look at [Makepkg](https://wiki.archlinux.org/index.php/Makepkg)
- During bauh initialization a full AUR normalized index is saved at **/tmp/bauh/arch/aur.txt**, and it will only be used if the AUR API cannot handle the number of matches for a given query.
- If some of your installed packages are not categorized, send an e-mail to **bauh4linux@gmail.com** informing their names and categories in the following format: ```name=category1[,category2,category3,...]``` or open a PullRequest changing [categories.txt](https://github.com/vinifmor/bauh-files/blob/master/arch/categories.txt)
- Custom actions
    - **synchronize packages database**: synchronizes the database against the configured mirrors (`sudo pacman -Syy`)
    - **refresh mirrors**: allows the user to define multiple mirrors locations and sort by the fastest (`sudo pacman-mirrors -c country1,country2 && sudo pacman-mirrors --fasttrack 5 && sudo pacman -Syy`)
    - **quick system upgrade**: it executes a default pacman upgrade (`pacman -Syyu --noconfirm`)
    - **clean cache**: it cleans the pacman cache diretory (default: `/var/cache/pacman/pkg`)
    - **mark PKGBUILD as editable**: it marks a given PKGBUILD of a package as editable (a popup with the PKGBUILD will be displayed before upgrading/downgrading this package). Action only available when the configuration property **edit_aur_pkgbuild** is not **false**.
    - **unmark PKGBUILD as editable**: reverts the action described above. Action only available when the configuration property **edit_aur_pkgbuild** is not **false**.
- Installed AUR packages have their **PKGBUILD** files cached at **~/.cache/bauh/arch/installed/$pkgname**
- Packages with ignored updates are defined at **~/.config/bauh/arch/updates_ignored.txt**
- The configuration file is located at **~/.config/bauh/arch.yml** and it allows the following customizations:
```
optimize: true  # if 'false': disables the auto-compilation improvements
sync_databases: true # package databases synchronization once a day before the first package installation/upgrade/downgrade
sync_databases_startup: true  # package databases synchronization once a day during startup
clean_cached: true  # defines if old cached versions should be removed from the disk cache during a package uninstallation
refresh_mirrors_startup: false # if the package mirrors should be refreshed during startup
mirrors_sort_limit: 5  # defines the maximum number of mirrors that will be used for speed sorting. Use 0 for no limit or leave it blank to disable sorting. 
aur:  true. Default: true  # allows to manage AUR packages
repositories: true  # allows to manage packages from the configured repositories. Default: true
repositories_mthread_download: false  # enable multi-threaded download for repository packages if aria2/axel is installed (otherwise pacman will download the packages). Default: false
automatch_providers: true  # if a possible provider for a given package dependency exactly matches its name, it will be chosen instead of asking for the user to decide (false). Default: true.
edit_aur_pkgbuild: false  # if the AUR PKGBUILD file should be displayed for edition before the make process. true (PKGBUILD will always be displayed for edition), false (PKGBUILD never will be displayed), null (a popup will ask if the user want to edit the PKGBUILD). Default: false.
aur_build_dir: null  # defines a custom build directory for AUR packages (a null value will point to /tmp/bauh/arch (non-root user) or /tmp/bauh_root/arch (root user)). Default: null.
aur_remove_build_dir: true  # it defines if a package's generated build directory should be removed after the operation is finished (installation, upgrading, ...). Options: true, false (default: true).
aur_build_only_chosen : true  # some AUR packages have a common file definition declaring several packages to be built. When this property is 'true' only the package the user select to install will be built (unless its name is different from those declared in the PKGBUILD base). With a 'null' value a popup asking if the user wants to build all of them will be displayed. 'false' will build and install all packages. Default: true.
check_dependency_breakage: true # if, during the verification of the update requirements, specific versions of dependencies must also be checked. Example: package A depends on version 1.0 of B. If A and B were selected to upgrade, and B would be upgrade to 2.0, then B would be excluded from the transaction. Default: true.
suggest_unneeded_uninstall: false  # if the dependencies apparently no longer necessary associated with the uninstalled packages should be suggested for uninstallation. When this property is enabled it automatically disables the property 'suggest_optdep_uninstall'. Default: false (to prevent new users from making mistakes)
suggest_optdep_uninstall: false  # if the optional dependencies associated with uninstalled packages should be suggested for uninstallation. Only the optional dependencies that are not dependencies of other packages will be suggested. Default: false (to prevent new users from making mistakes)
```
- Required dependencies:
    - **pacman**
    - **wget**
- Optional dependencies:
    - **git**: allows to retrieve packages release history and downgrading
    - **aria2** or **axel**: provides faster, multi-threaded downloads for required source files

#### Native Web Applications ( web )
- It allows the installation of native Web applications by typing their addresses/URLs on the search bar

<p align="center">
    <img src="https://raw.githubusercontent.com/vinifmor/bauh-files/master/pictures/web/url_search.gif">
</p>


- It offers the possibility to customize the generated app the way you want:

<p align="center">
    <img src="https://raw.githubusercontent.com/vinifmor/bauh-files/master/pictures/web/options.gif">
</p>


- It provides some suggestions coming with predefined settings, and they also can be retrieved by their names. They are
defined at [suggestions.yml](https://github.com/vinifmor/bauh-files/blob/master/web/suggestions.yml), and downloaded during the application usage.

<p align="center">
    <img src="https://raw.githubusercontent.com/vinifmor/bauh-files/master/pictures/web/suggestions.gif">
</p>


- It relies on [NodeJS](https://nodejs.org/en/), [Electron](https://electronjs.org/) and [nativefier](https://github.com/jiahaog/nativefier) to do all the magic, but you do not need them installed on your system. An isolated installation environment
will be generated at **~/.local/share/bauh/web/env**.
- The isolated environment is created based on the settings defined in [environment.yml](https://github.com/vinifmor/bauh-files/blob/master/web/environment.yml)
 (downloaded during runtime).
- Some applications require Javascript fixes to properly work. If there is a known fix, bauh will download the file from [fix](https://github.com/vinifmor/bauh-files/tree/master/web/fix) and
attach it to the generated app.
- The installed applications are located at **~/.local/share/bauh/installed**.
- A desktop entry / shortcut will be generated for the installed applications at **~/.local/share/application**
- If the Tray Mode **Start Minimized** is defined during the installation setup, a desktop entry will be also generated at **~/.config/autostart**
allowing the application to launch automatically after the system's boot attached to the tray.

<p align="center">
    <img src="https://raw.githubusercontent.com/vinifmor/bauh-files/master/pictures/web/tray.gif">
</p>


- Specific actions
    - Clean installation environment: removes all the installation environment folders (it does not remove installed apps)
 
- The configuration file is located at **~/.config/bauh/web.yml** and it allows the following customizations:
```
environment:
  electron:
    version: null  # set a custom Electron version here (e.g: '6.1.4')
  system: false  # set it to 'true' if you want to use the nativefier version globally installed on your system 
```
- Required dependencies: 
    - Arch-based systems: **python-lxml**, **python-beautifulsoup4**
    - Debian-based systems ( using pip ): **beautifulsoup4**, **lxml** 

### General settings

#### Environment variables / parameters
You can change some application settings via environment variables or arguments (type ```bauh --help``` to get more information).
- `--tray`: if bauh should be launched attaching itself to the system tray.
- `--settings`: it displays only the settings window.
- `--reset`: it cleans all configurations and cached data stored in the HOME directory.
- `--logs`: it enables logs (for debugging purposes).

#### General configuration file (**~/.config/bauh/config.yml**)
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
  style: null  # the current QT style set. A null value will map to 'Fusion', 'Breeze' or 'Oxygen' (depending on what is installed)
  table:
    max_displayed: 50  # defines the maximum number of displayed applications on the table.
  tray:  # system tray settings
    default_icon: null  # defines a path to a custom icon
    updates_icon: null  # defines a path to a custom icon indicating updates
  hdpi: true  # enables HDPI rendering improvements. Use 'false' to disable them if you think the interface looks strange
  auto_scale: false # activates Qt auto screen scale factor (QT_AUTO_SCREEN_SCALE_FACTOR). It fixes scaling issues for some desktop environments (like Gnome)
  scale_factor: 1.0  # defines the interface display scaling factor (Qt). Raise the value to raise the interface size. The settings window display this value as a percentage (e.g: 1.0 -> 100%).
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
```
#### Tray icons
Priority: 
  1) Icon paths defined in **~/.config/bauh/config.yml**
  2) Icons from the system with the following names: `bauh_tray_default` and `bauh_tray_updates`
  3) Own packaged icons
  
#### CLI
- It is a mode in which you can perform the same actions allowed in the GUI via command line. For now it only allows to check for software updates (`bauh-cli updates`).
- To verify the available commands: `bauh-cli --help`. 
- To list the command parameters: `bauh-cli [command] --help`. (e.g: `bauh-cli updates --help`)

### How to improve performance
- Disable the application types you do not want to deal with
- If you don't care about restarting the app every time a new supported package technology is installed, enable `single_dependency_checking`. This can reduce the application response time, since it won't need to recheck if the required technologies are available on your system every time a given action is executed.
- If you don't mind to see the applications icons, you can disable them via `download: icons: false`. The application may have a slight response improvement, since it will reduce the IO and parallelism within it.

### Files and Logs
- Installation logs and temporary files are saved at **/tmp/bauh** (or **/tmp/bauh_root** if you launch it as root)
- Some data about your installed applications are stored in **~/.cache/bauh** to load them faster

### [bauh-files](https://github.com/vinifmor/bauh-files)
- It is a separate repository with some files downloaded during runtime.

### Code structure
#### Modules

**view**: code associated with the graphical interface

**gems**: code responsible to work with the different packaging technologies (every submodule deals with one or more types)

**api**: code abstractions representing the main actions that a user can do with Linux packages (search, install, ...). These abstractions are implemented by the **gems**, and
the **view** code is only attached to them (it does not know how the **gems** handle these actions)

**commons**: common code used by **gems** and **view**

### Roadmap
- Support for other packaging technologies
- Separate modules for each packaging technology
- Memory and performance improvements
- Improve user experience
