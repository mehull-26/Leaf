# gui.py — PDF Outline Editor (Qt6 + PyPDF)
# Requirements:
#   pip install PySide6 pypdf
#
# Notes:
#   • Uses PyPDF (pure Python). Outlines persist on save/reopen.
#   • Offset is global: Actual = Logical + Offset.
#   • On open, offset resets to 0 so new files show (1/1).
#   • Save avoids duplicate outlines by rebuilding the writer.
#   • Move is transaction-safe and prevents moving into own subtree.
#   • Logical/Actual columns shown; Actual is greyed out.
#   • Filename badge is light blue when clean, light red when dirty.

import sys
from dataclasses import dataclass, field
from typing import List, Optional

from PySide6.QtCore import Qt, QModelIndex
from PySide6.QtGui import QAction, QIcon, QColor, QBrush
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QTreeWidget, QTreeWidgetItem, QSpinBox,
    QInputDialog, QMessageBox, QDialog, QDialogButtonBox, QFormLayout,
    QComboBox
)

# ---------------------------
# Data model (shared with CLI)
# ---------------------------

try:
    from pypdf import PdfReader, PdfWriter
except ImportError as e:
    raise SystemExit("Install dependency first:\n  pip install pypdf")


@dataclass
class OutlineNode:
    id: str
    title: str
    page_logical: Optional[int] = None
    children: List["OutlineNode"] = field(default_factory=list)
    is_group: bool = False


def enumerate_tree(nodes: List[OutlineNode]) -> List[OutlineNode]:
    out = []

    def walk(lst):
        for n in lst:
            out.append(n)
            if n.children:
                walk(n.children)
    walk(nodes)
    return out


def assign_ids(nodes: List[OutlineNode]) -> None:
    i = 1
    for n in enumerate_tree(nodes):
        n.id = f"n{i}"
        i += 1


