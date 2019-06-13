## fpakman
Graphical interface for Flatpak application management. It is a tray icon to let the user known when new updates are available.
It has also a management window allowing the user to see all installed apllications and update them.

### Developed with:
- Python3 and QT 5.

### Requirements
- Python >= 3.5
- qt5 packages
- libappindicator3 (for GTK3 desktop environments)
- python3-venv (for Debian based distros -> Ubuntu, Linux Mint, ...)

## Installation script
You can install the application without compromising your system via the provided installation script called 'sandbox_installer.py'.
Type in the terminal: sudo python3 sandbox_installer.py. If you want to uninstall the application, just call the script the same way.

### Settings
You can change some application settings via environment variables:
- **FPAKMAN_UPDATE_NOTIFICATION: enable or disable system updates notifications. Use 0 (disable) or 1 (enable, default).
- **FPAKMAN_CHECK_INTERVAL**: define the updates check interval in seconds. Default: 60.

### Roadmap
- Show update commands
- Search and install applications.
