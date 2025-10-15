# Leaf

**Leaf** is a lightweight CLI + GUI tool for editing PDF outlines (bookmarks).  
It lets you add, remove, rename, move, and group bookmarks with precision — all from a neat shell interface.  
The GUI exists and works, but it is minimal and **not yet recommended**.  
The CLI is full-featured and rock-solid.

>**Motivation:** While reading books in PDF format, I often encounter PDFs that lack outlines, making it difficult to navigate to the desired section. I tried using online tools, but they required subscriptions for files with many pages or a large size. Hence, I developed this tool, which helps me quickly add outlines to chapters or content in a paper or book. 

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

Read the documentation at [Documentation](docs/intro.md)
