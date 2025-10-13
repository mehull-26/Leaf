# cli.py — PDF outline editor (PyPDF)
# Features: open, save, saveas, list [--paths], add, grp, remove, move, setpage, clearpage, offset set/clear, help
# Notes:
#   • Uses PyPDF (pip install pypdf)
#   • Offset is global. Actual page = logical + offset.
#   • On open, offset = 0 so display shows (1/1).
#   • Writer is rebuilt on save to avoid duplicate outlines.
#   • Paths use 1-based indices per level: e.g., 1>3>2

import os
import sys
import shlex
from dataclasses import dataclass, field
from typing import List, Optional

import json
import hashlib

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style

from rich.console import Console
from rich.tree import Tree
from rich.text import Text
from rich.panel import Panel
from rich import box

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    raise SystemExit("Install dependency first:\n  pip install pypdf")

# =========================
# Data model
# =========================


@dataclass
class OutlineNode:
    id: str
    title: str
    page_logical: Optional[int] = None
    children: List["OutlineNode"] = field(default_factory=list)
    is_group: bool = False


def short_label(path: str | None, maxlen: int = 10) -> str:
    if not path:
        return "no-file"
    base = os.path.basename(path)
    if len(base) <= maxlen:
        return base
    # Make it exactly maxlen chars: first maxlen-1 + ellipsis
    return base[:maxlen - 1] + "…"


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

# -----------prefs--------------


def _prefs_path() -> str:
    # Home-based dotfile, portable across Win/Linux/macOS
    return os.path.join(os.path.expanduser("~"), ".pdfout_prefs.json")


