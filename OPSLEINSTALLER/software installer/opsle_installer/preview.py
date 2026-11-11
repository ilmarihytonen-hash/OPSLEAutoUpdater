import sys

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget

from opsle_installer.localization import translate


PREVIEW_STEPS = (
    (0, "Checking software sources..."),
    (15, "Installing mandatory software updates..."),
    (42, "Installing mandatory software updates..."),
    (68, "Installing system updates..."),
    (91, "Installing system updates..."),
    (100, "Mandatory updates complete. Restarting..."),
)


class UpdatePreview(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OPSLE Update Screen Preview")
        self.setMinimumSize(720, 420)
        self.setStyleSheet(
            "QWidget { background-color: #101820; color: #f3f6f8; }"
            "QLabel#title { font-size: 24px; font-weight: 600; }"
            "QLabel#status { font-size: 16px; color: #d3dce2; }"
            "QLabel#warning { font-size: 18px; font-weight: 600; color: #ffd166; }"
            "QLabel#hint { font-size: 12px; color: #94a3ad; }"
            "QProgressBar { border: 1px solid #71808a; border-radius: 6px; "
            "background: #26343e; text-align: center; min-height: 24px; }"
            "QProgressBar::chunk { background-color: #42a5f5; border-radius: 5px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(72, 56, 72, 32)
        layout.addStretch(2)

        title = QLabel(translate("OPSLE system update"))
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        warning = QLabel(translate("Do not power off your computer."))
        warning.setObjectName("warning")
        warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(warning)

        self.status = QLabel()
        self.status.setObjectName("status")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setMinimumHeight(48)
        layout.addWidget(self.status)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(True)
        layout.addWidget(self.progress)
        layout.addStretch(2)

        hint = QLabel(
            translate("Preview only — no updates will be installed. Esc closes; F5 replays.")
        )
        hint.setObjectName("hint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        self.timer = QTimer(self)
        self.timer.setInterval(1400)
        self.timer.timeout.connect(self.show_next_step)
        self.step_index = 0
        self.show_step(0)
        self.timer.start()

    def show_step(self, index: int) -> None:
        progress, message = PREVIEW_STEPS[index]
        self.progress.setValue(progress)
        self.status.setText(translate(message))

    def show_next_step(self) -> None:
        if self.step_index + 1 >= len(PREVIEW_STEPS):
            self.timer.stop()
            return
        self.step_index += 1
        self.show_step(self.step_index)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        if event.key() == Qt.Key.Key_F5:
            self.timer.stop()
            self.step_index = 0
            self.show_step(self.step_index)
            self.timer.start()
            return
        super().keyPressEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    window = UpdatePreview()
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
