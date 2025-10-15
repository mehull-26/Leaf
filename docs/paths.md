## Paths

A **path** locates a node by position in the tree using **1-based** indices per level.

### Syntax
```

<k1>[>k2[>k3...]]

````
- `k1` is the index among top-level nodes (1-based).
- `k2` is the index among the children of `k1`, and so on.

### Examples
- `1` → first top-level node  
- `2>3` → second top-level node’s third child  
- `1>2>1` → first root node → its second child → that child’s first child

### Where to use paths
Anywhere you can pass a node id (`n#`), you can also pass a path:
- `rename 1>3 "New Title"`
- `move 1>2 -t 2>1 -i 0`
- `setpage 2>1 10`
- `remove 1>2>1`

### Discovering paths
Use:
```bash
list --paths
````

You’ll see `[#k]` next to each node at every level. Those `k` values form the path.

---

## Indexing (Insertion Positions)

An **insert index** is **0-based** and applies within the destination’s children list.

* `--index 0` → first position at that level
* `--index 1` → second position, and so on
* If omitted, items are appended at the end.

### Examples

**Add at root first:**

```bash
add "Intro" 1 -i 0
```

**Add as first child of path 1:**

```bash
add "Section 1.1" 3 -p 1 -i 0
```

**Add under path 2>3 at slot 2:**

```bash
add "Topic" 5 -p 2>3 -i 2
```

**Move to root first:**

```bash
move n3 -i 0
```

**Move under 2>1 at slot 0:**

```bash
move n8 -t 2>1 -i 0
```

---

## Root Aliases

When specifying a destination parent, you can target the root with:

* `0`
* `root`
* `/`

Examples:

```bash
add "Appendix" 120 -p root -i 0
move n5 -t 0 -i 0
```

---

## Common Pitfalls

* Passing a bare number like `1` as a **parent** means path `1`, not index.
  Use `--index` for positions and `--parent`/`--to` for destinations.
* Don’t confuse 1-based **paths** with 0-based **indices**:

  * Path `1>2` selects a node.
  * Index `-i 0` specifies “first position” under the parent.


