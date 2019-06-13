## fpakman
Graphical interface for Flatpak application management. It is a tray icon to let the user known when new updates are available.
It has also a management window allowing the user to see all installed apllications and update them.

### Technologies:
- Python3 and QT 5.

## Settings
You can change some application settings via environment variables:
- **FPAKMAN_UPDATE_NOTIFICATION: enable or disable system updates notifications. Use 0 (disable) or 1 (enable, default).
- **FPAKMAN_CHECK_INTERVAL**: define the updates check interval in seconds. Default: 60.

## Installation script
You can install the application without compromising your system via the provided installation script called 'sandbox_installer.py'.
Type in the terminal: sudo python3 sandbox_installer.py. If you want to uninstall the application, just call the script the same way.

### Roadmap
- Test installer for Ubuntu
- Locales
- Search and install applications.