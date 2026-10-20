from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QThread, Qt, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qh_office_optimizer import constants
from qh_office_optimizer.file_rules import file_identity_key, iter_valid_office_file_records
from qh_office_optimizer.formatting import format_size, parse_image_size_label
from qh_office_optimizer.magick import find_and_validate_magick
from qh_office_optimizer.models import FileItem, OptimizationConfig, OutputMode
from qh_office_optimizer.optimizer import CancelToken, optimize_batch
from qh_office_optimizer.output_rules import FatalOutputError


def app_icon() -> QIcon:
    icon_path = Path(__file__).with_name("icon.ico")
    return QIcon(str(icon_path)) if icon_path.is_file() else QIcon()


class SizeItem(QTableWidgetItem):
    def __init__(self, text: str, size: int | None) -> None:
        super().__init__(text)
        self.size = -1 if size is None else size

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, SizeItem):
            return self.size < other.size
        return super().__lt__(other)


class FileTableWidget(QTableWidget):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__(0, 3)
        self._file_drop_enabled = True
        self.setFileDropEnabled(True)
        self.setHorizontalHeaderLabels(["Tên", "Dung lượng cũ", "Sau tối ưu"])
        self.setColumnWidth(0, 600)
        self.setColumnWidth(1, 90)
        self.setColumnWidth(2, 90)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setDragEnabled(False)
        self.setDropIndicatorShown(True)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.ExtendedSelection)
        self.setWordWrap(True)
        self.setSortingEnabled(True)
        self.verticalHeader().setVisible(False)
        self.viewport().installEventFilter(self)

    def setFileDropEnabled(self, enabled: bool) -> None:  # noqa: N802
        self._file_drop_enabled = enabled
        self.setAcceptDrops(enabled)
        self.viewport().setAcceptDrops(enabled)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.viewport() and event.type() in {
            QEvent.Type.DragEnter,
            QEvent.Type.DragMove,
            QEvent.Type.Drop,
        }:
            return self._handle_file_drop_event(event)
        return super().eventFilter(watched, event)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if not self._handle_file_drop_event(event):
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if not self._handle_file_drop_event(event):
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        if not self._handle_file_drop_event(event):
            super().dropEvent(event)

    def _handle_file_drop_event(self, event) -> bool:
        if not self._file_drop_enabled:
            return False
        paths = self._paths_from_mime_data(event.mimeData())
        if not paths:
            return False
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        if event.type() == QEvent.Type.Drop:
            self.files_dropped.emit(paths)
        return True

    @staticmethod
    def _paths_from_mime_data(mime_data) -> list[Path]:
        if not mime_data.hasUrls():
            return []
        return [Path(url.toLocalFile()) for url in mime_data.urls() if url.isLocalFile()]


class HelpDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(constants.HELP_TITLE)
        self.setWindowIcon(app_icon())
        self.setFixedSize(800, 600)

        layout = QVBoxLayout(self)
        text = QPlainTextEdit()
        text.setPlainText(constants.HELP_TEXT)
        text.setReadOnly(True)
        text.setWordWrapMode(text.wordWrapMode())
        layout.addWidget(text)


class FileScanWorker(QThread):
    files_scanned = Signal(list)

    def __init__(self, paths: list[Path], excluded_keys: set[str]) -> None:
        super().__init__()
        self.paths = list(paths)
        self.excluded_keys = set(excluded_keys)

    def run(self) -> None:
        self.files_scanned.emit(iter_valid_office_file_records(self.paths, self.excluded_keys))


