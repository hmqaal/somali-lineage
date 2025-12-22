import json
from collections import defaultdict, deque

IN_FILE = "tree.json"
OUT_FILE = "tree_clean.json"

# Put IDs you want to delete here (as strings)
DELETE_IDS = {
    # "123",
    # "456",
}

data = json.load(open(IN_FILE, "r", encoding="utf-8"))

def norm_id(x):
    if x in (None, "", "null"):
        return None
    return str(x).strip()

def score(n):
    name = (n.get("name") or "").strip()
    s = 0
    if name and name.lower() != "genealogy":
        s += 10
        s += min(len(name), 80) / 20
    if n.get("parentId") not in (None, "", "null"):
        s += 1
    return s

# 1) Deduplicate by id (keep best)
best = {}
dup_removed = 0
for n in data:
    pid = norm_id(n.get("id"))
    if not pid:
        continue
    node = {
        "id": pid,
        "parentId": norm_id(n.get("parentId")),
        "name": (n.get("name") or "").strip()
    }
    if pid in best:
        dup_removed += 1
        if score(node) > score(best[pid]):
            best[pid] = node
    else:
        best[pid] = node

nodes = list(best.values())
id_to_node = {n["id"]: n for n in nodes}

# 2) Build children index for cascade delete
children = defaultdict(list)
for n in nodes:
    if n["parentId"]:
        children[n["parentId"]].append(n["id"])

# 3) Cascade delete: delete selected IDs + all descendants
to_delete = set()
q = deque([i for i in DELETE_IDS if i in id_to_node])
while q:
    cur = q.popleft()
    if cur in to_delete:
        continue
    to_delete.add(cur)
    for ch in children.get(cur, []):
        q.append(ch)

cascade_deleted = len(to_delete)
if cascade_deleted:
    nodes = [n for n in nodes if n["id"] not in to_delete]

# Rebuild ids after deletion
ids = set(n["id"] for n in nodes)

# 4) Fix missing parents (turn into roots)
missing_fixed = 0
for n in nodes:
    p = n.get("parentId")
    if p is not None and p not in ids:
        n["parentId"] = None
        missing_fixed += 1

# 5) Fix self-parent links
self_fixed = 0
for n in nodes:
    if n.get("parentId") == n.get("id"):
        n["parentId"] = None
        self_fixed += 1

# Save
nodes.sort(key=lambda x: int(x["id"]) if str(x["id"]).isdigit() else str(x["id"]))
json.dump(nodes, open(OUT_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

print("Input:", len(data))
print("Output:", len(nodes))
print("Duplicates removed:", dup_removed)
print("Cascade deleted:", cascade_deleted)
print("Missing parents fixed:", missing_fixed)
print("Self-parent fixed:", self_fixed)
print("Wrote:", OUT_FILE)