class PdfOutlineModel:
    def __init__(self):
        self.filename: Optional[str] = None
        self.reader: Optional[PdfReader] = None
        self.writer: Optional[PdfWriter] = None
        self.root: List[OutlineNode] = []
        self.offset: int = 0
        self.id_map = {}
        self._dirty: bool = False

    # --- file ops ---
    def open(self, path: str):
        self.reader = PdfReader(path)
        self.writer = PdfWriter()
        for p in self.reader.pages:
            self.writer.add_page(p)
        self.filename = path
        self.root = self._import_outlines()
        assign_ids(self.root)
        self._rebuild_id_map()
        self.offset = 0
        self._dirty = False

    def _ensure_open(self):
        if not (self.reader and self.writer and self.filename):
            raise RuntimeError("No PDF open")

    def close(self):
        self.reader = None
        self.writer = None
        self.filename = None
        self.root = []
        self.id_map = {}
        self.offset = 0
        self._dirty = False

    def save(self):
        self._ensure_open()
        self._export_outlines()
        with open(self.filename, "wb") as f:
            self.writer.write(f)
        self._dirty = False

    def saveas(self, path: str):
        self._ensure_open()
        self._export_outlines()
        with open(path, "wb") as f:
            self.writer.write(f)
        self.filename = path
        self._dirty = False

    # --- import/export outlines ---
    def _import_outlines(self) -> List[OutlineNode]:
        if not self.reader:
            return []
        try:
            raw = self.reader.outline
        except Exception:
            raw = []

        def conv(items):
            out: List[OutlineNode] = []
            for it in items:
                if isinstance(it, list):
                    if out:
                        out[-1].children = conv(it)
                        out[-1].is_group = True
                    continue
                title = getattr(it, "title", str(it)) or "Untitled"
                try:
                    actual_1 = self.reader.get_destination_page_number(it) + 1
                except Exception:
                    actual_1 = None
                node = OutlineNode(
                    id="",
                    title=title,
                    page_logical=(actual_1 if actual_1 else None),
                    children=[],
                    is_group=(actual_1 is None),
                )
                out.append(node)
            return out

        return conv(raw)

    def _export_outlines(self):
        if not self.writer:
            return
        old_pages = list(self.writer.pages)
        self.writer = PdfWriter()
        for p in old_pages:
            self.writer.add_page(p)

        def build(nodes: List[OutlineNode], parent=None):
            for n in nodes:
                if n.page_logical is not None:
                    actual_idx = n.page_logical + self.offset - 1
                    if actual_idx < 0 or actual_idx >= len(self.writer.pages):
                        raise ValueError(f"Page {actual_idx+1} out of range.")
                    dest_page = self.writer.pages[actual_idx]
                    new_parent = self.writer.add_outline_item(
                        n.title, dest_page, parent=parent)
                else:
                    new_parent = self.writer.add_outline_item(
                        n.title, None, parent=parent)
                if n.children:
                    build(n.children, parent=new_parent)
        build(self.root)

    # --- id/path helpers ---
    def _rebuild_id_map(self):
        self.id_map = {n.id: n for n in enumerate_tree(self.root)}

    def _find_parent_and_index(self, target: OutlineNode):
        def walk(lst):
            for i, n in enumerate(lst):
                if n is target:
                    return lst, i
                got = walk(n.children)
                if got:
                    return got
            return None
        return walk(self.root)

    def _is_descendant(self, root: "OutlineNode", maybe_child: "OutlineNode") -> bool:
        stack = list(root.children)
        while stack:
            n = stack.pop()
            if n is maybe_child:
                return True
            stack.extend(n.children)
        return False

    # --- commands ---
    # --- new: rename & clear_all (CLI-compatible) ---

    def rename(self, tok: str, new_title: str):
        """
        Rename a node, where tok can be an id ('n7') or a path ('1>2>1')
        to match CLI semantics. GUI can just pass node.id here.
        """
        # if you already have _get_ref from CLI path logic, use it:
        try:
            # id or path, if present in your GUI model
            node = self._get_ref(tok)
        except AttributeError:
            # GUI build typically has no _get_ref; we accept only ids here
            node = self.id_map.get(tok)
            if node is None:
                raise ValueError(f"Unknown id or path: {tok}")

        node.title = new_title
        assign_ids(self.root)
        self._rebuild_id_map()
        self._dirty = True

    def clear_all(self):
        """Remove ALL outlines (with GUI doing the confirmation)."""
        self.root = []
        assign_ids(self.root)
        self._rebuild_id_map()
        self._dirty = True

    def add_outline(self, title: str, page: int, parent: Optional[OutlineNode] = None, index: Optional[int] = None):
        node = OutlineNode("", title, int(page), [], False)
        target_list = parent.children if parent else self.root
        insert_at = len(target_list) if index is None else int(index)
        if insert_at < 0 or insert_at > len(target_list):
            raise ValueError("Insert index out of range")
        target_list.insert(insert_at, node)
        assign_ids(self.root)
        self._rebuild_id_map()
        self._dirty = True
        return node

    def add_group(self, name: str, parent: Optional[OutlineNode] = None, index: Optional[int] = None):
        node = OutlineNode("", name, None, [], True)
        target_list = parent.children if parent else self.root
        insert_at = len(target_list) if index is None else int(index)
        if insert_at < 0 or insert_at > len(target_list):
            raise ValueError("Insert index out of range")
        target_list.insert(insert_at, node)
        assign_ids(self.root)
        self._rebuild_id_map()
        self._dirty = True
        return node

    def remove(self, node: OutlineNode):
        pair = self._find_parent_and_index(node)
        if not pair:
            raise ValueError("Node not found")
        parent_list, idx = pair
        del parent_list[idx]
        assign_ids(self.root)
        self._rebuild_id_map()
        self._dirty = True

    def move(self, node: OutlineNode, dest_parent: Optional[OutlineNode], index: Optional[int]):
        # 1: resolve source (no pop yet)
        src_pair = self._find_parent_and_index(node)
        if not src_pair:
            raise ValueError("Node not found")
        src_list, src_idx = src_pair

        # 2: destination list
        dest_list = dest_parent.children if dest_parent else self.root

        # prevent moving into own subtree
        if dest_parent and (node is dest_parent or self._is_descendant(node, dest_parent)):
            raise ValueError(
                "Cannot move a node into itself or its descendants")

        # 3: index
        insert_at = len(dest_list) if index is None else int(index)
        if insert_at < 0 or insert_at > len(dest_list):
            raise ValueError("Destination index out of range")

        if dest_list is src_list and insert_at > src_idx:
            insert_at -= 1
        if dest_list is src_list and insert_at == src_idx:
            return  # no-op

        # 4: mutate
        moved = src_list.pop(src_idx)
        dest_list.insert(insert_at, moved)
        assign_ids(self.root)
        self._rebuild_id_map()
        self._dirty = True

    def set_page(self, node: OutlineNode, page: int):
        node.page_logical = int(page)
        node.is_group = False
        assign_ids(self.root)
        self._rebuild_id_map()
        self._dirty = True

    def clear_page(self, node: OutlineNode):
        node.page_logical = None
        node.is_group = True
        assign_ids(self.root)
        self._rebuild_id_map()
        self._dirty = True

    def offset_set(self, val: int):
        self.offset = int(val)
        self._dirty = True

    def offset_clear(self):
        self.offset = 0
        self._dirty = True

