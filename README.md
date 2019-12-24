**bauh** ( ba-oo ) is a graphical interface for managing your Linux applications / packages. It was formerly known as **fpakman**. It is able to manage AUR, AppImage, Flatpak and Snap applications, and also to generate native Web applications. When you launch **bauh** you will see
a management panel where you can search, update, install, uninstall and launch applications. Downgrading is also possible in some cases.

It has a **tray mode** ( see [Settings](https://github.com/vinifmor/bauh/tree/wgem#general-settings) ) that attaches itself to the system tray. The attached bauh icon will get red when updates are available.

This project has an official Twitter account ( **@bauh4linux** ) so people can stay on top of its news.

To contribute with this project, have a look at [CONTRIBUTING.md](https://github.com/vinifmor/bauh/blob/master/CONTRIBUTING.md)


![management panel](https://raw.githubusercontent.com/vinifmor/bauh/master/pictures/panel.png)


### Developed with
- Python3 and Qt5

### Basic requirements

#### Debian-based distros
- **python3.5** or above
- **pip3**
- **python3-requests**
- **python-yaml**
- **python3-venv** ( only for [Manual installation](https://github.com/vinifmor/bauh/tree/wgem#manual-installation) )
- **libappindicator3** ( for the **tray mode** in GTK3 desktop environments )

#### Arch-based distros
- **python**
- **python-requests**
- **python-pip**
- **python-pyqt5**
- **python-yaml**
- **libappindicator-gtk3** ( for the **tray mode** in GTK3 desktop environments )

The other requirements depend on which type of applications you want to manage ( see [Gems](https://github.com/vinifmor/bauh/tree/wgem#gems--package-technology-support-) ).

### Installation

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
In order to autostart the application, use your Desktop Environment settings to register it as a startup application / script (**bauh --tray=1**). Or
create a file named **bauh.desktop** in **~/.config/autostart** with the content below:
```
[Desktop Entry]
Type=Application
Name=bauh ( tray )
Exec=/path/to/bauh --tray=1
```

### Uninstallation
Before uninstalling bauh via your package manager, consider executing `bauh --reset` to remove configuration and cached files stored in your **HOME** folder.


### Gems ( package technology support )
#### Flatpak ( flatpak )
- The user is able to search, install, uninstall, downgrade, launch and retrieve the applications history

![flatpak_search](https://raw.githubusercontent.com/vinifmor/bauh/staging/pictures/flatpak/search.gif)

- Required dependencies:
    - Any distro: **flatpak**

#### Snap ( snap )
- The user is able to search, install, uninstall, refresh, launch and downgrade applications

![snap_search](https://raw.githubusercontent.com/vinifmor/bauh/staging/pictures/snap/search.gif)

- Required dependencies:
    - Any distro: **snapd** ( it must be enabled after its installation. Details at https://snapcraft.io/docs/installing-snapd )

#### AppImage ( appimage )
- The user is able to search, install, uninstall, downgrade, launch and retrieve the applications history

![appimage_search](https://raw.githubusercontent.com/vinifmor/bauh/staging/pictures/appimage/search.gif)

- Supported sources: [AppImageHub](https://appimage.github.io) ( **applications with no releases published to GitHub are currently not available** )
- Installed applications are store at **~/.local/share/bauh/appimage/installed**
- Desktop entries ( menu shortcuts ) of the installed applications are stored at **~/.local/share/applications**
- Downloaded database files are stored at **~/.local/share/bauh/appimage** as **apps.db** and **releases.db**
- Databases are always updated when bauh starts
- Databases updater daemon running every 20 minutes ( it can be customized via the configuration file described below )
- Crashes may happen during an AppImage installation if **AppImageLauncher** is installed. It is advisable to uninstall it and reboot the system before trying to install an application.
- All supported application names can be found at [apps.txt](https://github.com/vinifmor/bauh-files/blob/master/appimage/apps.txt)
- The configuration file is located at **~/.config/bauh/appimage.yml** and it allows the following customizations:
```
db_updater:
  enabled: true  # if 'false': disables the daemon database updater ( bauh will not be able to see if there are updates for your already installed AppImages )
  interval: 1200  # the databases update interval in SECONDS ( 1200 == 20 minutes )
```
- Required dependencies
    - Arch-based systems: **sqlite**, **wget** ( or **aria2** for faster multi-threaded downloads )
    - Debian-based systems: **sqlite3**, **wget** ( or **aria2** for faster multi-threaded downloads )
    - [**fuse**](https://github.com/libfuse/libfuse) may be required to run AppImages on your system
    - P.S: **aria2 will only be used if multi-threaded downloads are enabled**

#### AUR ( arch )
- Only available for **Arch-based systems**
- The user is able to search, install, uninstall, downgrade, launch and retrieve packages history

![aur_search](https://raw.githubusercontent.com/vinifmor/bauh/staging/pictures/aur/search.gif)

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

#### Native Web Applications ( web )
- It allows the installation of native Web applications by typing their addresses / URLs on the search bar

![url_search](https://raw.githubusercontent.com/vinifmor/bauh/staging/pictures/web/url_search.gif)

- It offers the possibility to customize the generated app the way you want:

![options](https://raw.githubusercontent.com/vinifmor/bauh/staging/pictures/web/options.png)

- It provides some suggestions coming with predefined settings, and they also can be retrieved by their names. They are
defined at [suggestions.yml](https://github.com/vinifmor/bauh-files/blob/master/web/suggestions.yml), and downloaded during the application usage.

![suggestions](https://raw.githubusercontent.com/vinifmor/bauh/staging/pictures/web/suggestions.gif)

- It relies on [NodeJS](https://nodejs.org/en/), [Electron](https://electronjs.org/) and [nativefier](https://github.com/jiahaog/nativefier) to do all the magic, but you do not need them installed on your system. An isolated installation environment
will be generated at **~/.local/share/bauh/web/env**.
- The isolated environment is created based on the settings defined in [environment.yml](https://github.com/vinifmor/bauh-files/blob/master/web/environment.yml)
 ( downloaded during runtime ).
- Some applications require Javascript fixes to properly work. If there is a known fix, bauh will download the file from [fix](https://github.com/vinifmor/bauh-files/tree/master/web/fix) and
attach it to the generated app.
- The installed applications are located at **~/.local/share/bauh/installed**.
- A desktop entry / shortcut will be generated for the installed applications at **~/.local/share/application**
- If the Tray Mode **Start Minimized** is defined during the installation setup, a desktop entry will be also generated at **~/.config/autostart**
allowing the application to launch automatically after the system's boot attached to the tray.

![tray_mode](https://raw.githubusercontent.com/vinifmor/bauh/staging/pictures/web/tray.gif)
 
- The configuration file is located at **~/.config/bauh/web.yml** and it allows the following customizations:
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

#### Environment variables / parameters
You can change some application settings via environment variables or arguments (type ```bauh --help``` to get more information).
- `BAUH_TRAY (--tray )`: If the tray icon and update-check daemon should be created. Use `0` (disable, default) or `1` (enable).
- `BAUH_LOGS (--logs )`: enable **bauh** logs (for debugging purposes). Use: `0` (disable, default) or `1` (enable)
- `--reset`: cleans all configurations and cached data stored in the HOME directory

#### General configuration file ( **~/.config/bauh/config.yml** )
```
disk_cache:
  enabled: true  # allows bauh to save applications icons and data to the disk to load them faster when needed
download:
  icons: true # allows bauh to download the applications icons when they are not saved on the disk
  multithreaded: true  # allows bauh to use a multithreaded download client installed on the system to download applications source files faster ( current only **aria2** is supported )
gems: null  # defines the enabled applications types managed by bauh ( a null value means all available ) 
locale: null  # defines a different translation for bauh ( a null value will retrieve the system's default locale )
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
  style: null  # the current QT style set. A null value will map to 'Fusion' or 'Breeze' ( depending on what is installed )  
  table:
    max_displayed: 50  # defines the maximum number of displayed applications on the table.
  tray:  # system tray settings
    default_icon: null  # defines a path to a custom icon
    updates_icon: null  # defines a path to a custom icon indicating updates
updates:
  check_interval: 30  # the updates checking interval in SECONDS

```
#### Tray icons
Priority: 
  1) Icon paths defined in **~/.config/bauh/config.yml**
  2) Icons from the system with the following names: `bauh_tray_default` and `bauh_tray_updates`
  3) Own packaged icons

### How to improve the performance
- Disable the application types you do not want to deal with
- If you don't care about restarting the app every time a new supported package technology is installed, enable `single_dependency_checking`. This can reduce the application response time, since it won't need to recheck if the required technologies are available on your system every time a given action is executed.
- If you don't mind to see the applications icons, you can disable them via `download: icons: false`. The application may have a slight response improvement, since it will reduce the IO and parallelism within it.
- Let the `disk_cache` always enabled so **bauh** does not need to dynamically retrieve data every time you launch it.


### Files and Logs
- Installation logs and temporary files are saved at **/tmp/bauh**
- Some data about your installed applications are stored in **~/.cache/bauh** to load them faster ( default behavior ).

### [bauh-files](https://github.com/vinifmor/bauh-files)
- It is a separate repository with some files downloaded during runtime.

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
