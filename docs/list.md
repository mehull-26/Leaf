# Tree Model

This document explains how Leaf represents and manipulates the outline tree.

---

## Node Types

- **Leaf**: has a logical page (`page_logical != None`) and points to a PDF page.
- **Group**: a folder node (`page_logical == None`) that contains children.

Both node types have:
- `id` like `n7` (regenerated after edits)
- `title`
- `children` (list)
- `is_group` (derived from page presence)

---

## Structure

The outline is a rooted, ordered tree:

```

root (implicit)
├─ Node A (leaf)
│  ├─ Node A.1 (leaf)
│  └─ Node A.2 (group)
│     └─ Node A.2.1 (leaf)
└─ Node B (group)
└─ Node B.1 (leaf)

```

- Root is not a node you edit; it’s the destination for top-level inserts.
- Order matters. All inserts and moves respect list order.

---

## IDs and Paths

- IDs (`n#`) are session-stable but will be reassigned after edits.
- Paths (`1>2>1`) are positional and built from current order.  
  Use `list --paths` to discover them.

Use either **id** or **path** in any command that targets a node.

---

## Groups and External Viewers

Some viewers (like Zotero) may ignore nodes with no destination.  
Leaf anchors groups to their first leaf page during export so they appear consistently in such viewers.

---

## Operations (Model Semantics)

- **Add** inserts into `parent.children` or `root` at `index` (0-based).
- **Remove** deletes a node and its entire subtree.
- **Move** is transaction-safe:
  - Validates destination and index before mutating.
  - Prevents moving a node into its own subtree.
  - Adjusts index when moving within the same list to keep order stable.
- **Rename** changes title only.
- **Set/Clear Page** toggles node between leaf and group.
- **Offset** does not change the tree; it alters page resolution on export and display.

---

## Save Behavior

On each `save`/`saveas`:
1. The writer is rebuilt with the same pages to avoid duplicate outlines.
2. The outline tree is walked and destinations are created using:
```

actual_index = page_logical + offset - 1

```
3. Groups are anchored to a valid page (first leaf or page 1) for broad compatibility.

If any destination goes out of bounds, save raises a clear error.

---

## Practical Tips

- Use `grp` to scaffold structure, then `add` leaves under groups.
- Prefer paths for stable targeting in scripts; IDs are great for quick interactive edits.
- Keep offset aligned to your book’s numbering scheme before bulk `add` operations.
```
