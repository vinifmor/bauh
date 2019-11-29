# How can I contribute?
Well, you can...
* Report bugs
* Add improvements
* Fix bugs
* Add new translations or fix the current ones

# Reporting bugs
The best means of reporting bugs is by following these basic guidelines:

* First describe in the title of the issue tracker what's gone wrong.
* In the body, explain a basic synopsis of what exactly happens, explain how you got the bug one step at a time. If you're including script output, make sure you run the script with the verbose flag `-v`.
* Explain what you had expected to occur, and what really occurred.
* Optionally, if you want, if you're a programmer, you can try to issue a pull request yourself that fixes the issue.

# Adding improvements
The way to go here is to ask yourself if the improvement would be useful for more than just a singular person, if it's for a certain use case then sure!

* In any pull request, explain thoroughly what changes you made
* Explain why you think these changes could be useful
* If it fixes a bug, be sure to link to the issue itself.
* Follow the [PEP 8](https://www.python.org/dev/peps/pep-0008/) code style to keep the code consistent.

# Adding a new translation
* To add a new translation, you will have to create a file in each directory listed below named as the first two letters of the language in the ISO format (e.g: for 'english' would be 'en'):
- **bauh/view/resources/locale**
- **bauh/gems/appimage/resources/locale**
- **bauh/gems/arch/resources/locale**
- **bauh/gems/flatpak/resources/locale**
- **bauh/gems/snap/resources/locale**
