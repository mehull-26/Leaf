# Command Reference (Leaf)

This document details every CLI command, its options, valid variations, and examples.

> Notation:
> - `<required>` values are required.
> - `[optional]` values are optional.
> - `id` means a node id like `n5`.
> - `path` means a positional path like `1>2>1` (1-based per level).
> - Root aliases: `0`, `root`, `/`.
> - Insert indices are **0-based**.

---

## Session & Files

### `open <file.pdf>`
Open a PDF. If a saved offset exists for this file, it is restored.

**Example**
```bash
open thesis.pdf
````

### `save`

Write changes to the current file.

**Example**

```bash
save thesis_outlined.pdf
```


### `saveas <file.pdf>`

Write changes to a new file and switch context to it.

**Example**

```bash
saveas thesis_outlined.pdf
```

### `close`

Close the current PDF. Prompts to discard if there are unsaved changes.

### `quit` / `exit`

Leave the shell. Prompts to discard if there are unsaved changes.

---

## Viewing

### `list [--paths]`

Show the outline tree. Pages display as `p. logical/actual`.
With `--paths`, per-level indices `[#k]` are shown to help build paths.

**Example**

```bash
list
list --paths
```

---

## Creating Nodes

### `add "<title>" <page> [--parent/-p <id|path|0|root|/>] [--index/-i <n>]`

Add a leaf node (bookmark) with a logical page.

* If `--parent` is omitted, the node is added at the root.
* `--index` inserts at a specific 0-based position in the destination’s children. If omitted, the node is appended at the end.

**Examples**

```bash
add "Introduction" 1                   # adds at logical page 1
add "Preface" 1 -i 0                   # first at root
add "Preface" 1 -p n2                  # append within n2 node as its child
add "Section 1.1" 3 -p 1 -i 0          # first child under path 1
add "Topic" 5 -p 2>3 -i 2              # path 2>3, insert at index 2
add "Appendix A" 120 -p root -i 0      # first at root using alias
```

### `grp "<name>" [--parent/-p <id|path|0|root|/>] [--index/-i <n>]`

Create a folder (group) node with no page.

**Examples**

```bash
grp "Chapters"
grp "Appendices" -i 0
grp "Background" -p 1 -i 1
```

---

## Editing Nodes

### `rename <id|path> "<new title>"`

Change a node’s title.

**Examples**

```bash
rename n7 "System Overview"
rename 2>1 "Methods"
```

### `remove <id|path>`

Delete a single node and its subtree.

**Examples**

```bash
remove n3
remove 1>2>1
```

### `remove --all`

Delete all outlines after a confirmation prompt.

---

## Moving Nodes

### `move <id|path> [--to/-t <id|path|0|root|/>] [--index/-i <n>]`

Move a node to a new parent and/or position. Transaction-safe:

* Validates destination before mutating.
* Prevents moving into its own subtree.
* Indices are 0-based within destination’s children.

If `--to` is omitted, the destination is the root.

**Examples**

```bash
move n3 -i 0                     # to root, first position
move n8 -t 1                     # under path 1, append at end
move n5 -t 2>1 -i 0              # under path 2>1, first slot
move 1>3 -t root -i 2            # path source and root destination
```

---

## Pages

### `setpage <id|path> <page>`

Assign a logical page to the node and mark it as a leaf.

**Examples**

```bash
setpage n4 12
setpage 1>2 3
```

### `clearpage <id|path>`

Remove the page assignment and turn the node into a group.

**Example**

```bash
clearpage n9
```

---

## Offset

### `offset <n>` or `offset set <n>`

Set global offset for this file. Actual page = Logical + Offset.
The offset is stored per-file and auto-restored when reopened.

### `offset clear`

Reset offset to 0.

**Examples**

```bash
offset 2
offset set 3
offset clear
```

---

## Tips

* Use `list --paths` to discover paths for complex moves/inserts.
* Root aliases: `0`, `root`, `/`.
* Index is 0-based. `--index 0` always means “first position.”
* Save frequently; the prompt turns blue when clean, red when dirty.


# Paths & Indexing

This document explains how **paths** and **indices** work in Leaf’s CLI.

---

