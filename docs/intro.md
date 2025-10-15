# Leaf Documentation

---

## 1 · Overview

**Leaf** is a command-line tool for editing PDF outlines (bookmarks) interactively.  
It supports full tree manipulation — adding, grouping, moving, renaming, and reordering bookmarks — with a per-file offset system that automatically saves preferences.  

The **CLI** is the main and complete interface.  
A **GUI** built on Qt6 exists but is minimal and experimental.

---

## 2 · Core Concepts

- **Outline** → a single bookmark node in the PDF.  
- **Group** → a folder containing other outlines (no page).  
- **Offset** → adjustment between logical and actual PDF pages.  
- **Path** → hierarchical reference like `1>3>2`.  
- **ID** → unique internal name like `n4`.

---

## 3 · [Command Reference](cmd_reference.md)

| Command | Description |
|----------|-------------|
| `open <file.pdf>` | Open a PDF file. |
| `save`, `saveas <file.pdf>` | Save changes (in-place or as new file). |
| `close`, `quit` | Close current PDF or exit shell. |
| `list [--paths]` | Display outline tree. |
| `add "<title>" <page> [--parent/-p <id\|path\|0\|root\|/>][--index/-i <n>]` | Add new outline at given page. |
| `grp "<name>" [--parent/-p <id\|path\|0\|root\|/>] [--index/-i <n>]` | Add a folder/group node. |
| `remove <id\|path>` / `remove --all` | Remove a specific node or all outlines. |
| `rename <id\|path> "<new title>"` | Rename an existing node. |
| `move <id\|path> [--to/-t <id\|path\|0\|root\|/>] [--index/-i <n>]` | Move a node to another parent or position. |
| `setpage <id\|path> <page>` | Assign a page number to a node. |
| `clearpage <id\|path>` | Remove the page link from a node. |
| `offset <n>` / `offset set <n>` / `offset clear` | Set, view, or reset page offset. |


---

## 4 · [Paths and Indexing](paths.md)

- **Paths** use `>` to navigate levels, e.g., `1>3>2`.  
- **Index (`--index`)** is **0-based** — use `0` for the first slot.  
- **Root** can be referenced using `0`, `root`, or `/`.  

Examples:
```bash
add "Introduction" 1 -i 0
add "Methods" 4 -p 1 -i 1
move n3 -t 0 -i 0
```
## 5. [Offsets](offset.md)

Leaf stores offsets per file in a small JSON file:
```
{
  "/Users/mehul/Documents/ip1.pdf": 2,
  "/Users/mehul/Desktop/book.pdf": 0
}
```

This ensures that when reopening the same file, your offset is remembered.

## 6. Example Workflow
```
leaf thesis.pdf
add "Abstract" 1
add "Introduction" 3
grp "Appendices" -i 0
move n3 -t 0 -i 0
offset set 2
save
```

## 7. [Listing Tree](list.md)

When listing outlines:
```
├── [n2] Chapter 1  (p. 5/8)
```

- Left → internal node ID
- Right → logical / actual page (after offset)

## 8. GUI (Work in Progress)

- Built with PySide6 (Qt6)
- Can open, view, add, and move outlines
- Still minimal — lacks full CLI capabilities

Recommended only for light testing

## 9. Known Limitations
- Undo/Redo not yet implemented
- GUI incomplete
- Some malformed PDFs may not preserve all outline details