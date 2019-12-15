
OK_BUTTON = """QPushButton { background: green; color: white; font-weight: bold} 
               QPushButton:disabled { background-color: gray; }
             """

GROUP_BOX = """
QGroupBox {
    font-weight: bold;
    font-size: 12px;
    border: 1px solid silver;
    border-radius: 6px;
    margin-top: 6px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 7px;
    padding: 0px 5px 0px 5px;
}
"""