"""PyQt6 first-start setup wizard."""

import json
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QEvent, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from setup_core import (
    USERNAME_PATTERN,
    SystemSetupBackend,
    load_setup_info,
    load_software_catalog,
    mark_setup_complete,
    save_setup_info,
)


ROOT = Path(__file__).resolve().parent
TRANSLATIONS = ROOT / "locales"
EULA_PATH = ROOT / "eula.txt"


def load_translations():
    translations = {}
    for path in TRANSLATIONS.glob("*.json"):
        with path.open(encoding="utf-8") as translation_file:
            translation = json.load(translation_file)
        if not isinstance(translation, dict):
            raise RuntimeError(f"Translation file {path.name} must contain an object.")
        if not isinstance(translation.get("language_name"), str) or not isinstance(
            translation.get("locale"), str
        ):
            raise RuntimeError(
                f"Translation file {path.name} must define language_name and locale."
            )
        translations[path.stem] = translation
    if "en" not in translations:
        raise RuntimeError("The English translation file is missing.")
    english = translations["en"]
    for language, translation in translations.items():
        if language != "en":
            translations[language] = {**english, **translation}
    return translations


class SetupWorker(QThread):
    progress = pyqtSignal(str)
    progress_value = pyqtSignal(int)
    succeeded = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, backend, data, catalog):
        super().__init__()
        self.backend = backend
        self.data = data
        self.catalog = catalog

    def run(self):
        try:
            self.backend.apply(
                self.data,
                self.catalog,
                self.progress.emit,
                self.progress_value.emit,
            )
        except Exception as error:
            self.failed.emit(str(error))
        else:
            self.succeeded.emit()


class NetworkWorker(QThread):
    completed = pyqtSignal(bool, str)

    def __init__(self, action, ssid="", password=""):
        super().__init__()
        self.action = action
        self.ssid = ssid
        self.password = password

    def run(self):
        try:
            if self.action == "connect":
                SystemSetupBackend.connect_wifi(self.ssid, self.password)
            connected, message = SystemSetupBackend.check_network_connection()
            self.completed.emit(connected, message)
        except (OSError, RuntimeError, ValueError) as error:
            self.completed.emit(False, str(error))


class NetworkDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.setWindowTitle("Connect to the internet")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        title = QLabel("Connect before installing")
        title.setStyleSheet("font-size: 19px; font-weight: 700;")
        layout.addWidget(title)
        explanation = QLabel(
            "Setup needs internet access to refresh package sources and install "
            "the selected software. Check your current connection, or connect "
            "to Wi-Fi below."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        form = QFormLayout()
        self.ssid = QLineEdit()
        self.ssid.setPlaceholderText("Wi-Fi network name")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Wi-Fi password")
        form.addRow("Network name", self.ssid)
        form.addRow("Password", self.password)
        layout.addLayout(form)

        self.status = QLabel("Check the existing connection or connect to Wi-Fi.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        actions = QHBoxLayout()
        self.check_button = QPushButton("Check connection")
        self.connect_button = QPushButton("Connect Wi-Fi")
        self.connect_button.setObjectName("primaryButton")
        actions.addWidget(self.check_button)
        actions.addWidget(self.connect_button)
        layout.addLayout(actions)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        self.continue_button = self.buttons.button(
            QDialogButtonBox.StandardButton.Ok
        )
        self.continue_button.setText("Continue to setup")
        self.continue_button.setEnabled(False)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancel")
        layout.addWidget(self.buttons)

        self.check_button.clicked.connect(self._check_connection)
        self.connect_button.clicked.connect(self._connect_wifi)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self._check_connection()

    def _start_worker(self, action):
        self.check_button.setEnabled(False)
        self.connect_button.setEnabled(False)
        self.continue_button.setEnabled(False)
        self.status.setText("Checking network connection…")
        self.worker = NetworkWorker(
            action,
            self.ssid.text().strip(),
            self.password.text(),
        )
        self.worker.completed.connect(self._network_checked)
        self.worker.start()

    def _check_connection(self):
        self._start_worker("check")

    def _connect_wifi(self):
        if not self.ssid.text().strip() or not self.password.text():
            self.status.setText("Enter the Wi-Fi network name and password.")
            return
        self._start_worker("connect")

    def _network_checked(self, connected, message):
        self.check_button.setEnabled(True)
        self.connect_button.setEnabled(True)
        self.continue_button.setEnabled(connected)
        self.status.setText(
            message
            if connected
            else f"{message} Connect to a network, then check again."
        )


class SetupWizard(QDialog):
    LANGUAGE_PAGE = 0
    KEYBOARD_PAGE = 1
    CLOCK_PAGE = 2
    ACCOUNT_PAGE = 3
    PASSWORD_PAGE = 4
    SCHOOL_PAGE = 5
    SOFTWARE_PAGE = 6
    THEME_PAGE = 7
    DESKTOP_PAGE = 8
    REVIEW_PAGE = 9
    COMPLETE_PAGE = 10
    STEP_COUNT = REVIEW_PAGE + 1

    def __init__(
        self,
        test_mode=False,
        catalog=None,
        parent=None,
        debug_mode=False,
        setup_info_path=None,
        debug_log_path=None,
        completion_marker_path=None,
    ):
        super().__init__(parent)
        self.test_mode = test_mode
        self.debug_mode = debug_mode
        self.completion_marker_path = completion_marker_path
        previous_setup = load_setup_info(setup_info_path)
        if previous_setup.get("already_done", False):
            raise RuntimeError(
                "Setup is already marked complete in setup-info.json. "
                "Remove or reset that file only if you intend to run setup again."
            )
        self.setup_info_path = setup_info_path
        self.catalog = catalog if catalog is not None else load_software_catalog()
        self.translations = load_translations()
        self.language = "en"
        self.backend = SystemSetupBackend(
            simulate=test_mode or debug_mode,
            debug=debug_mode,
            debug_log_path=debug_log_path,
        )
        self.worker = None
        self.setup_finished = False
        self.setup_info_write_failed = False
        self.install_progress = 0
        self.eula_available = False
        self._text_widgets = []
        self.fields = {}
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.kill_switch_shortcut = None
        if self.debug_mode:
            self.kill_switch_shortcut = QShortcut(
                QKeySequence("Ctrl+Shift+Q"), self
            )
            self.kill_switch_shortcut.setContext(
                Qt.ShortcutContext.ApplicationShortcut
            )
            self.kill_switch_shortcut.activated.connect(self.close)
        self.setWindowTitle("Startup Service")
        self.setMinimumSize(860, 620)
        self.setStyleSheet(
            "QDialog { background: #f5f7fb; color: #17243b; }"
            "QLabel { color: #35445c; }"
            "QFrame#sidebar { background: #14213b; border: none; }"
            "QFrame#brandMark { background: #7c6cf2; border-radius: 12px; }"
            "QLabel#brandLetter { color: white; font-size: 22px; font-weight: 800; }"
            "QLabel#brandName { color: #f8fafc; font-size: 16px; font-weight: 700; }"
            "QLabel#brandCaption { color: #a9b5ca; font-size: 11px; }"
            "QLabel#sidebarSection { color: #8492aa; font-size: 10px; "
            "font-weight: 700; letter-spacing: 1px; }"
            "QFrame#stepRow { background: transparent; border: none; border-radius: 9px; }"
            "QFrame#stepRow[active=\"true\"] { background: #263657; }"
            "QLabel#stepNumber { background: #26334c; border-radius: 12px; "
            "color: #b7c2d5; font-size: 11px; font-weight: 700; }"
            "QLabel#stepNumber[active=\"true\"] { background: #8b7cf6; color: white; }"
            "QLabel#stepNumber[complete=\"true\"] { background: #285d56; color: #a7f3d0; }"
            "QLabel#stepName { color: #a9b5ca; font-size: 12px; }"
            "QLabel#stepName[active=\"true\"] { color: white; font-weight: 700; }"
            "QLabel#sidebarNote { color: #8492aa; font-size: 11px; }"
            "QFrame#mainPanel { background: #f5f7fb; border: none; }"
            "QLabel#kicker { color: #7566dc; font-size: 10px; font-weight: 800; "
            "letter-spacing: 1.4px; }"
            "QLabel#heading { color: #17243b; font-size: 27px; font-weight: 750; }"
            "QLabel#subtitle { color: #65738a; font-size: 13px; }"
            "QLabel#stepIndicator { color: #68768b; font-size: 11px; font-weight: 700; }"
            "QFrame#card { background: white; border: 1px solid #e4e9f1; "
            "border-radius: 16px; }"
            "QPushButton { min-height: 40px; padding: 0 19px; border: 1px solid #e0e5ee; "
            "border-radius: 9px; background: white; color: #35445c; font-weight: 650; }"
            "QPushButton:hover { background: #f2f4f9; border-color: #cbd3e0; }"
            "QPushButton:pressed { background: #e8ebf3; }"
            "QPushButton#primaryButton { background: #6558d9; border-color: #6558d9; "
            "color: white; }"
            "QPushButton#primaryButton:hover { background: #5649c7; border-color: #5649c7; }"
            "QPushButton#primaryButton:pressed { background: #4539b0; }"
            "QPushButton:disabled { background: #e5e8ef; border-color: #e5e8ef; "
            "color: #9aa4b4; }"
            "QLineEdit, QComboBox, QPlainTextEdit { min-height: 24px; padding: 9px 11px; "
            "border: 1px solid #dce2eb; border-radius: 8px; background: #fbfcfe; "
            "color: #17243b; selection-background-color: #b9b1ff; }"
            "QLineEdit:hover, QComboBox:hover { border-color: #bac3d2; }"
            "QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus { "
            "border: 1px solid #7669e8; background: white; }"
            "QComboBox QAbstractItemView { background: white; color: #17243b; "
            "selection-background-color: #eeeaff; }"
            "QScrollArea { border: none; background: transparent; }"
            "QScrollArea QWidget { background: transparent; }"
            "QCheckBox { spacing: 9px; color: #17243b; font-weight: 650; }"
            "QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #c8d0dd; "
            "border-radius: 5px; background: white; }"
            "QCheckBox::indicator:hover { border-color: #7669e8; }"
            "QCheckBox::indicator:checked { background: #6558d9; border-color: #6558d9; }"
            "QProgressBar { border: none; border-radius: 4px; background: #e6e9f1; "
            "text-align: center; }"
            "QProgressBar::chunk { background: #7669e8; border-radius: 4px; }"
            "QFrame#appCard { background: #fbfcfe; border: 1px solid #e7ebf2; "
            "border-radius: 10px; }"
            "QLabel#appDescription { color: #758197; font-size: 11px; }"
            "QLabel#eulaError { color: #b4533c; font-size: 11px; }"
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._build_sidebar(root)

        main_panel = QFrame()
        main_panel.setObjectName("mainPanel")
        main_layout = QVBoxLayout(main_panel)
        main_layout.setContentsMargins(38, 30, 38, 24)
        main_layout.setSpacing(16)
        root.addWidget(main_panel, 1)

        self.kicker = QLabel()
        self.kicker.setObjectName("kicker")
        main_layout.addWidget(self.kicker)
        self.heading = QLabel()
        self.heading.setObjectName("heading")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("subtitle")
        self.subtitle.setWordWrap(True)
        main_layout.addWidget(self.heading)
        main_layout.addWidget(self.subtitle)

        progress_row = QHBoxLayout()
        self.step_indicator = QLabel()
        self.step_indicator.setObjectName("stepIndicator")
        progress_row.addWidget(self.step_indicator)
        progress_row.addStretch()
        main_layout.addLayout(progress_row)
        self.step_progress = QProgressBar()
        self.step_progress.setRange(0, self.STEP_COUNT)
        self.step_progress.setTextVisible(False)
        self.step_progress.setFixedHeight(6)
        main_layout.addWidget(self.step_progress)
        self.pages = QStackedWidget()
        main_layout.addWidget(self.pages, 1)

        self._build_language_page()
        self._build_keyboard_page()
        self._build_clock_page()
        self._build_account_page()
        self._build_password_page()
        self._build_school_page()
        self._build_software_page()
        self._build_theme_page()
        self._build_desktop_page()
        self._build_review_page()
        self._build_complete_page()
        self._watch_setup_fields()
        self._build_navigation(main_layout)
        self._translate()
        self._load_eula()
        self._persist_setup_info(status="wizard_started", page_index=0, fatal=True)

    def _watch_setup_fields(self):
        for field in self.fields.values():
            widgets = field.values() if isinstance(field, dict) else (field,)
            for widget in widgets:
                if isinstance(widget, QLineEdit):
                    widget.textChanged.connect(
                        lambda *_: self._persist_setup_info()
                    )
                    widget.installEventFilter(self)
                elif isinstance(widget, QComboBox):
                    widget.currentIndexChanged.connect(
                        lambda *_: self._persist_setup_info()
                    )
                    widget.installEventFilter(self)
                elif isinstance(widget, QCheckBox):
                    widget.toggled.connect(lambda *_: self._persist_setup_info())
        self.eula_checkbox.toggled.connect(lambda *_: self._persist_setup_info())

    def _persist_setup_info(
        self, status="wizard_in_progress", page_index=None, fatal=False
    ):
        if self.setup_info_write_failed:
            return False
        if page_index is None:
            page_index = self.pages.currentIndex()
        step_keys = (
            "step_language",
            "step_keyboard",
            "step_clock",
            "step_account",
            "step_password",
            "step_school",
            "step_software",
            "step_theme",
            "step_desktop",
            "step_review",
        )
        current_stage = (
            self.progress_label.text()
            if hasattr(self, "progress_label") and self.progress_label.isVisible()
            else ""
        )
        try:
            self.setup_info_path = save_setup_info(
                self._setup_data(),
                self.setup_info_path,
                status=status,
                wizard_step=self._t(step_keys[min(page_index, self.REVIEW_PAGE)]),
                install_progress=self.install_progress,
                current_stage=current_stage,
                already_done=not (self.test_mode or self.debug_mode)
                and status == "completed",
            )
        except (OSError, TypeError, ValueError) as error:
            self.setup_info_write_failed = True
            if fatal:
                raise RuntimeError(f"Could not save setup information: {error}") from error
            QMessageBox.warning(
                self,
                self._t("install_failed"),
                f"Could not update the password-free setup summary: {error}",
            )
            return False
        return True

    def eventFilter(self, watched, event):
        if (
            event.type() == QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        ):
            if isinstance(watched, QComboBox) and watched.view().isVisible():
                return super().eventFilter(watched, event)
            index = self.pages.currentIndex()
            if index < self.REVIEW_PAGE:
                self._next()
            elif index == self.REVIEW_PAGE:
                self._start_install()
            return True
        return super().eventFilter(watched, event)

    def _build_sidebar(self, root):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(238)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(20, 26, 18, 22)
        layout.setSpacing(0)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(11)
        mark = QFrame()
        mark.setObjectName("brandMark")
        mark.setFixedSize(40, 40)
        mark_layout = QVBoxLayout(mark)
        mark_layout.setContentsMargins(0, 0, 0, 0)
        letter = QLabel("S")
        letter.setObjectName("brandLetter")
        letter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark_layout.addWidget(letter)
        brand_row.addWidget(mark)

        brand_copy = QVBoxLayout()
        brand_copy.setSpacing(2)
        brand_name = QLabel("Startup Service")
        brand_name.setObjectName("brandName")
        brand_caption = QLabel(self._t("brand_caption"))
        brand_caption.setObjectName("brandCaption")
        self._text_widgets.append((brand_caption, "brand_caption"))
        brand_copy.addWidget(brand_name)
        brand_copy.addWidget(brand_caption)
        brand_row.addLayout(brand_copy)
        brand_row.addStretch()
        layout.addLayout(brand_row)
        layout.addSpacing(38)

        section = QLabel(self._t("setup_steps"))
        section.setObjectName("sidebarSection")
        self._text_widgets.append((section, "setup_steps"))
        layout.addWidget(section)
        layout.addSpacing(13)

        self.sidebar_steps = []
        step_keys = (
            "step_language",
            "step_keyboard",
            "step_clock",
            "step_account",
            "step_password",
            "step_school",
            "step_software",
            "step_theme",
            "step_desktop",
            "step_review",
        )
        for number, key in enumerate(step_keys, start=1):
            row = QFrame()
            row.setObjectName("stepRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(7, 5, 8, 5)
            row_layout.setSpacing(10)

            number_label = QLabel(str(number))
            number_label.setObjectName("stepNumber")
            number_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            number_label.setFixedSize(24, 24)
            name_label = QLabel(self._t(key))
            name_label.setObjectName("stepName")
            name_label.setWordWrap(True)
            self._text_widgets.append((name_label, key))
            row_layout.addWidget(number_label)
            row_layout.addWidget(name_label, 1)
            layout.addWidget(row)
            self.sidebar_steps.append((row, number_label, name_label))

        layout.addStretch()
        note = QLabel(self._t("sidebar_note"))
        note.setObjectName("sidebarNote")
        note.setWordWrap(True)
        self._text_widgets.append((note, "sidebar_note"))
        layout.addWidget(note)
        root.addWidget(sidebar)

    def _card(self):
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(17)
        return frame, layout

    def _label(self, key):
        label = QLabel(self._t(key))
        label.setWordWrap(True)
        self._text_widgets.append((label, key))
        return label

    def _t(self, key):
        return self.translations.get(self.language, self.translations["en"]).get(
            key, self.translations["en"].get(key, key)
        )

    def _translate(self):
        self.setWindowTitle(self._t("window_title"))
        self.kicker.setText(self._t("setup_kicker"))
        self.heading.setText(self._t("heading"))
        self.subtitle.setText(self._t("subtitle"))
        for widget, key in self._text_widgets:
            widget.setText(self._t(key))
        self.back_button.setText(self._t("back"))
        self.next_button.setText(self._t("next"))
        self.start_button.setText(self._t("start_setup"))
        if hasattr(self, "step_indicator"):
            self._update_navigation(self.pages.currentIndex())

    def _build_language_page(self):
        card, layout = self._card()
        layout.addWidget(self._label("language_intro"))
        form = QFormLayout()
        self.fields["language"] = QComboBox()
        for language_code, translation in sorted(
            self.translations.items(),
            key=lambda item: item[1]["language_name"].casefold(),
        ):
            self.fields["language"].addItem(
                translation["language_name"], language_code
            )
        self.fields["language"].setCurrentIndex(
            self.fields["language"].findData(self.language)
        )
        self.fields["language"].currentIndexChanged.connect(self._language_changed)
        form.addRow(self._label("wizard_language"), self.fields["language"])
        layout.addLayout(form)
        layout.addStretch()
        self.pages.addWidget(card)

    def _build_keyboard_page(self):
        card, layout = self._card()
        layout.addWidget(self._label("keyboard_intro"))
        form = QFormLayout()
        self.fields["keyboard"] = QComboBox()
        self.fields["keyboard"].addItem("English (US)", "us")
        self.fields["keyboard"].addItem("Danish", "dk")
        form.addRow(self._label("keyboard"), self.fields["keyboard"])
        layout.addLayout(form)
        layout.addStretch()
        self.pages.addWidget(card)

    def _build_clock_page(self):
        card, layout = self._card()
        layout.addWidget(self._label("clock_intro"))
        form = QFormLayout()
        self.fields["timezone"] = QComboBox()
        self.fields["timezone"].addItems(
            ["Europe/Copenhagen", "Europe/London", "Europe/Berlin", "UTC"]
        )
        self.fields["timezone"].setCurrentText("Europe/Copenhagen")
        form.addRow(self._label("clock"), self.fields["timezone"])
        layout.addLayout(form)
        layout.addStretch()
        self.pages.addWidget(card)

    def _language_changed(self):
        self.language = self.fields["language"].currentData() or "en"
        self._translate()
        self.fields["theme"].setItemText(0, self._t("dark"))
        self.fields["theme"].setItemText(1, self._t("light"))
        self.fields["desktop"].setItemText(0, self._t("xfce_desc"))
        self.fields["desktop"].setItemText(1, self._t("kde_desc"))
        for app in self.catalog:
            checkbox = self.fields["software"][app["id"]]
            suffix = f"  •  {self._t('recommended')}" if app["recommended"] else ""
            checkbox.setText(f"{app['name']}{suffix}")
        if hasattr(self, "eula_text"):
            self._load_eula()

    def _build_account_page(self):
        card, layout = self._card()
        layout.addWidget(self._label("account_intro"))
        form = QFormLayout()
        self.fields["full_name"] = QLineEdit()
        self.fields["username"] = QLineEdit()
        form.addRow(self._label("full_name"), self.fields["full_name"])
        form.addRow(self._label("username"), self.fields["username"])
        layout.addLayout(form)
        layout.addStretch()
        self.pages.addWidget(card)

    def _build_password_page(self):
        card, layout = self._card()
        layout.addWidget(self._label("password_intro"))
        form = QFormLayout()
        self.fields["password"] = QLineEdit()
        self.fields["password"].setEchoMode(QLineEdit.EchoMode.Password)
        self.fields["password_confirm"] = QLineEdit()
        self.fields["password_confirm"].setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(self._label("password"), self.fields["password"])
        form.addRow(self._label("confirm_password"), self.fields["password_confirm"])
        layout.addLayout(form)
        layout.addStretch()
        self.pages.addWidget(card)

    def _build_school_page(self):
        card, layout = self._card()
        layout.addWidget(self._label("school_intro"))
        form = QFormLayout()
        self.fields["school_server"] = QLineEdit()
        self.fields["school_server"].setPlaceholderText(
            "e.g. https://school.example (optional)"
        )
        form.addRow(self._label("school_server"), self.fields["school_server"])
        layout.addLayout(form)
        layout.addWidget(self._label("school_later"))
        layout.addStretch()
        self.pages.addWidget(card)

    def _build_software_page(self):
        card, layout = self._card()
        layout.addWidget(self._label("software_intro"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        software_layout = QVBoxLayout(content)
        self.fields["software"] = {}
        for app in self.catalog:
            app_card = QFrame()
            app_card.setObjectName("appCard")
            app_layout = QVBoxLayout(app_card)
            app_layout.setContentsMargins(14, 11, 14, 11)
            app_layout.setSpacing(5)
            checkbox = QCheckBox(
                f"{app['name']}{'  •  ' + self._t('recommended') if app['recommended'] else ''}"
            )
            checkbox.setProperty("description", app["description"])
            checkbox.setToolTip(app["description"])
            checkbox.setChecked(app["recommended"])
            description = self._label(app["description"])
            description.setObjectName("appDescription")
            app_layout.addWidget(checkbox)
            app_layout.addWidget(description)
            software_layout.addWidget(app_card)
            self.fields["software"][app["id"]] = checkbox
        software_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        self.pages.addWidget(card)

    def _build_theme_page(self):
        card, layout = self._card()
        layout.addWidget(self._label("theme_intro"))
        form = QFormLayout()
        self.fields["theme"] = QComboBox()
        self.fields["theme"].addItem(self._t("dark"), "dark")
        self.fields["theme"].addItem(self._t("light"), "light")
        form.addRow(self._label("theme"), self.fields["theme"])
        layout.addLayout(form)
        layout.addStretch()
        self.pages.addWidget(card)

    def _build_desktop_page(self):
        card, layout = self._card()
        layout.addWidget(self._label("desktop_intro"))
        form = QFormLayout()
        self.fields["desktop"] = QComboBox()
        self.fields["desktop"].addItem(self._t("xfce_desc"), "xfce")
        self.fields["desktop"].addItem(self._t("kde_desc"), "kde")
        form.addRow(self._label("desktop"), self.fields["desktop"])
        layout.addLayout(form)
        layout.addStretch()
        self.pages.addWidget(card)

    def _build_review_page(self):
        card, layout = self._card()
        layout.addWidget(self._label("review_intro"))
        self.progress_label = QLabel()
        self.progress_label.setWordWrap(True)
        layout.addWidget(self.progress_label)
        self.progress = QProgressBar()
        self.progress.setObjectName("installProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p%")
        self.progress.hide()
        layout.addWidget(self.progress)
        self.eula_text = QPlainTextEdit()
        self.eula_text.setReadOnly(True)
        self.eula_text.setMaximumHeight(150)
        layout.addWidget(self.eula_text)
        self.eula_checkbox = QCheckBox()
        self.eula_checkbox.setText(self._t("eula_agree"))
        self.eula_checkbox.stateChanged.connect(self._update_start_enabled)
        layout.addWidget(self.eula_checkbox)
        self._text_widgets.append((self.eula_checkbox, "eula_agree"))
        self.eula_error = QLabel()
        self.eula_error.setObjectName("eulaError")
        self.eula_error.setWordWrap(True)
        layout.addWidget(self.eula_error)
        self.pages.addWidget(card)

    def _build_complete_page(self):
        card, layout = self._card()
        self.complete_status = QLabel()
        self.complete_status.setWordWrap(True)
        layout.addWidget(self.complete_status)
        layout.addStretch()
        self.pages.addWidget(card)

    def _build_navigation(self, root):
        navigation = QHBoxLayout()
        self.back_button = QPushButton()
        self.back_button.setObjectName("secondaryButton")
        self.next_button = QPushButton()
        self.next_button.setObjectName("primaryButton")
        self.start_button = QPushButton()
        self.start_button.setObjectName("primaryButton")
        self.start_button.hide()
        self.reboot_button = QPushButton()
        self.reboot_button.setObjectName("primaryButton")
        self.reboot_button.setText(self._t("reboot"))
        self.reboot_button.hide()
        self.close_button = QPushButton(self._t("close"))
        self._text_widgets.append((self.close_button, "close"))
        self.back_button.clicked.connect(self._back)
        self.next_button.clicked.connect(self._next)
        self.start_button.clicked.connect(self._start_install)
        self.reboot_button.clicked.connect(self._reboot)
        self.close_button.clicked.connect(self.close)
        navigation.addWidget(self.back_button)
        navigation.addStretch()
        navigation.addWidget(self.close_button)
        navigation.addWidget(self.next_button)
        navigation.addWidget(self.start_button)
        navigation.addWidget(self.reboot_button)
        root.addLayout(navigation)
        self.pages.currentChanged.connect(self._update_navigation)
        self._update_navigation(0)

    def _load_eula(self):
        if EULA_PATH.is_file():
            contents = EULA_PATH.read_text(encoding="utf-8").strip()
            self.eula_text.setPlainText(contents or self._t("eula_empty"))
            self.eula_available = bool(contents)
            self.eula_error.setText("" if contents else self._t("eula_empty"))
        else:
            self.eula_available = False
            self.eula_text.setPlainText(self._t("eula_missing"))
            self.eula_error.setText(self._t("eula_missing"))
        if self.test_mode or self.debug_mode:
            self.eula_available = True
            self.eula_text.setPlainText(self._t("preview_eula"))
            self.eula_error.clear()
        self._update_start_enabled()

    def _update_navigation(self, index):
        complete = self.setup_finished
        self.step_indicator.setVisible(not complete)
        self.step_progress.setVisible(not complete)
        self.step_indicator.setText(
            self._t("step_counter").format(
                current=min(index + 1, self.STEP_COUNT), total=self.STEP_COUNT
            )
        )
        self.step_progress.setValue(min(index + 1, self.STEP_COUNT))
        self._update_sidebar(index)
        self.back_button.setVisible(index > 0 and index < self.REVIEW_PAGE)
        self.next_button.setVisible(index < self.REVIEW_PAGE and not complete)
        self.start_button.setVisible(index == self.REVIEW_PAGE and not complete)
        self.next_button.setDefault(index < self.REVIEW_PAGE and not complete)
        self.start_button.setDefault(index == self.REVIEW_PAGE and not complete)
        self.close_button.setVisible(
            index == self.COMPLETE_PAGE
            and complete
            and (self.test_mode or self.debug_mode)
        )
        self.reboot_button.setVisible(
            index == self.COMPLETE_PAGE
            and complete
            and not (self.test_mode or self.debug_mode)
        )
        self._update_start_enabled()
        if index != self.COMPLETE_PAGE:
            self._persist_setup_info(page_index=index)

    def closeEvent(self, event):
        if not (self.test_mode or self.debug_mode):
            event.ignore()
            return
        super().closeEvent(event)

    def _update_sidebar(self, index):
        for step_index, (row, number_label, name_label) in enumerate(
            self.sidebar_steps
        ):
            active = step_index == index
            complete = step_index < index or self.setup_finished
            row.setProperty("active", active)
            number_label.setProperty("active", active)
            number_label.setProperty("complete", complete)
            name_label.setProperty("active", active)
            number_label.setText("✓" if complete else str(step_index + 1))
            for widget in (row, number_label, name_label):
                widget.style().unpolish(widget)
                widget.style().polish(widget)

    def _update_start_enabled(self, *_):
        if hasattr(self, "start_button"):
            self.start_button.setEnabled(
                self.eula_available and self.eula_checkbox.isChecked()
            )

    def _back(self):
        self.pages.setCurrentIndex(max(0, self.pages.currentIndex() - 1))

    def _next(self):
        index = self.pages.currentIndex()
        if index == self.ACCOUNT_PAGE:
            if not self.fields["full_name"].text().strip():
                QMessageBox.warning(self, self._t("validation"), self._t("name_required"))
                return
            if not USERNAME_PATTERN.fullmatch(self.fields["username"].text()):
                QMessageBox.warning(
                    self, self._t("validation"), self._t("username_invalid")
                )
                return
        if index == self.PASSWORD_PAGE:
            if len(self.fields["password"].text()) < 8:
                QMessageBox.warning(
                    self, self._t("validation"), self._t("password_short")
                )
                return
            if self.fields["password"].text() != self.fields["password_confirm"].text():
                QMessageBox.warning(self, self._t("validation"), self._t("password_mismatch"))
                return
        if not self._persist_setup_info(page_index=index):
            return
        self.pages.setCurrentIndex(min(self.REVIEW_PAGE, index + 1))

    def _setup_data(self):
        return {
            "language": self.fields["language"].currentData(),
            "locale": self.translations[
                self.fields["language"].currentData()
            ]["locale"],
            "keyboard": self.fields["keyboard"].currentData(),
            "timezone": self.fields["timezone"].currentText(),
            "full_name": self.fields["full_name"].text(),
            "username": self.fields["username"].text(),
            "password": self.fields["password"].text(),
            "desktop": self.fields["desktop"].currentData(),
            "theme": self.fields["theme"].currentData(),
            "software": [
                app_id
                for app_id, checkbox in self.fields["software"].items()
                if checkbox.isChecked()
            ],
            "school_server": self.fields["school_server"].text().strip(),
            "eula_accepted": self.eula_checkbox.isChecked(),
        }

    def _start_install(self):
        data = self._setup_data()
        if data["password"] != self.fields["password_confirm"].text():
            QMessageBox.warning(self, self._t("validation"), self._t("password_mismatch"))
            return
        if not (self.test_mode or self.debug_mode):
            network_dialog = NetworkDialog(self)
            if network_dialog.exec() != QDialog.DialogCode.Accepted:
                return
        try:
            if not self._persist_setup_info(status="installing"):
                return
        except (OSError, TypeError, ValueError) as error:
            QMessageBox.critical(self, self._t("install_failed"), str(error))
            return
        self.start_button.setEnabled(False)
        self.back_button.setEnabled(False)
        self.install_progress = 0
        self.progress.setValue(0)
        self.progress.show()
        self.progress_label.setText(self._t("starting"))
        self.progress_label.show()
        self.worker = SetupWorker(self.backend, data, self.catalog)
        self.worker.progress.connect(self._install_stage_changed)
        self.worker.progress_value.connect(self._install_progress_changed)
        self.worker.succeeded.connect(self._install_succeeded)
        self.worker.failed.connect(self._install_failed)
        self.worker.start()

    def _install_succeeded(self):
        self.progress.hide()
        self.setup_finished = True
        self.install_progress = 100
        if not (self.test_mode or self.debug_mode):
            try:
                mark_setup_complete(self.completion_marker_path)
            except OSError as error:
                QMessageBox.critical(
                    self,
                    self._t("install_complete"),
                    f"Setup completed, but its one-time completion marker could "
                    f"not be saved: {error}",
                )
        self._persist_setup_info(status="completed")
        if self.debug_mode:
            print("Debug setup finished. No reboot was performed; close the wizard to exit.")
            if self.setup_info_path is not None:
                print(f"Setup summary saved to: {self.setup_info_path}", flush=True)
        self.eula_checkbox.setEnabled(False)
        self.complete_status.setText(
            self._t("preview_complete")
            if self.test_mode or self.debug_mode
            else self._t("install_complete")
        )
        self.start_button.hide()
        self.back_button.hide()
        self.next_button.hide()
        self.reboot_button.setVisible(not (self.test_mode or self.debug_mode))
        self.close_button.show()
        self.close_button.setText(self._t("close"))
        self.close_button.setEnabled(True)
        self.pages.setCurrentIndex(self.COMPLETE_PAGE)
        self._update_navigation(self.COMPLETE_PAGE)

    def _install_failed(self, message):
        self.progress.hide()
        self._persist_setup_info(status="failed")
        self.start_button.setEnabled(True)
        self.back_button.setEnabled(True)
        self.progress_label.setText(self._t("install_failed"))
        QMessageBox.critical(self, self._t("install_failed"), message)

    def _install_stage_changed(self, message):
        self.progress_label.setText(message)
        self._persist_setup_info(status="installing")

    def _install_progress_changed(self, value):
        self.install_progress = value
        self.progress.setValue(value)
        self._persist_setup_info(status="installing")

    def _reboot(self):
        if self.test_mode or self.debug_mode:
            return
        answer = QMessageBox.question(
            self,
            self._t("reboot"),
            self._t("reboot_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            result = subprocess.run(
                ["systemctl", "reboot"], text=True, capture_output=True, check=False
            )
            if result.returncode:
                details = result.stderr.strip() or result.stdout.strip()
                QMessageBox.critical(
                    self,
                    self._t("reboot_failed"),
                    details or self._t("reboot_failed"),
                )


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    test_mode = "--preview" in argv or "--test" in argv
    application = QApplication.instance() or QApplication(sys.argv[:1])
    try:
        from configreader import load_config

        config = load_config()
        debug_mode = config.get("debug_mode", False)
        if not isinstance(debug_mode, bool):
            raise ValueError("The debug_mode setting in config.json must be true or false.")
        wizard = SetupWizard(test_mode=test_mode, debug_mode=debug_mode)
    except (OSError, ValueError, RuntimeError) as error:
        QMessageBox.critical(None, "Startup Service", str(error))
        return 1
    wizard.showFullScreen()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
