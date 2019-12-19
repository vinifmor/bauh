**bauh** ( ba-oo ) is a graphical user interface to manage your Linux applications ( packages ) ( old **fpakman** ). It currently supports Flatpak, Snap, AppImage and AUR packaging types. When you launch **bauh** you will see
a management panel where you can search, update, install, uninstall and launch applications. You can also downgrade some applications depending on the package technology.

It has a **tray mode** (see **Settings** below) that attaches the application icon to the system tray providing a quick way to launch it. Also the icon will get red when updates are available.

This project has an official Twitter account ( **@bauh4linux** ) so people can stay on top of its news.

To contribute with this project, have a look at [CONTRIBUTING.md](https://github.com/vinifmor/bauh/blob/master/CONTRIBUTING.md)


![management panel](https://raw.githubusercontent.com/vinifmor/bauh/master/pictures/panel.png)


### Developed with
- Python3 and Qt5.

### Requirements

#### Debian-based distros
- **python3.5** or above
- **pip3**
- **python3-venv** ( only for **Manual installation** described below )

#### Arch-based distros
- **python**
- **python-requests**
- **python-pip**
- **python-pyqt5**
- **python-yaml**

##### Optional
- **flatpak**: to be able to handle Flatpak applications
- **snapd**: to be able to handle Snap applications
- **pacman**: to be able to handle AUR packages
- **wget**: to be able to handle AppImage and AUR packages
- **sqlite3**: to be able to handle AppImage applications
- **git**: to be able to downgrade AUR packages
- **aria2**: faster AppImage and AUR source files downloading ( reduces packages installation time. More information below. )
- **libappindicator3**: for the **tray mode** in GTK3 desktop environments

- [**fuse**](https://github.com/libfuse/libfuse) may be required to run AppImages on your system.

### Distribution

**AUR**

As [**bauh**](https://aur.archlinux.org/packages/bauh) package. There is also a staging version ([**bauh-staging**](https://aur.archlinux.org/packages/bauh-staging)) but is intended for testing and may not work properly.

[**PyPi**](https://pypi.org/project/bauh)

```pip3 install bauh ```

It may require **sudo**, but prefer the **Manual installation** described below to not mess up with your system libraries.


### Manual installation
- If you prefer a manual and isolated installation, open your favorite terminal application and type the following commands:

```
python3 -m venv bauh_env ( creates a virtualenv in a folder called **bauh_env** )
bauh_env/bin/pip install bauh ( installs bauh in the isolated environment )
bauh_env/bin/bauh  ( launches bauh )

# P.S: if you want to launch it attached to your system tray, replace the last command by: bauh_env/bin/bauh --tray=1
```

- To update your isolated bauh to the latest version:
```
bauh_env/bin/pip install bauh --upgrade
```

- To uninstall it just remove the **bauh_env** folder

- To create a shortcut ( desktop entry ) for it in your system menu ( assuming you created the isolated environment in your home folder using Python 3.7 ):
    - Create a file called **bauh.desktop** in **~/.local/share/applications** with the following content
```
[Desktop Entry]
Type=Application
Name=bauh
Comment=Install and remove applications ( AppImage, AUR, Flatpak, Snap )
Exec=/home/$USER/bauh_env/bin/bauh
Icon=/home/$USER/bauh_env/lib/python3.7/site-packages/bauh/view/resources/img/logo.svg
```

- If you want a shortcut to the tray, put the **--tray=1** parameter in the end of the **Exec** line of the example above ( e.g: **Exec=/home/$USER/bauh_env/bin/bauh --tray=1** )
- P.S: If the shortcut is not working, try to replace the **$USER** var by your user name.

### Autostart
In order to autostart the application, use your Desktop Environment settings to register it as a startup application / script (**bauh --tray=1**).

### Uninstallation
Before uninstalling bauh via your package manager, consider executing `bauh --reset` to remove configuration and cache files stored in your **HOME** folder.

### Theme issues
If bauh is not starting properly after changing its style, execute `bauh --reset` to reset its configuration or just delete the **style** key from the file **~/.config/bauh/config.json**.

### Gems ( package technology support )
#### Flatpak ( flatpak )
- The user is able to search, install, uninstall, downgrade, launch and retrieve the applications history

#### Snap ( snap )
- The user is able to search, install, uninstall, refresh, launch and downgrade applications

#### AppImage ( appimage )
- The user is able to search, install, uninstall, downgrade, launch and retrieve the applications history
- Supported sources: [AppImageHub](https://appimage.github.io) ( **applications with no releases published to GitHub are currently not available** )
- Installed applications are store at **~/.local/share/bauh/appimage/installed**
- Desktop entries ( menu shortcuts ) of the installed applications are stored at **~/.local/share/applications**
- Downloaded database files are stored at **~/.local/share/bauh/appimage** as **apps.db** and **releases.db**
- Databases are always updated when bauh starts
- Databases updater daemon running every 20 minutes ( it can be customized via the configuration file described below )
- Crashes may happen during an AppImage installation if **AppImageLauncher** is installed. It is advisable to uninstall it and reboot the system before trying to install an application.
- All supported application names can be found at: https://github.com/vinifmor/bauh-files/blob/master/appimage/apps.txt
- The configuration file is located at **~/.config/bauh/appimage.yml** and it allows the following customizations:
```
db_updater:
  enabled: true  # if 'false': disables the daemon database updater ( bauh will not be able to see if there are updates for your already installed AppImages )
  interval: 1200  # the databases update interval in SECONDS ( 1200 == 20 minutes )
```
- Required dependencies
    - Arch-based systems: **sqlite**, **wget** ( or **aria2** for faster multi-threaded downloads )
    - Debian-based systems: **sqlite3**, **wget** ( or **aria2** for faster multi-threaded downloads )
    - **aria2 will only be used if the multi-threaded download settings are enabled**

#### AUR ( arch )
- Only available for Arch-based systems
- The user is able to search, install, uninstall, downgrade, launch and retrieve packages history
- It handles conflicts, and missing / optional packages installations ( including from your distro mirrors )
- Automatically makes simple package compilation improvements:

    a) if **MAKEFLAGS** is not set in **/etc/makepkg.conf**,
    then a copy of **/etc/makepkg.conf** will be generated at **~/.config/bauh/arch/makepkg.conf** defining MAKEFLAGS to work with
    the number of your machine processors (**-j${nproc}**).

    b) same as previous, but related to **COMPRESSXZ** definition ( if '--threads=0' is not defined )

    Obs: For more information about them, have a look at [Makepkg](https://wiki.archlinux.org/index.php/Makepkg)
- During bauh initialization a full AUR normalized index is saved at **/tmp/bauh/arch/aur.txt**, and it will only be used if the AUR API cannot handle the number of matches for a given query.
- If some of your installed packages are not categorized, send an e-mail to **bauh4linux@gmail.com** informing their names and categories in the following format: ```name=category1[,category2,category3,...]```
- The configuration file is located at **~/.config/bauh/arch.yml** and it allows the following customizations:
```
optimize: true  # if 'false': disables the auto-compilation improvements
transitive_checking: true  # if 'false': the dependency checking process will be faster, but the application will ask for a confirmation every time a not installed dependency is detected.
``` 
- Required dependencies:
    - **pacman**
    - **wget**
- Optional dependencies:
    - **git**: allows to retrieve packages release history and downgrading
    - **aria2**: provides faster, multi-threaded downloads for required source files ( if the param )

#### Web Applications ( web )
- It allows the installation of native Web applications by typing an address / URL in the search bar.
- It also offers the possibility to customize the generated app the way you want: [TODO image or video]
- It also provides some suggestions coming with predefined settings, and they also can be retrieved by searching their names. They are
defined at [suggestions.yml](https://github.com/vinifmor/bauh-files/blob/master/web/suggestions.yml), and downloaded during the application usage.
- It relies on [NodeJS](https://nodejs.org/en/), [Electron](https://electronjs.org/) and [nativefier](https://github.com/jiahaog/nativefier) to do all the magic, but you do not need them installed on your system. An isolated installation environment
will be generated at **~/.local/share/bauh/web/env**.
- The isolated environment is created based on the settings defined in [environment.yml](https://github.com/vinifmor/bauh-files/blob/master/web/environment.yml)
 ( downloaded during runtime ).
- Some applications require Javascript fixes to properly work. If it is a known fix, bauh will download the file JS file from [fix](https://github.com/vinifmor/bauh-files/tree/master/web/fix) and
install it with the generated app.
- The installed applications are located at **~/.local/share/bauh/installed**.
- A desktop entry / shortcut will generated for the installed applications at **~/.local/share/application**
- When the Tray Mode **Start Minimized** is defined during the installation setup, a desktop entry will be also generated at **~/.config/autostart**
allowing the application to launch automatically attached to system tray after the boot. 
- The configuration file for the Web apps support is located at **~/.config/bauh/web.yml** and it allows the following customizations:
```
environment:
  electron:
    version: null  # set a custom Electron version here ( e.g: '6.1.4' )
  system: false  # set it to 'true' if you want to use the nativefier version globally installed on your system 
```
- Required dependencies: 
    - Arch-based systems: **python-lxml**, **python-beautifulsoup4**
    - Debian-based systems ( using pip ): **beautifulsoup4**, **lxml** 

### General settings
You can change some application settings via environment variables or arguments (type ```bauh --help``` to get more information).
- **BAUH_SYSTEM_NOTIFICATIONS**: enable or disable system notifications. Use **0** (disable) or **1** (enable, default).
- **BAUH_CHECK_INTERVAL**: define the updates check interval in seconds. Default: 60.
- **BAUH_LOCALE**: define a custom app translation for a given locale key (e.g: 'pt', 'en', 'es', ...). Default: system locale.
- **BAUH_CACHE_EXPIRATION**: define a custom expiration time in SECONDS for cached API data. Default: 3600 (1 hour).
- **BAUH_ICON_EXPIRATION**: define a custom expiration time in SECONDS for cached icons. Default: 300 (5 minutes).
- **BAUH_DISK_CACHE**: enables / disables disk cache. When disk cache is enabled, the installed packages data are loaded faster. Use **0** (disable) or **1** (enable, default).
- **BAUH_DOWNLOAD_ICONS**: Enables / disables applications icons downloading. It may improve the application speed depending on how applications data are being retrieved. Use **0** (disable) or **1** (enable, default).
- **BAUH_CHECK_PACKAGING_ONCE**: If the availabilty of the supported packaging types should be checked only once. It improves the application speed if enabled, but can generate errors if you uninstall any packaging technology while using it, and every time a new supported packaging type is installed it will only be available after a restart. Use **0** (disable, default) or **1** (enable).
- **BAUH_TRAY**: If the tray icon and update-check daemon should be created. Use **0** (disable, default) or **1** (enable).
- **BAUH_SUGGESTIONS**: If application suggestions should be displayed if no package considered an application is installed (runtimes / libraries do not count as applications). Use **0** (disable) or **1** (enable, default).
- **BAUH_MAX_DISPLAYED**: Maximum number of displayed packages in the management panel table. Default: 50.
- **BAUH_LOGS**: enable **bauh** logs (for debugging purposes). Use: **0** (disable, default) or **1** (enable)
- **BAUH_DOWNLOAD_MULTITHREAD**: enable multi-threaded download for installation files ( only possible if **aria2** is installed ). This feature reduces the application installation time. Use **0** (disable) or **1** (enabled, default).
- **BAUH_TRAY_DEFAULT_ICON_PATH**: define a custom icon for the tray mode ( absolute path)
- **BAUH_TRAY_UPDATES_ICON_PATH** define a custom updates icon for the tray mode ( absolute path)

### How to improve **bauh** performance
- Disable package types that you do not want to deal with ( via GUI )
- If you don't care about restarting the app every time a new supported packaging technology is installed, set "check-packaging-once=1" (**bauh --check-packaging-once=1**). This can reduce the application response time up in some scenarios, since it won't need to recheck if the packaging type is available for every action you request.
- If you don't mind to see the applications icons, you can set "download-icons=0" (**bauh --download-icons=0**). The application may have a slight response improvement, since it will reduce the parallelism within it.
- Let the disk cache always enabled so **bauh** does not need to dynamically retrieve some data every time you launch it.


### Files and Logs
- Some application settings are stored in **~/.config/bauh/config.json**
- Installation logs are saved at **/tmp/bauh/logs/install**
- Some data about your installed applications are stored in **~/.cache/bauh** to load them faster ( default behavior ).

### [bauh-files](https://github.com/vinifmor/bauh-files)
- It is a separate repository with some files downloaded by **bauh** during runtime.

### Code structure
#### Modules

**view**: code associated with the graphical interface

**gems**: code responsible to work with the different packaging technologies ( every submodule deals with one or more types )

**api**: code abstractions representing the main actions that a user can do with Linux packages (search, install, ...). These abstractions are implemented by the **gems**, and
the **view** code is only attached to them (it does not know how the **gems** handle these actions)

**commons**: common code used by **gems** and **view**

### Roadmap
- Support for other packaging technologies
- Separate modules for each packaging technology
- Memory and performance improvements
- Improve user experience
