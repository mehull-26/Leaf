# Offsets

Leaf uses a **per-file global offset** to reconcile logical page numbers with the PDF’s actual page indices.

---

## What is Offset?

Many PDFs have front matter (cover, contents, etc.) that shifts chapter numbering.  
Offset lets you set a global correction:

```

Actual PDF page = Logical page + Offset

````

This applies to:
- Display in `list` (shown as `p. logical/[dim]actual[/dim]`)
- Exported outline destinations on `save`/`saveas`

---

## Commands

### `offset <n>` / `offset set <n>`
Set the offset to `n`. Positive or negative integers are allowed.

**Examples**
```bash
offset 2
offset set -3
````

### `offset clear`

Reset offset to 0.

---

## Persistence

Offsets are stored per-file in:

```
~/.pdfout_prefs.json
```

Example:

```json
{
  "C:\\Users\\Mehul\\Docs\\ip1.pdf": 2,
  "D:\\papers\\thesis.pdf": 0
}
```

On `open <file.pdf>`, Leaf restores the saved offset **before** importing outlines so that:

```
logical = actual - offset
```

This keeps bookmarks consistent across sessions.

---

## Examples

**Set offset for a book with 2-page preface:**

```bash
offset set 2
add "Chapter 1" 1       # will resolve to actual page 3
save
```

**Clear offset and reassign pages:**

```bash
offset clear
setpage n5 10
save
```

---

## Tips

* If a bookmark points outside the PDF after applying offset, save will fail with a clear “page out of range” error.
* Changing offset after creating outlines updates how they resolve on the next save; you don’t need to re-enter titles.