def _load_prefs() -> dict:
    try:
        with open(_prefs_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_prefs(prefs: dict) -> None:
    try:
        with open(_prefs_path(), "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2)
    except Exception:
        pass  # don’t crash UI/CLI if prefs can’t be written


def _file_key(path: str) -> str:
    # Absolute path is good enough as a stable key
    return os.path.abspath(path)

# =========================
# Core model
# =========================


class PdfOutlineModel:
    def __init__(self):
        self.filename: Optional[str] = None
        self._prefs = _load_prefs()
        self.reader: Optional[PdfReader] = None
        self.writer: Optional[PdfWriter] = None
        self.root: List[OutlineNode] = []
        self.offset: int = 0
        self.id_map = {}
        self._dirty: bool = False

    # ---------- File ops ----------

    def open(self, path: str):
        self.reader = PdfReader(path)
        self.writer = PdfWriter()
        for p in self.reader.pages:
            self.writer.add_page(p)
        self.filename = path

        # 1) load saved offset for this file
        k = _file_key(path)
        self.offset = int(self._prefs.get(k, 0))

        self.root = self._import_outlines()
        assign_ids(self.root)
        self._rebuild_id_map()
        self._dirty = False

    def save(self):
        self._ensure_open()
        if not self.writer or not self.filename:
            raise RuntimeError("No PDF loaded")
        self._export_outlines()
        with open(self.filename, "wb") as f:
            self.writer.write(f)
        self._dirty = False

    def saveas(self, path: str):
        self._ensure_open()
        if not self.writer:
            raise RuntimeError("No PDF loaded")
        self._export_outlines()
        with open(path, "wb") as f:
            self.writer.write(f)
        self.filename = path
        self._prefs[_file_key(self.filename)] = self.offset
        _save_prefs(self._prefs)

        self._dirty = False

    # ---------- Import/Export ----------
    def _import_outlines(self) -> List[OutlineNode]:
        if not self.reader:
            return []
        try:
            raw = self.reader.outline
        except Exception:
            raw = []

        def conv(items) -> list[OutlineNode]:
            out: List[OutlineNode] = []
            for it in items:
                if isinstance(it, list):
                    # children of previous node
                    if out:
                        out[-1].children = conv(it)
                        out[-1].is_group = True
                    continue
                title = getattr(it, "title", str(it)) or "Untitled"

                actual_1 = None
                try:
                    actual_1 = self.reader.get_destination_page_number(it) + 1
                except Exception:
                    pass

                if actual_1 is not None:
                    try:
                        logical = logical = int(actual_1) - int(self.offset)
                    except Exception:
                        logical = actual_1
                    node = OutlineNode("", title, logical, [], False)
                else:
                    node = OutlineNode("", title, None, [], True)

                out.append(node)
            return out

        return conv(raw)

    def _export_outlines(self):
        self._ensure_open()
        # Recreate writer to avoid duplicate outlines on repeated saves
        if not self.writer:
            return
        old_pages = list(self.writer.pages)
        self.writer = PdfWriter()
        for p in old_pages:
            self.writer.add_page(p)

        def first_leaf_logical(node):
            stack = [node]
            while stack:
                cur = stack.pop(0)
                if cur.page_logical is not None:
                    return cur.page_logical
                stack = cur.children + stack
            return None  # no leaf with page

        def build(nodes, parent=None):
            for n in nodes:
                # choose a page for Zotero: leaf page for groups, or own page for leaves
                logical = n.page_logical
                if logical is None:
                    # anchor groups to first child page
                    logical = first_leaf_logical(n)

                if logical is not None:
                    actual_idx = logical + self.offset - 1
                    if actual_idx < 0 or actual_idx >= len(self.writer.pages):
                        raise ValueError(f"Page {actual_idx+1} out of range.")
                    dest_page = self.writer.pages[actual_idx]
                else:
                    # truly empty group: anchor to page 1 so Zotero keeps it visible
                    dest_page = self.writer.pages[0]

                new_parent = self.writer.add_outline_item(
                    n.title, dest_page, parent=parent)
                if n.children:
                    build(n.children, parent=new_parent)

        build(self.root)

    # ---------- Path helpers ----------
    @staticmethod
    def parse_path(s: str) -> List[int]:
        parts = [p.strip() for p in s.split(">")]
        if not parts or any(not p.isdigit() or int(p) <= 0 for p in parts):
            raise ValueError("Path must be like 1>3>2 with positive integers")
        return [int(p) - 1 for p in parts]  # zero-based per level

    def _get_ref(self, tok: str) -> OutlineNode:
        # Allow id (n#) or path (1>2>3)
        if tok.startswith("n") and tok[1:].isdigit():
            n = self.id_map.get(tok)
            if not n:
                raise ValueError(f"Unknown id {tok}")
            return n
        # treat as path
        idxs = self.parse_path(tok)
        cur = None
        lst = self.root
        for i in idxs:
            if i < 0 or i >= len(lst):
                raise ValueError("Path out of range")
            cur = lst[i]
            lst = cur.children
        if cur is None:
            raise ValueError("Empty path")
        return cur

    def _find_parent_and_index(self, target: OutlineNode):
        # returns (parent_list, index)
        def walk(lst):
            for i, n in enumerate(lst):
                if n is target:
                    return lst, i
                got = walk(n.children)
                if got:
                    return got
            return None
        return walk(self.root)

    # ---------- Commands ----------
    def rename(self, tok: str, new_title: str):
        node = self._get_ref(tok)  # already supports id or path in your build
        node.title = new_title
        assign_ids(self.root)
        self._rebuild_id_map()
        self._dirty = True

    def clear_all(self):
        self.root = []
        assign_ids(self.root)
        self._rebuild_id_map()
        self._dirty = True

    def _ensure_open(self):
        if not self.reader or not self.writer or not self.filename:
            raise RuntimeError("No PDF open")

    def close(self):
        """Close the current PDF and reset state, keeping the CLI session alive."""
        self.reader = None
        self.writer = None
        self.filename = None
        self.root = []
        self.id_map = {}
        self.offset = 0
        self._dirty = False

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
        return node.id

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
        return node.id

    def remove(self, tok: str):
        self._ensure_open()
        target = self._get_ref(tok)
        pair = self._find_parent_and_index(target)
        if not pair:
            raise ValueError("Node not found")
        parent_list, idx = pair
        del parent_list[idx]
        assign_ids(self.root)
        self._rebuild_id_map()
        self._dirty = True

    def _is_descendant(self, root: "OutlineNode", maybe_child: "OutlineNode") -> bool:
        """Return True if maybe_child is inside root's subtree (including nested)."""
        stack = list(root.children)
        while stack:
            n = stack.pop()
            if n is maybe_child:
                return True
            stack.extend(n.children)
        return False

    def move(self, tok: str, to_tok: Optional[str], index: Optional[int]):
        self._ensure_open()
        """
        Move node by id or path to a new parent (or root if to_tok is None).
        Transaction-safe: no deletion if destination is invalid.
        """
        node = self._get_ref(tok)

        # 1) Resolve source location (but do NOT pop yet)
        src_pair = self._find_parent_and_index(node)
        if not src_pair:
            raise ValueError("Node not found")
        src_list, src_idx = src_pair

        # 2) Resolve destination list
        if to_tok:
            dest_parent = self._get_ref(to_tok)
            # Disallow moving into itself or its own subtree
            if node is dest_parent or self._is_descendant(node, dest_parent):
                raise ValueError(
                    "Cannot move a node into itself or its descendants")
            dest_list = dest_parent.children
        else:
            dest_list = self.root  # move to top level

        # 3) Compute and validate insertion index
        insert_at = len(dest_list) if index is None else int(index)
        if insert_at < 0 or insert_at > len(dest_list):
            raise ValueError("Destination index out of range")

        # 4) If moving within the same list and inserting after its current position,
        #    removing first will shift indices; compensate up-front
        if dest_list is src_list and insert_at > src_idx:
            insert_at -= 1

        # 5) If this is a true no-op (same list, same position), just return
        if dest_list is src_list and insert_at == src_idx:
            return  # nothing to do; not dirty

        # 6) All checks passed. Now actually mutate.
        moved = src_list.pop(src_idx)
        dest_list.insert(insert_at, moved)

        assign_ids(self.root)
        self._rebuild_id_map()
        self._dirty = True

    def set_page(self, tok: str, page: int):
        self._ensure_open()
        node = self._get_ref(tok)
        node.page_logical = int(page)
        node.is_group = False
        self._dirty = True

    def clear_page(self, tok: str):
        self._ensure_open()
        node = self._get_ref(tok)
        node.page_logical = None
        node.is_group = True
        self._dirty = True

    def offset_set(self, val: int):
        self._ensure_open()
        self.offset = int(val)
        self._dirty = True
        if self.filename:
            k = _file_key(self.filename)
            self._prefs[k] = self.offset
            _save_prefs(self._prefs)

    def offset_clear(self):
        self._ensure_open()
        self.offset = 0
        self._dirty = True
        if self.filename:
            k = _file_key(self.filename)
            self._prefs[k] = self.offset
            _save_prefs(self._prefs)

    # ---------- Listing ----------
    def list_tree(self, show_paths: bool = False) -> Tree:
        self._ensure_open()
        label = Text(short_label(self.filename or "no-file"), style="bold")
        t = Tree(label)

        def add_children(rparent, children):
            for idx, n in enumerate(children, start=1):
                if n.page_logical is not None:
                    lp = n.page_logical
                    actual = lp + self.offset
                    pg_text = Text.assemble(
                        ("p. ", "dim"),
                        (str(lp), "magenta"),
                        ("/", "dim"),
                        (str(actual), "grey50"),
                    )
                else:
                    pg_text = Text("no page", style="yellow")

                idx_badge = f"[#{idx}] " if show_paths else ""
                node_text = Text.assemble(
                    ("  ", ""),
                    (idx_badge, "dim"),
                    ("[", "dim"),
                    (n.id, "bold cyan"),
                    ("] ", "dim"),
                    (n.title, "white"),
                    ("  (", "dim"),
                    pg_text,
                    (")", "dim"),
                )
                sub = rparent.add(node_text)
                if n.children:
                    add_children(sub, n.children)
        add_children(t, self.root)
        return t

    # ---------- Internals ----------
    def _rebuild_id_map(self):
        self.id_map = {n.id: n for n in enumerate_tree(self.root)}

# =========================
# Help page (bordered, tidy)
# =========================


HELP_TEXT = """
[bold]Commands[/bold]

[cyan]open[/cyan] <file.pdf>
    Open a PDF. Offset resets to 0.

[cyan]save[/cyan]
    Save to current file. Outlines rebuilt cleanly (no duplicates).

[cyan]saveas[/cyan] <file.pdf>
    Save to a new file and switch context.

[cyan]list[/cyan] [--paths]
    Show outline tree with ids. Pages display as p. logical/[dim]actual[/dim].
    With --paths, show per-level indices [#k] to build paths by eye.

[cyan]add[/cyan] "<title>" <page> [--parent <id|path>] [--index <n>]
    Add an outline at logical page under optional parent, inserted at index (0-based).

[cyan]grp[/cyan] "<name>" [--parent <id|path>] [--index <n>]
    Add a group (folder) under optional parent, inserted at index (0-based).

[cyan]remove[/cyan] <id|path>
    Remove a node by id (e.g., n3) or by path (e.g., 1>2>1).
    
[cyan]remove[/cyan] --all
    Remove ALL outlines. Asks for confirmation.

[cyan]move[/cyan] <id|path> [--to <parent_id|path>] [--index <n>]
    Move a node under a new parent (or root if --to omitted).
    Index is 0-based within the destination's children.
    Examples:
      move 2
      move 1>3 --to n5 --index 0
      move n9 --to 3>2

[cyan]setpage[/cyan] <id|path> <page>
    Set logical page for a node and make it a leaf.

[cyan]clearpage[/cyan] <id|path>
    Remove page from a node (turns into a group).

[cyan]offset[/cyan] set <n>
[cyan]offset[/cyan] <n>
[cyan]offset[/cyan] clear
    Global shift applied to all outlines. Actual = logical + offset.

[cyan]close[/cyan]
    Close the current PDF (asks to discard if unsaved).

[cyan]quit[/cyan] / [cyan]exit[/cyan]
    Exit the shell (asks to discard if unsaved).

[cyan]rename[/cyan] <id|path> "<new title>"
    Rename a node without changing its page or position.

[cyan]help[/cyan]
    Show this help.
"""


def print_help(console: Console):
    console.print(Panel.fit(Text.from_markup(HELP_TEXT),
                  title="Help", border_style="blue"))
    console.print()

# =========================
# CLI shell
# =========================


def make_indented(text: str) -> str:
    return "\n".join(("  " + line) if line.strip() else "" for line in text.splitlines())


def main():
    console = Console()
    model = PdfOutlineModel()

    def confirm_discard_if_dirty() -> bool:
        if getattr(model, "_dirty", False):
            console.print(make_indented(
                "[yellow]Unsaved changes.[/yellow] Type [bold]YES[/bold] to discard and continue:"))
            ans = session.prompt("  > ").strip()
            return ans == "YES"
        return True

    # open from CLI arg if provided
    if len(sys.argv) > 1:
        try:
            model.open(sys.argv[1])
            console.print(make_indented(
                f"[green]Opened[/green] {sys.argv[1]}"))
            console.print()
        except Exception as e:
            console.print(make_indented(f"[red]Error:[/red] {e}"))
            console.print()

    style = Style.from_dict({
        "bracket": "ansibrightblack",
        "file": "ansibrightcyan",
        "colon": "ansibrightblack",
    })
    session = PromptSession()

    def prompt_str() -> HTML:
        fname = short_label(model.filename)  # <— truncated
        color = "ansibrightred" if model._dirty else "ansibrightcyan"
        return HTML(f'<bracket>[</bracket><file><{color}>{fname}</{color}></file><bracket>]</bracket><colon>:</colon> ')

    console.print(Panel(Text("PDF Outline Shell",
                  justify="center"), border_style="cyan", box=box.SIMPLE))
    console.print()

    while True:
        try:
            raw = session.prompt(prompt_str(), style=style)
        except (EOFError, KeyboardInterrupt):
            console.print("\nExiting.")
            break

        if not raw.strip():
            continue

        try:
            parts = shlex.split(raw)
        except ValueError as e:
            console.print(make_indented(f"[red]Parse error:[/red] {e}"))
            console.print()
            continue

        cmd, *args = parts
        try:
            if cmd in ("quit", "exit"):
                if not confirm_discard_if_dirty():
                    console.print(make_indented("[cyan]Aborted[/cyan]"))
                    console.print()
                    continue
                break

            elif cmd == "help":
                print_help(console)

            elif cmd == "open":
                if not args:
                    raise ValueError("open <file.pdf>")
                model.open(args[0])
                console.print(make_indented(
                    f"[green]Opened[/green] {args[0]}"))
                console.print()

            elif cmd == "save":
                model.save()
                console.print(make_indented("[green]Saved[/green]"))
                console.print()

            elif cmd == "saveas":
                if not args:
                    raise ValueError("saveas <file.pdf>")
                model.saveas(args[0])
                console.print(make_indented(
                    f"[green]Saved as[/green] {args[0]}"))
                console.print()

            elif cmd == "rename":
                # rename <id|path> "<new title>"
                if len(args) < 2:
                    raise ValueError('rename <id|path> "<new title>"')
                tok, new_title = args[0], args[1]
                model.rename(tok, new_title)
                console.print(make_indented("[green]Renamed[/green]"))
                console.print()

            elif cmd == "list":
                show_paths = (len(args) == 1 and args[0] == "--paths")
                console.print(f"  Offset: {model.offset}\n")
                console.print(model.list_tree(show_paths=show_paths))
                console.print()

            elif cmd == "add":
                # add "<title>" <page> [--parent <id|path>] [--index <n>]
                if len(args) < 2:
                    raise ValueError(
                        'add "<title>" <page> [--parent <id|path>] [--index <n>]')
                title = args[0]
                page = int(args[1])
                parent = None
                index = None

                i = 2
                while i < len(args):
                    if args[i] == "--parent" or "-p":
                        i += 1
                        if i >= len(args):
                            raise ValueError("--parent needs a value")
                        parent = model._get_ref(args[i])
                    elif args[i] == "--index" or "-i":
                        i += 1
                        if i >= len(args) or not args[i].lstrip("-").isdigit():
                            raise ValueError("--index needs an integer")
                        index = int(args[i])
                    else:
                        raise ValueError(f"Unknown option {args[i]}")
                    i += 1

                model.add_outline(title, page, parent=parent, index=index)
                console.print(make_indented(f"[green]Added[/green]"))
                console.print()

            elif cmd == "grp":
                # grp "<name>" [--parent <id|path>] [--index <n>]
                if len(args) < 1:
                    raise ValueError(
                        'grp "<name>" [--parent <id|path>] [--index <n>]')
                name = args[0]
                parent = None
                index = None

                i = 1
                while i < len(args):
                    if args[i] == "--parent":
                        i += 1
                        if i >= len(args):
                            raise ValueError("--parent needs a value")
                        parent = model._get_ref(args[i])
                    elif args[i] == "--index":
                        i += 1
                        if i >= len(args) or not args[i].lstrip("-").isdigit():
                            raise ValueError("--index needs an integer")
                        index = int(args[i])
                    else:
                        raise ValueError(f"Unknown option {args[i]}")
                    i += 1

                model.add_group(name, parent=parent, index=index)
                console.print(make_indented(
                    f"[green]Group added[/green]"))
                console.print()

            elif cmd == "remove":
                # keep your existing single-node remove…
                if len(args) == 1 and args[0] != "--all":
                    model.remove(args[0])
                    console.print(make_indented("[green]Removed[/green]"))
                    console.print()
                elif len(args) == 1 and args[0] == "--all":
                    # confirmation prompt
                    console.print(make_indented(
                        "[yellow]This will delete ALL outlines.[/yellow] Type [bold]YES[/bold] to confirm:"))
                    confirm = session.prompt("  > ").strip()
                    if confirm == "YES":
                        model.clear_all()
                        console.print(make_indented(
                            "[green]All outlines cleared[/green]"))
                        console.print()
                    else:
                        console.print(make_indented("[cyan]Aborted[/cyan]"))
                        console.print()
                else:
                    raise ValueError("remove <id|path>  |  remove --all")

            elif cmd == "move":
                if not args:
                    raise ValueError(
                        "move <id|path> [--to <parent_id|path>] [--index <n>]")
                tok = args[0]
                to = None
                index = None
                i = 1
                while i < len(args):
                    if args[i] == "--to":
                        i += 1
                        to = args[i]
                    elif args[i] == "--index":
                        i += 1
                        index = int(args[i])
                    else:
                        raise ValueError(f"Unknown option {args[i]}")
                    i += 1
                model.move(tok, to, index)
                console.print(make_indented("[green]Moved[/green]"))
                console.print()

            elif cmd == "setpage":
                if len(args) != 2:
                    raise ValueError("setpage <id|path> <page>")
                model.set_page(args[0], int(args[1]))
                console.print(make_indented("[green]Page set[/green]"))
                console.print()

            elif cmd == "close":
                if not confirm_discard_if_dirty():
                    console.print(make_indented("[cyan]Aborted[/cyan]"))
                    console.print()
                    continue
                model.close()
                console.print("  Closed current file")
                console.print()

            elif cmd == "clearpage":
                if len(args) != 1:
                    raise ValueError("clearpage <id|path>")
                model.clear_page(args[0])
                console.print(make_indented("[green]Page cleared[/green]"))
                console.print()

            elif cmd == "offset":
                # Support: "offset 2", "offset set 2", "offset clear"
                if len(args) == 1 and args[0].lstrip("-").isdigit():
                    model.offset_set(int(args[0]))
                    console.print(make_indented(
                        f"[green]Offset set to[/green] {model.offset}"))
                    console.print()
                elif args and args[0] == "set":
                    if len(args) < 2:
                        raise ValueError("offset set <n>")
                    model.offset_set(int(args[1]))
                    console.print(make_indented(
                        f"[green]Offset set to[/green] {model.offset}"))
                    console.print()
                elif args and args[0] == "clear":
                    model.offset_clear()
                    console.print(make_indented(
                        "[green]Offset cleared[/green]"))
                    console.print()
                else:
                    print_help(console)

            else:
                console.print(make_indented(
                    f"[red]Unknown command:[/red] {cmd}"))
                console.print()

        except Exception as e:
            console.print(make_indented(f"[red]Error:[/red] {e}"))
            console.print()


if __name__ == "__main__":
    main()
