from PyQt5.QtWidgets import QWidget, QApplication


def centralize(widget: QWidget):
    geo = widget.frameGeometry()
    screen = QApplication.desktop().screenNumber(QApplication.desktop().cursor().pos())
    center_point = QApplication.desktop().screenGeometry(screen).center()
    geo.moveCenter(center_point)
    widget.move(geo.topLeft())
