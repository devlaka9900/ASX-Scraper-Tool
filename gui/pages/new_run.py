"""New Run: the three inputs (Project ID, Page URL, Cutoff date) + output folder."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDateEdit, QFileDialog, QHBoxLayout, QLineEdit, QScrollArea, QVBoxLayout, QWidget,
)

from core.pipeline import RunRequest
from gui import validation
from gui.settings import Settings
from gui.widgets.common import IconButton, card, label, primary, repolish

MAX_WIDTH = 760


def _qdate(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


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

        # Project ID
        fl.addWidget(label("Project ID", "h3"))
        self._project = QLineEdit(settings.last_project_id)
        self._project.setPlaceholderText("e.g. AU--ASELA--REG--ASX-0")
        self._project.setAccessibleName("Project ID")
        self._project_err = label("", "error")
        fl.addWidget(self._project)
        fl.addWidget(self._project_err)
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
        self._cutoff = QDateEdit()
        self._cutoff.setCalendarPopup(True)
        self._cutoff.setDisplayFormat("yyyy-MM-dd")
        self._cutoff.setAccessibleName("Cutoff date")
        self._cutoff.setMinimumWidth(160)
        last = settings.last_cutoff
        try:
            start = datetime.strptime(last, "%Y-%m-%d").date() if last else date.today()
        except ValueError:
            start = date.today()
        self._cutoff.setDate(_qdate(start))
        row.addWidget(self._cutoff)
        for text, tip, fn in (
            ("Today", "Set cutoff to today", lambda: date.today()),
            ("30 days ago", "Set cutoff to 30 days ago", lambda: date.today() - timedelta(days=30)),
            ("90 days ago", "Set cutoff to 90 days ago", lambda: date.today() - timedelta(days=90)),
            ("Start of year", "Set cutoff to 1 January this year", lambda: date(date.today().year, 1, 1)),
            ("1 year ago", "Set cutoff to one year ago", lambda: date.today() - timedelta(days=365)),
        ):
            chip = IconButton(text, None)
            chip.setProperty("chip", True)
            chip.setToolTip(tip)
            chip.clicked.connect(lambda _=False, f=fn: self._cutoff.setDate(_qdate(f())))
            row.addWidget(chip)
        row.addStretch(1)
        fl.addLayout(row)
        fl.addWidget(label("A PDF counts as Updated when its date is after 00:00 on the cutoff day.", "hint"))
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

        foot = QHBoxLayout()
        foot.addStretch(1)
        self._start = primary("Start run", "play")
        self._start.setMinimumWidth(160)
        self._start.setMinimumHeight(40)
        self._start.setAccessibleName("Start run")
        self._start.clicked.connect(self._submit)
        foot.addWidget(self._start)
        lay.addLayout(foot)
        lay.addStretch(1)

        for key, edit in (("id", self._project), ("url", self._url), ("out", self._output)):
            edit.textChanged.connect(lambda _t, k=key: self._on_edit(k))
            edit.editingFinished.connect(lambda k=key: self._on_blur(k))
            edit.returnPressed.connect(self._submit)
        self.setTabOrder(self._project, self._url)
        self.setTabOrder(self._url, self._cutoff)
        self.setTabOrder(self._cutoff, self._output)
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
            ("out", self._output, self._output_err, validation.output_dir_error(self._output.text())),
        )
        ok = True
        for key, edit, err_label, error in checks:
            ok &= error is None
            show = error is not None and key in self._touched
            err_label.setText(error if show else "")
            err_label.setVisible(show)
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
        self._touched.update({"id", "url", "out"})
        if not self._validate():
            return
        qd = self._cutoff.date()
        cutoff = datetime(qd.year(), qd.month(), qd.day())
        req = RunRequest(
            project_id=self._project.text().strip(),
            url=self._url.text().strip(),
            cutoff=cutoff,
            output_root=Path(self._output.text().strip()),
            overwrite_downloads=self._redownload.isChecked(),
        )
        self._settings.output_dir = req.output_root
        self._settings.remember_run(req.project_id, req.url, cutoff.strftime("%Y-%m-%d"))
        self.startRequested.emit(req)

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._validate()
        self._start.setToolTip("A run is already in progress" if busy else "")

    def focus_first(self) -> None:
        self._project.setFocus()