class OptimizerWorker(QThread):
    log_message = Signal(str)
    file_updated = Signal(str, int)
    finished_work = Signal()
    fatal_error = Signal()

    def __init__(self, config: OptimizationConfig, magick_path: Path) -> None:
        super().__init__()
        self.config = config
        self.magick_path = magick_path
        self.cancel_token = CancelToken()

    def request_cancel(self) -> None:
        self.cancel_token.request_cancel()

    def run(self) -> None:
        try:
            optimize_batch(
                self.config,
                self.magick_path,
                self.log_message.emit,
                lambda path, size: self.file_updated.emit(str(path), size),
                self.cancel_token,
            )
        except FatalOutputError:
            pass
        except Exception:
            self.fatal_error.emit()
        finally:
            self.finished_work.emit()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(constants.APP_TITLE)
        self.setWindowIcon(app_icon())
        self.setFixedSize(800, 600)

        self.file_items: dict[str, FileItem] = {}
        self.worker: OptimizerWorker | None = None
        self.file_scan_worker: FileScanWorker | None = None
        self.has_completed_run = False
        self.close_after_worker = False

        self.magick_status = find_and_validate_magick()
        self._build_ui()
        self._connect_signals()

        if not self.magick_status.valid:
            self.append_status(constants.WRN001)
        self.update_optimize_button()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)

        controls = QHBoxLayout()
        self.help_button = QPushButton("Hướng dẫn")
        self.size_combo = QComboBox()
        self.size_combo.addItems(constants.IMAGE_SIZE_LABELS)
        self.size_combo.setCurrentText(constants.DEFAULT_IMAGE_SIZE_LABEL)
        self.output_combo = QComboBox()
        self.output_combo.addItems(constants.OUTPUT_LABELS)
        self.output_combo.setCurrentText(constants.DEFAULT_OUTPUT_LABEL)
        self._set_combo_popup_background(self.size_combo)
        self._set_combo_popup_background(self.output_combo)
        self.optimize_button = QPushButton("Tối ưu")
        self.optimize_button.setEnabled(False)

        controls.addWidget(self.help_button)
        controls.addWidget(QLabel("Kích thước ảnh"))
        controls.addWidget(self.size_combo)
        controls.addWidget(QLabel("Đầu ra"))
        controls.addWidget(self.output_combo)
        controls.addStretch(1)
        controls.addWidget(self.optimize_button)
        root.addLayout(controls)

        self.table = FileTableWidget()
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        root.addWidget(self.table, 1)

        self.status_box = QPlainTextEdit()
        self.status_box.setFixedHeight(100)
        self.status_box.setReadOnly(True)
        self.status_box.setUndoRedoEnabled(False)
        root.addWidget(self.status_box)

        self.setCentralWidget(central)

    @staticmethod
    def _set_combo_popup_background(combo: QComboBox) -> None:
        popup_view = QListView(combo)
        popup_view.setStyleSheet("QListView { background-color: #f0f0f0; }")
        combo.setView(popup_view)

    def _connect_signals(self) -> None:
        self.help_button.clicked.connect(self.show_help)
        self.optimize_button.clicked.connect(self.on_optimize_clicked)
        self.table.files_dropped.connect(self.add_dropped_paths)
        self.table.customContextMenuRequested.connect(self.show_table_menu)
        self.size_combo.currentTextChanged.connect(self.on_configuration_changed)
        self.output_combo.currentTextChanged.connect(self.on_configuration_changed)

    def show_help(self) -> None:
        dialog = HelpDialog(self)
        parent_geometry = self.geometry()
        dialog.move(
            parent_geometry.center().x() - dialog.width() // 2,
            parent_geometry.center().y() - dialog.height() // 2,
        )
        dialog.exec()

    def append_status(self, message: str) -> None:
        self.status_box.appendPlainText(message)
        scrollbar = self.status_box.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def add_dropped_paths(self, paths: list[Path]) -> None:
        if self.worker and self.worker.isRunning():
            return
        if self.file_scan_worker and self.file_scan_worker.isRunning():
            return
        self.table.setFileDropEnabled(False)
        self.optimize_button.setEnabled(False)
        self.file_scan_worker = FileScanWorker(paths, set(self.file_items))
        self.file_scan_worker.files_scanned.connect(self.on_files_scanned)
        self.file_scan_worker.finished.connect(self.on_file_scan_finished)
        self.file_scan_worker.start()

    def on_files_scanned(self, records: list[tuple[Path, int]]) -> None:
        self._add_scanned_file_records(records)

    def on_file_scan_finished(self) -> None:
        self.file_scan_worker = None
        if not (self.worker and self.worker.isRunning()):
            self.table.setFileDropEnabled(True)
        self.update_optimize_button()

    def _add_scanned_file_records(self, records: list[tuple[Path, int]]) -> None:
        if not records:
            return
        added_file = False
        self.table.setSortingEnabled(False)
        self.table.setUpdatesEnabled(False)
        for path, size in records:
            key = file_identity_key(path)
            if key in self.file_items:
                continue
            item = FileItem(path=path, old_size=size)
            self.file_items[key] = item
            self._append_file_row(item, resize=False)
            added_file = True
        self.table.resizeRowsToContents()
        self.table.setUpdatesEnabled(True)
        self.table.setSortingEnabled(True)
        if added_file:
            self.has_completed_run = False
        self.update_optimize_button()

    def on_configuration_changed(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        if self.has_completed_run:
            self.has_completed_run = False
        self.update_optimize_button()

    def _append_file_row(self, item: FileItem, resize: bool = True) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        path_item = QTableWidgetItem(str(item.path))
        path_item.setFlags(path_item.flags() & ~Qt.ItemIsEditable)
        old_size_item = SizeItem(format_size(item.old_size), item.old_size)
        old_size_item.setFlags(old_size_item.flags() & ~Qt.ItemIsEditable)
        new_size_item = SizeItem("", None)
        new_size_item.setFlags(new_size_item.flags() & ~Qt.ItemIsEditable)

        self.table.setItem(row, 0, path_item)
        self.table.setItem(row, 1, old_size_item)
        self.table.setItem(row, 2, new_size_item)
        if resize:
            self.table.resizeRowToContents(row)

    def show_table_menu(self, position) -> None:
        if (self.worker and self.worker.isRunning()) or (
            self.file_scan_worker and self.file_scan_worker.isRunning()
        ):
            return
        selected_rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        if not selected_rows:
            return
        menu = QMenu(self)
        delete_action = QAction("Xóa khỏi danh sách", self)
        delete_action.triggered.connect(lambda: self.delete_rows(selected_rows))
        menu.addAction(delete_action)
        menu.exec(self.table.viewport().mapToGlobal(position))

    def delete_rows(self, rows: list[int]) -> None:
        self.table.setSortingEnabled(False)
        for row in rows:
            item = self.table.item(row, 0)
            if item:
                self.file_items.pop(file_identity_key(Path(item.text())), None)
            self.table.removeRow(row)
        self.table.setSortingEnabled(True)
        self.update_optimize_button()

    def update_optimize_button(self) -> None:
        running = bool(self.worker and self.worker.isRunning())
        if running:
            self.optimize_button.setEnabled(True)
            self.optimize_button.setText("Hủy")
            return
        self.optimize_button.setText("Tối ưu")
        self.optimize_button.setEnabled(
            bool(self.file_items)
            and self.magick_status.valid
            and not self.has_completed_run
            and not (self.file_scan_worker and self.file_scan_worker.isRunning())
        )

    def on_optimize_clicked(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.request_cancel()
            self.optimize_button.setEnabled(False)
            return
        if not self.magick_status.valid or not self.magick_status.path:
            self.append_status(constants.WRN001)
            return

        config = OptimizationConfig(
            files=[item.path for item in self.file_items.values()],
            max_edge=parse_image_size_label(self.size_combo.currentText()),
            output_mode=OutputMode.from_label(self.output_combo.currentText()),
        )
        self.set_running_state(True)
        self.worker = OptimizerWorker(config, self.magick_status.path)
        self.worker.log_message.connect(self.append_status)
        self.worker.file_updated.connect(self.update_file_size)
        self.worker.fatal_error.connect(lambda: self.append_status(constants.ERR006))
        self.worker.finished_work.connect(self.on_worker_finished)
        self.worker.start()
        self.update_optimize_button()

    def set_running_state(self, running: bool) -> None:
        self.size_combo.setEnabled(not running)
        self.output_combo.setEnabled(not running)
        self.table.setFileDropEnabled(not running)

    def update_file_size(self, path_text: str, new_size: int) -> None:
        key = file_identity_key(Path(path_text))
        existing = self.file_items.get(key)
        if existing:
            self.file_items[key] = FileItem(existing.path, existing.old_size, new_size)
        for row in range(self.table.rowCount()):
            path_item = self.table.item(row, 0)
            if path_item and file_identity_key(Path(path_item.text())) == key:
                self.table.setItem(row, 2, SizeItem(format_size(new_size), new_size))
                self.table.resizeRowToContents(row)
                break

    def on_worker_finished(self) -> None:
        self.set_running_state(False)
        self.has_completed_run = True
        self.worker = None
        self.update_optimize_button()
        if self.close_after_worker:
            self.close_after_worker = False
            self.close()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.worker and self.worker.isRunning():
            from PySide6.QtWidgets import QMessageBox

            answer = QMessageBox.question(
                self,
                constants.APP_TITLE,
                "Tiến trình đang chạy. Bạn có muốn đóng cửa sổ sau khi xử lý xong tệp hiện tại không?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer == QMessageBox.Yes:
                self.worker.request_cancel()
                self.close_after_worker = True
                self.setEnabled(False)
                event.ignore()
            else:
                event.ignore()
            return
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    app.setWindowIcon(app_icon())
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
