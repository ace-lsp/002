import sys
from PyQt6.QtWidgets import QApplication
from gui import RenamerWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RenamerWindow()
    window.show()
    sys.exit(app.exec())