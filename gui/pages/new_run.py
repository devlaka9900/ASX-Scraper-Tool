"""New Run: DocumentId (+ optional Startpoint), Page URL, Cutoff date, output folder."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QVBoxLayout,
    QWidget,
)

from core.pipeline import RunRequest
from gui import icons, theme, validation
from gui.settings import Settings
from gui.widgets.common import ElidedLabel, IconButton, card, divider, label, primary, repolish, secondary
from gui.widgets.date_input import DateInput

MAX_WIDTH = 760

DEV_NOTE = (
    "If the cutoff date is unavailable or difficult to determine, derive it from the Waivers section: "
    "use the date of the most recent document in that section, which reflects the latest version "
    "delivered by CUBE."
)


class NewRunPage(QWidget):
    startRequested = Signal(object)          # RunRequest

    def __init__(self, settings: Settings, parent: QWidget | None = None):
        super().__init__(parent)
        self._settings = settings
        self._touched: set[str] = set()
        self._busy = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)
        host = QWidget()
        scroll.setWidget(host)
        host_lay = QHBoxLayout(host)
        host_lay.setContentsMargins(32, 32, 32, 32)
        host_lay.addStretch(1)
        column = QWidget()
        column.setMaximumWidth(MAX_WIDTH)
        column.setMinimumWidth(480)
        host_lay.addWidget(column, 100)
        host_lay.addStretch(1)

        lay = QVBoxLayout(column)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(18)
        lay.addWidget(label("New run", "h1"))
        lay.addWidget(label("Scrape an ASX page, download every PDF and find out which were updated "
                            "after your cutoff date.", "secondary", wrap=True))

        form = card()
        fl = QVBoxLayout(form)
        fl.setContentsMargins(24, 22, 24, 22)
        fl.setSpacing(6)

        # DocumentId (stored internally as project_id)
        fl.addWidget(label("DocumentId", "h3"))
        self._project = QLineEdit(settings.last_project_id)
        self._project.setPlaceholderText("e.g. AU--ASELA--REG--ASX-0")
        self._project.setAccessibleName("DocumentId")
        self._project_err = label("", "error")
        fl.addWidget(self._project)
        fl.addWidget(self._project_err)
        fl.addSpacing(8)

        # Startpoint — optional free text, shown next to the DocumentId on the app screens
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(label("Startpoint", "h3"))
        head.addWidget(label("optional", "caption"))
        head.addStretch(1)
        fl.addLayout(head)
        self._startpoint = QLineEdit()
        self._startpoint.setMaxLength(validation.STARTPOINT_MAX)
        self._startpoint.setPlaceholderText("Optional — e.g. a starting chapter, document or reference")
        self._startpoint.setAccessibleName("Startpoint (optional)")
        self._startpoint.setClearButtonEnabled(True)
        fl.addWidget(self._startpoint)
        fl.addSpacing(8)

        # URL
        fl.addWidget(label("Page URL", "h3"))
        self._url = QLineEdit(settings.last_url)
        self._url.setPlaceholderText("https://www.asx.com.au/about/regulation/rules-guidance-notes-and-waivers/…")
        self._url.setAccessibleName("Page URL")
        self._url_err = label("", "error")
        fl.addWidget(self._url)
        fl.addWidget(self._url_err)
        fl.addSpacing(8)

        # Cutoff
        fl.addWidget(label("Cutoff date", "h3"))
        row = QHBoxLayout()
        row.setSpacing(10)
        self._cutoff = DateInput()
        self._cutoff.set_accessible_name("Cutoff date")
        self._cutoff.setMaximumWidth(260)
        row.addWidget(self._cutoff)
        row.addStretch(1)
        fl.addLayout(row)
        self._cutoff_err = label("", "error")
        fl.addWidget(self._cutoff_err)
        fl.addWidget(label("Type the date as YYYY-MM-DD or use the calendar. A PDF counts as Updated when "
                           "its date is after 00:00 on the cutoff day.", "hint", wrap=True))
        fl.addSpacing(8)

        # Output folder
        fl.addWidget(label("Output folder", "h3"))
        orow = QHBoxLayout()
        orow.setSpacing(10)
        self._output = QLineEdit(str(settings.output_dir))
        self._output.setAccessibleName("Output folder")
        orow.addWidget(self._output, 1)
        browse = IconButton("Browse…", "folder")
        browse.clicked.connect(self._browse)
        orow.addWidget(browse)
        fl.addLayout(orow)
        self._output_err = label("", "error")
        fl.addWidget(self._output_err)
        self._existing = label("", "hint", wrap=True)
        fl.addWidget(self._existing)
        fl.addSpacing(4)

        self._redownload = QCheckBox("Re-download files that already exist")
        self._redownload.setToolTip("Off: PDFs already in downloads/ are reused (same as the command-line tool).")
        fl.addWidget(self._redownload)
        lay.addWidget(form)

        # developer note
        note = card("flat")
        nl = QHBoxLayout(note)
        nl.setContentsMargins(16, 12, 16, 12)
        nl.setSpacing(12)
        self._note_icon = QLabel()
        self._note_icon.setFixedSize(20, 20)
        nl.addWidget(self._note_icon, 0, Qt.AlignmentFlag.AlignTop)
        nbox = QVBoxLayout()
        nbox.setSpacing(2)
        nbox.addWidget(label("Developer note", "h3"))
        note_text = label(DEV_NOTE, "secondary", wrap=True)
        note_text.setAccessibleName("Developer note")
        nbox.addWidget(note_text)
        nl.addLayout(nbox, 1)
        theme.bus.changed.connect(self._refresh_note_icon)
        self._refresh_note_icon()

        foot = QHBoxLayout()
        foot.addStretch(1)
        self._start = primary("Start run", "play")
        self._start.setMinimumWidth(160)
        self._start.setMinimumHeight(40)
        self._start.setAccessibleName("Start run")
        self._start.clicked.connect(self._submit)
        foot.addWidget(self._start)
        lay.addLayout(foot)           # Start stays above the fold at the minimum window size …
        lay.addWidget(note)           # … the developer note sits below it
        lay.addStretch(1)

        for key, edit in (("id", self._project), ("url", self._url), ("out", self._output)):
            edit.textChanged.connect(lambda _t, k=key: self._on_edit(k))
            edit.editingFinished.connect(lambda k=key: self._on_blur(k))
            edit.returnPressed.connect(self._submit)
        self._startpoint.returnPressed.connect(self._submit)
        self._cutoff.changed.connect(lambda: self._on_edit("date"))
        self._cutoff.blurred.connect(lambda: self._on_blur("date"))
        self._cutoff.returnPressed.connect(self._submit)
        self.setTabOrder(self._project, self._startpoint)
        self.setTabOrder(self._startpoint, self._url)
        self.setTabOrder(self._url, self._cutoff.edit())
        self.setTabOrder(self._cutoff.edit(), self._cutoff.button())
        self.setTabOrder(self._cutoff.button(), self._output)
        self.setTabOrder(self._output, browse)
        self.setTabOrder(browse, self._redownload)
        self.setTabOrder(self._redownload, self._start)
        self._validate()

    # ---- validation -------------------------------------------------------- #

    def _on_edit(self, key: str) -> None:
        self._validate()

    def _on_blur(self, key: str) -> None:
        self._touched.add(key)
        self._validate()

    def _validate(self) -> bool:
        checks = (
            ("id", self._project, self._project_err, validation.project_id_error(self._project.text())),
            ("url", self._url, self._url_err, validation.url_error(self._url.text())),
            ("date", self._cutoff, self._cutoff_err, self._cutoff.error()),
            ("out", self._output, self._output_err, validation.output_dir_error(self._output.text())),
        )
        ok = True
        for key, edit, err_label, error in checks:
            ok &= error is None
            show = error is not None and key in self._touched
            err_label.setText(error if show else "")
            err_label.setVisible(show)
            if isinstance(edit, DateInput):
                edit.set_invalid(show)
            else:
                edit.setProperty("invalid", show)
                repolish(edit)
        self._start.setEnabled(ok and not self._busy)
        self._update_existing_notice()
        return ok

    def _update_existing_notice(self) -> None:
        pid = self._project.text().strip()
        out = self._output.text().strip()
        notes: list[str] = []
        if pid and out and validation.project_id_error(pid) is None:
            if (Path(out) / pid).exists():
                notes.append(f"A folder for “{pid}” already exists here. Existing PDFs are reused (tick "
                             "re-download to refresh them) and the reports are overwritten.")
            long_warning = validation.long_path_warning(out, pid)
            if long_warning:
                notes.append(long_warning)
        self._existing.setText("\n".join(notes))
        self._existing.setVisible(bool(notes))

    # ---- actions ------------------------------------------------------------ #

    def _browse(self) -> None:
        start = self._output.text().strip() or str(self._settings.output_dir)
        chosen = QFileDialog.getExistingDirectory(self, "Choose output folder", start)
        if chosen:
            self._touched.add("out")
            self._output.setText(chosen)

    def _submit(self) -> None:
        if self._busy:                   # Enter in a field must not bypass the disabled button
            return
        self._touched.update({"id", "url", "date", "out"})
        if not self._validate():
            return
        cutoff = self._cutoff.date()          # validated above, so never None here
        req = RunRequest(
            project_id=self._project.text().strip(),
            url=self._url.text().strip(),
            cutoff=cutoff,
            output_root=Path(self._output.text().strip()),
            overwrite_downloads=self._redownload.isChecked(),
            startpoint=validation.clean_startpoint(self._startpoint.text()),
        )
        if not self._confirm(req):            # Back to edit: nothing saved, form untouched
            return
        self._settings.output_dir = req.output_root
        self._settings.remember_run(req.project_id, req.url, cutoff.strftime("%Y-%m-%d"))
        self.startRequested.emit(req)

    def _confirm(self, req: RunRequest) -> bool:
        """Show the entered details for review; True = start the run (patchable in tests)."""
        return RunConfirmDialog(req, self.window()).exec() == QDialog.DialogCode.Accepted

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._validate()
        self._start.setToolTip("A run is already in progress" if busy else "")

    def focus_first(self) -> None:
        self._project.setFocus()

    def _refresh_note_icon(self) -> None:
        self._note_icon.setPixmap(icons.pixmap("alert", theme.current()["accent_ink"], 20,
                                               self.devicePixelRatioF(), 1.8))


class RunConfirmDialog(QDialog):
    """Read-only summary of a RunRequest: Accepted = start the run, Rejected = back to the form."""

    def __init__(self, req: RunRequest, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Confirm run")
        self.setModal(True)
        self.setMinimumWidth(560)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(14)
        lay.addWidget(label("Confirm run", "h1"))
        lay.addWidget(label("Check the details below, then start the run.", "secondary", wrap=True))

        box = card("flat")
        grid = QGridLayout(box)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        rows = (
            ("DocumentId", req.project_id),
            ("Startpoint", req.startpoint or "—"),
            ("Page URL", req.url),
            ("Cutoff date", req.cutoff.strftime("%Y-%m-%d")),
            ("Output folder", str(req.output_root)),
            ("Re-download", "Yes" if req.overwrite_downloads else "No"),
        )
        for i, (name, value) in enumerate(rows):
            grid.addWidget(label(name, "h3"), i, 0, Qt.AlignmentFlag.AlignTop)
            val = ElidedLabel(value)
            val.setAccessibleName(f"{name} value")
            grid.addWidget(val, i, 1)
        lay.addWidget(box)
        lay.addWidget(divider())

        foot = QHBoxLayout()
        foot.setSpacing(10)
        foot.addStretch(1)
        back = secondary("Back to edit")
        back.setAccessibleName("Back to edit")
        back.clicked.connect(self.reject)
        self._confirm_btn = primary("Confirm and start", "play")
        self._confirm_btn.setAccessibleName("Confirm and start")
        self._confirm_btn.setMinimumHeight(40)
        self._confirm_btn.setDefault(True)
        self._confirm_btn.clicked.connect(self.accept)
        foot.addWidget(back)
        foot.addWidget(self._confirm_btn)
        lay.addLayout(foot)
        self._confirm_btn.setFocus()
