import sys
import subprocess

from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from opsle_installer.apt import apt_available, installed_packages, package_install_command
from opsle_installer.catalog import load_catalog
from opsle_installer.terminal import find_terminal


class SoftwareInstaller(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OPSLE Software Installer")
        self.resize(640, 520)
        self.packages = load_catalog()
        self.installed: set[str] = set()
        self.process: QProcess | None = None
        self.operation_running = False

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(QLabel("Select software to install or upgrade on this computer."))

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search software")
        self.search.textChanged.connect(self.refresh_list)
        filters.addWidget(self.search, 1)
        layout.addLayout(filters)

        self.package_list = QListWidget()
        self.package_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        layout.addWidget(self.package_list, 1)

        actions = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh status")
        self.refresh_button.clicked.connect(self.refresh_installed_status)
        self.install_button = QPushButton("Install selected")
        self.install_button.clicked.connect(lambda: self.run_apt_action(upgrade=False))
        self.upgrade_button = QPushButton("Upgrade selected")
        self.upgrade_button.clicked.connect(lambda: self.run_apt_action(upgrade=True))
        actions.addWidget(self.refresh_button)
        actions.addStretch(1)
        actions.addWidget(self.install_button)
        actions.addWidget(self.upgrade_button)
        layout.addLayout(actions)

        self.status = QLabel("Loading installed package status…")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.setCentralWidget(root)
        self.refresh_installed_status()

    def refresh_installed_status(self) -> None:
        if not apt_available():
            self.status.setText("Package installation is available on Debian-based Linux only.")
            self.installed = set()
            self.refresh_list()
            self.install_button.setEnabled(False)
            self.upgrade_button.setEnabled(False)
            return
        try:
            self.installed = installed_packages()
        except (OSError, subprocess.CalledProcessError) as exc:
            QMessageBox.critical(
                self, "Could not read package status", f"Unable to query installed packages: {exc}"
            )
            self.status.setText("Package status could not be loaded.")
            return
        self.refresh_list()
        self.status.setText("Package status refreshed.")

    def refresh_list(self, *_: object) -> None:
        if not hasattr(self, "package_list"):
            return
        query = self.search.text().strip().casefold()
        self.package_list.clear()
        for package in self.packages:
            if query and query not in (
                f"{package.name} {package.package} {package.description}".casefold()
            ):
                continue
            state = "Installed" if package.package in self.installed else "Not installed"
            item = QListWidgetItem(f"{package.name} ({package.package}) — {state}")
            item.setData(Qt.ItemDataRole.UserRole, package.package)
            item.setToolTip(package.description)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.package_list.addItem(item)

    def run_apt_action(self, upgrade: bool) -> None:
        if self.operation_running or not apt_available():
            return

        terminal = find_terminal()
        if not terminal:
            QMessageBox.critical(
                self, "Terminal not found", "Install Konsole or configure x-terminal-emulator."
            )
            return

        selected = [
            self.package_list.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.package_list.count())
            if self.package_list.item(index).checkState() == Qt.CheckState.Checked
        ]
        if upgrade:
            selected = [name for name in selected if name in self.installed]
        if not selected:
            QMessageBox.information(self, "Nothing selected", "Select packages to continue.")
            return

        action = "upgrade" if upgrade else "install"
        answer = QMessageBox.question(
            self,
            f"Confirm {action}",
            f"{action.capitalize()} these packages?\n\n"
            + "\n".join(selected)
            + "\n\nAPT will ask for your password in a new terminal.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        apt_args = package_install_command(selected, upgrade_only=upgrade)
        script = 'apt-get update && "$@"'
        self.process = QProcess(self)
        self.process.setProgram(terminal)
        self.process.setArguments(
            ["-e", "sudo", "sh", "-c", script, "opsle-installer", *apt_args]
        )
        self.process.finished.connect(self.apt_process_finished)
        self.process.errorOccurred.connect(self.apt_process_error)
        self.operation_running = True
        self.set_controls_enabled(False)
        self.status.setText(f"APT is running in a terminal to {action} selected software.")
        self.process.start()

    def set_controls_enabled(self, enabled: bool) -> None:
        self.refresh_button.setEnabled(enabled)
        self.install_button.setEnabled(enabled and apt_available())
        self.upgrade_button.setEnabled(enabled and apt_available())
        self.search.setEnabled(enabled)
        self.package_list.setEnabled(enabled)

    def apt_process_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self.finish_operation(False, "Could not start the terminal.")

    def apt_process_finished(
        self, exit_code: int, exit_status: QProcess.ExitStatus
    ) -> None:
        succeeded = exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit
        self.finish_operation(
            succeeded,
            "Installation completed successfully."
            if succeeded
            else "Installation failed or was cancelled.",
        )

    def finish_operation(self, succeeded: bool, message: str) -> None:
        if not self.operation_running:
            return
        self.operation_running = False
        self.set_controls_enabled(True)
        self.status.setText(message)
        if succeeded:
            self.refresh_installed_status()
            self.status.setText(message)
        QMessageBox.information(
            self,
            "Installation complete" if succeeded else "Installation not completed",
            message,
        )


def run() -> int:
    app = QApplication(sys.argv)
    try:
        window = SoftwareInstaller()
    except ValueError as exc:
        QMessageBox.critical(None, "Invalid software catalog", str(exc))
        return 1
    window.show()
    return app.exec()
