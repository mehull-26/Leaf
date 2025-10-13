# Leaf

**Leaf** is a lightweight CLI + GUI tool for editing PDF outlines (bookmarks).  
It lets you add, remove, rename, move, and group bookmarks with precision — all from a neat shell interface.  
The GUI exists and works, but is minimal and **not recommended yet**.  
The **CLI** is full-blown and rock-solid.

---

## ✨ Features

- Add / remove / rename outlines  
- Group outlines (nested folders)  
- Move nodes by index or path  
- Manage global per-file offsets  
- Clear all outlines with confirmation  
- Persistent offset storage (`~/.pdfout_prefs.json`)  
- Smooth compatibility with Edge, Zotero, etc.

---

## 📦 Installation

```bash
git clone https://github.com/mehull-26/Leaf
cd scripts
pip install -r requirements.txt
```
To build executables:
```
pyinstaller --onefile scripts/cli.py -n leaf
pyinstaller --onefile scripts/gui.py -n leaf-gui
```

Add the dist/ folder to your PATH for global use.