# ---------------------------
# Move dialog
# ---------------------------


class MoveDialog(QDialog):
    def __init__(self, parent, model: PdfOutlineModel, current: OutlineNode):
        super().__init__(parent)
        self.setWindowTitle("Move")
        self.model = model
        self.current = current
        self.dest: Optional[OutlineNode] = None
        self.index: Optional[int] = None

        layout = QFormLayout(self)

        self.dest_combo = QComboBox(self)
        self.dest_combo.addItem("<root>", None)
        # flatten for simple selection
        flat = enumerate_tree(self.model.root)
        for n in flat:
            self.dest_combo.addItem(f"{n.id} • {n.title}", n)
        layout.addRow("Destination parent:", self.dest_combo)

        self.index_spin = QSpinBox(self)
        self.index_spin.setMinimum(0)
        self.index_spin.setMaximum(99999)
        layout.addRow("Insert index (0-based):", self.index_spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def accept(self):
        self.dest = self.dest_combo.currentData()
        self.index = int(self.index_spin.value())
        super().accept()

# ---------------------------
# Main window (GUI)
# ---------------------------


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.model = PdfOutlineModel()
        self.setWindowTitle("PDF Outline Editor")

        # Top badge: filename with clean/dirty color
        self.file_badge = QLabel("[no-file]")
        self.file_badge.setStyleSheet(
            # light blue when clean
            "QLabel { color: #66aaff; font-weight: 600; }")

        self.offset_spin = QSpinBox()
        self.offset_spin.setMinimum(-10000)
        self.offset_spin.setMaximum(10000)
        self.offset_spin.setValue(0)
        self.offset_spin.valueChanged.connect(self.on_offset_changed)

        offset_lbl = QLabel("Offset:")
        topbar = QHBoxLayout()
        topbar.addWidget(self.file_badge, 1)
        topbar.addWidget(offset_lbl)
        topbar.addWidget(self.offset_spin)

        # Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Title", "Logical", "Actual", "ID"])
        self.tree.setColumnWidth(0, 350)
        self.tree.itemSelectionChanged.connect(self.on_selection_changed)

        # Buttons
        btn_open = QPushButton("Open")
        btn_save = QPushButton("Save")
        btn_saveas = QPushButton("Save As")
        btn_close = QPushButton("Close")

        btn_add = QPushButton("Add")
        btn_grp = QPushButton("Grp")
        btn_remove = QPushButton("Remove")
        btn_move = QPushButton("Move")
        btn_set = QPushButton("Set Page")
        btn_clear = QPushButton("Clear Page")
        btn_help = QPushButton("Help")

        btn_rename = QPushButton("Rename")
        btn_clear_all = QPushButton("Clear All")

        btn_rename.clicked.connect(self.act_rename)
        btn_clear_all.clicked.connect(self.act_clear_all)

        btn_open.clicked.connect(self.act_open)
        btn_save.clicked.connect(self.act_save)
        btn_saveas.clicked.connect(self.act_saveas)
        btn_close.clicked.connect(self.act_close)

        btn_add.clicked.connect(self.act_add)
        btn_grp.clicked.connect(self.act_grp)
        btn_remove.clicked.connect(self.act_remove)
        btn_move.clicked.connect(self.act_move)
        btn_set.clicked.connect(self.act_setpage)
        btn_clear.clicked.connect(self.act_clearpage)
        btn_help.clicked.connect(self.act_help)

        btnbar1 = QHBoxLayout()
        for b in (btn_open, btn_save, btn_saveas, btn_close):
            btnbar1.addWidget(b)
        btnbar1.addStretch()

        btnbar2 = QHBoxLayout()
        for b in (btn_add, btn_grp, btn_remove, btn_rename, btn_move, btn_set, btn_clear, btn_clear_all, btn_help):
            btnbar2.addWidget(b)
        btnbar2.addStretch()

        # Layout
        central = QWidget()
        v = QVBoxLayout(central)
        v.addLayout(topbar)
        v.addLayout(btnbar1)
        v.addLayout(btnbar2)
        v.addWidget(self.tree)
        self.setCentralWidget(central)

        self.update_badge()
        self.refresh_tree()

        # Menus (optional)
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        act_o = QAction("Open", self)
        act_o.triggered.connect(self.act_open)
        act_s = QAction("Save", self)
        act_s.triggered.connect(self.act_save)
        act_sa = QAction("Save As", self)
        act_sa.triggered.connect(self.act_saveas)
        act_c = QAction("Close", self)
        act_c.triggered.connect(self.act_close)
        act_e = QAction("Exit", self)
        act_e.triggered.connect(self.close)
        for a in (act_o, act_s, act_sa, act_c, act_e):
            file_menu.addAction(a)

        edit_menu = menubar.addMenu("&Edit")
        for a in ("Add", "Grp", "Remove", "Move", "Set Page", "Clear Page"):
            edit_menu.addAction(QAction(a, self))

        edit_menu.addAction(QAction("Rename", self, triggered=self.act_rename))
        edit_menu.addAction(
            QAction("Clear All", self, triggered=self.act_clear_all))

        help_menu = menubar.addMenu("&Help")
        act_h = QAction("Show Help", self)
        act_h.triggered.connect(self.act_help)
        help_menu.addAction(act_h)

        # Open from argv
        if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".pdf"):
            try:
                self.model.open(sys.argv[1])
                self.offset_spin.setValue(0)
                self.update_badge()
                self.refresh_tree()
            except Exception as e:
                QMessageBox.critical(self, "Open error", str(e))

    # -------- UI helpers --------
    def update_badge(self):
        if self.model.filename:
            name = self.model.filename
            if self.model._dirty:
                self.file_badge.setText(f"[{name}]")
                self.file_badge.setStyleSheet(
                    # light red when unsaved
                    "QLabel { color: #ff8899; font-weight: 600; }")
            else:
                self.file_badge.setText(f"[{name}]")
                self.file_badge.setStyleSheet(
                    # light blue when saved
                    "QLabel { color: #66aaff; font-weight: 600; }")
        else:
            self.file_badge.setText("[no-file]")
            self.file_badge.setStyleSheet(
                "QLabel { color: #66aaff; font-weight: 600; }")

    def refresh_tree(self):
        self.tree.clear()
        grey = QBrush(QColor("#9aa2af"))  # faint grey for Actual

        def add_items(parent_item: Optional[QTreeWidgetItem], nodes: List[OutlineNode]):
            for n in nodes:
                logical = "" if n.page_logical is None else str(n.page_logical)
                actual = ""
                if n.page_logical is not None:
                    actual = str(n.page_logical + self.model.offset)
                item = QTreeWidgetItem([n.title, logical, actual, n.id])
                # store reference
                item.setData(0, Qt.UserRole, n)
                # grey out Actual column
                item.setForeground(2, grey)
                if parent_item:
                    parent_item.addChild(item)
                else:
                    self.tree.addTopLevelItem(item)
                if n.children:
                    add_items(item, n.children)
        add_items(None, self.model.root)
        self.tree.expandAll()

    def selected_node(self) -> Optional[OutlineNode]:
        sel = self.tree.selectedItems()
        if not sel:
            return None
        return sel[0].data(0, Qt.UserRole)

    def on_selection_changed(self):
        # could enable/disable buttons based on selection
        pass

    # -------- Actions --------
    def act_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open PDF", "", "PDF Files (*.pdf)")
        if not path:
            return
        try:
            self.model.open(path)
            self.offset_spin.setValue(0)
            self.update_badge()
            self.refresh_tree()
        except Exception as e:
            QMessageBox.critical(self, "Open error", str(e))

    def act_save(self):
        try:
            self.model.save()
            self.update_badge()
        except Exception as e:
            QMessageBox.critical(self, "Save error", str(e))

    def act_saveas(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save As", self.model.filename or "output.pdf", "PDF Files (*.pdf)")
        if not path:
            return
        try:
            self.model.saveas(path)
            self.update_badge()
        except Exception as e:
            QMessageBox.critical(self, "Save As error", str(e))

    def act_close(self):
        self.model.close()
        self.offset_spin.setValue(0)
        self.update_badge()
        self.refresh_tree()

    def act_add(self):
        if not self.model.filename:
            QMessageBox.warning(self, "No PDF", "Open a PDF first.")
            return
        title, ok = QInputDialog.getText(self, "Add Outline", "Title:")
        if not ok or not title.strip():
            return
        page, ok = QInputDialog.getInt(
            self, "Add Outline", "Logical page (>=1):", 1, 1, 999999)
        if not ok:
            return
        parent = self.selected_node()
        try:
            self.model.add_outline(title.strip(), page,
                                   parent=parent, index=None)
            self.update_badge()
            self.refresh_tree()
        except Exception as e:
            QMessageBox.critical(self, "Add error", str(e))

    def act_grp(self):
        if not self.model.filename:
            QMessageBox.warning(self, "No PDF", "Open a PDF first.")
            return
        name, ok = QInputDialog.getText(self, "Add Group", "Name:")
        if not ok or not name.strip():
            return
        parent = self.selected_node()
        try:
            self.model.add_group(name.strip(), parent=parent, index=None)
            self.update_badge()
            self.refresh_tree()
        except Exception as e:
            QMessageBox.critical(self, "Group error", str(e))

    def act_remove(self):
        n = self.selected_node()
        if not n:
            QMessageBox.information(self, "Remove", "Select a node to remove.")
            return
        if QMessageBox.question(self, "Confirm Remove", f"Remove '{n.title}' and its children?") != QMessageBox.Yes:
            return
        try:
            self.model.remove(n)
            self.update_badge()
            self.refresh_tree()
        except Exception as e:
            QMessageBox.critical(self, "Remove error", str(e))

    def act_move(self):
        n = self.selected_node()
        if not n:
            QMessageBox.information(self, "Move", "Select a node to move.")
            return
        dlg = MoveDialog(self, self.model, n)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            self.model.move(n, dlg.dest, dlg.index)
            self.update_badge()
            self.refresh_tree()
        except Exception as e:
            QMessageBox.critical(self, "Move error", str(e))

    def act_setpage(self):
        n = self.selected_node()
        if not n:
            QMessageBox.information(self, "Set Page", "Select a node.")
            return
        page, ok = QInputDialog.getInt(
            self, "Set Page", "Logical page (>=1):", 1, 1, 999999)
        if not ok:
            return
        try:
            self.model.set_page(n, page)
            self.update_badge()
            self.refresh_tree()
        except Exception as e:
            QMessageBox.critical(self, "Set Page error", str(e))

    def act_clearpage(self):
        n = self.selected_node()
        if not n:
            QMessageBox.information(self, "Clear Page", "Select a node.")
            return
        try:
            self.model.clear_page(n)
            self.update_badge()
            self.refresh_tree()
        except Exception as e:
            QMessageBox.critical(self, "Clear Page error", str(e))

    def on_offset_changed(self, val: int):
        # Global offset; reflects everywhere
        if not self.model.filename:
            self.offset_spin.blockSignals(True)
            self.offset_spin.setValue(0)
            self.offset_spin.blockSignals(False)
            return
        self.model.offset_set(val)
        self.update_badge()
        self.refresh_tree()

    def act_help(self):
        text = (
            "<b>Features</b><br>"
            "• Open, Save, Save As, Close<br>"
            "• Global Offset: Actual = Logical + Offset<br>"
            "• Add outline, Add group, Remove, Move, Set Page, Clear Page<br>"
            "• Logical/Actual shown; Actual in grey<br>"
            "• Clean/dirty badge: blue = saved, red = unsaved<br><br>"
            "<b>Tips</b><br>"
            "• Select a node before Remove / Move / Set Page / Clear Page<br>"
            "• Move lets you choose destination parent and insert index (0-based)<br>"
            "• Offset applies to every item on display and on save<br>"
        )
        QMessageBox.information(self, "Help", text)

    def act_rename(self):
        n = self.selected_node()
        if not n:
            QMessageBox.information(self, "Rename", "Select a node.")
            return
        new_title, ok = QInputDialog.getText(
            self, "Rename", "New title:", text=n.title)
        if not ok or not new_title.strip():
            return
        try:
            self.model.rename(n.id, new_title.strip())
            self.update_badge()
            self.refresh_tree()
        except Exception as e:
            QMessageBox.critical(self, "Rename error", str(e))

    def act_clear_all(self):
        if not self.model.filename:
            QMessageBox.warning(self, "No PDF", "Open a PDF first.")
            return
        confirm = QMessageBox.question(
            self, "Clear All",
            "This will remove ALL outlines. Continue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self.model.clear_all()
            self.update_badge()
            self.refresh_tree()
        except Exception as e:
            QMessageBox.critical(self, "Clear All error", str(e))


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(900, 600)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
