import json
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(layout="wide")
st.title("digital family tree ")

# --- UI controls ---
# Filter to the major clans (click-to-select, multi) + layout + initial depth
CLAN_OPTIONS = [
    ("Darood", "1"),
    ("Dir", "158"),
    ("Rahanweyn", "651"),
    ("Hawiye", "572"),
    ("Prune", "-1"),
    ("Sheikh Isaaq", "1000"),
]

col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    st.write("Filter clans")
    clan_cols = st.columns(len(CLAN_OPTIONS))
    selected_root_ids: list[str] = []
    for c, (label, cid) in zip(clan_cols, CLAN_OPTIONS):
        with c:
            if st.checkbox(label, value=False):
                selected_root_ids.append(cid)
with col2:
    orientation = st.radio("Layout", ["Horizontal", "Vertical"], horizontal=True, index=0)
with col3:
    depth_text = st.text_input("Initial generations shown", value="3")

try:
    initial_depth = max(1, int(depth_text.strip()))
except Exception:
    initial_depth = 3

# Use your cleaned file (recommended)
path = Path("tree_clean.json") if Path("tree_clean.json").exists() else Path("tree.json")
if not path.exists():
    st.error("tree.json or tree_clean.json not found in this folder.")
    st.stop()

data = json.loads(path.read_text(encoding="utf-8"))

# ---- Normalize + ensure ONE root for d3.stratify ----
ids = {str(n.get("id")) for n in data if n.get("id") is not None}

norm = []
for n in data:
    pid = str(n.get("id")).strip()
    if not pid:
        continue
    parent = n.get("parentId")
    parent = str(parent).strip() if parent not in (None, "", "null") else None
    name = (n.get("name") or "").strip()

    # If parent points to missing ID, attach to ROOT
    if parent is not None and parent not in ids:
        parent = "ROOT"

    norm.append({"id": pid, "parentId": parent, "name": name})

# Attach all roots to ROOT
for n in norm:
    if n["parentId"] is None:
        n["parentId"] = "ROOT"

# Add the super root node
norm.append({"id": "ROOT", "parentId": None, "name": "Somali Family Tree"})

# ---- Optional filtering to selected major clan subtrees ----
if selected_root_ids:
    # Build parent->children map
    children_map: dict[str, list[str]] = {}
    nodes_by_id: dict[str, dict] = {}
    for n in norm:
        nodes_by_id[str(n["id"])] = n
        pid = n.get("parentId")
        if pid is None:
            continue
        children_map.setdefault(str(pid), []).append(str(n["id"]))

    # Collect all descendants of each selected clan root id
    keep_ids: set[str] = set(["ROOT"])  # always keep ROOT

    stack = list(selected_root_ids)
    while stack:
        cur = stack.pop()
        if cur in keep_ids:
            continue
        keep_ids.add(cur)
        for ch in children_map.get(cur, []):
            stack.append(ch)

    # Build filtered node list; attach any kept node whose parent isn't kept to ROOT
    filtered = []
    for nid in keep_ids:
        if nid == "ROOT":
            continue
        n = nodes_by_id.get(nid)
        if not n:
            continue
        parent = n.get("parentId")
        parent = str(parent) if parent is not None else None
        if parent is None or parent not in keep_ids:
            parent = "ROOT"
        filtered.append({"id": str(n["id"]), "parentId": parent, "name": n.get("name", "")})

    filtered.append({"id": "ROOT", "parentId": None, "name": "Somali Family Tree"})
    norm = filtered

html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Somali Family Tree (D3 Tree)</title>
  <script src="https://d3js.org/d3.v7.min.js"></script>
  <style>
    body { margin: 0; font-family: Arial, sans-serif; }
    svg { width: 100vw; height: 95vh; display: block; background: #f7f7f7; }
    .link { fill: none; stroke: #9aa0a6; stroke-opacity: 0.7; stroke-width: 1.3px; }
    .node circle { stroke: #2f2f2f; stroke-width: 1px; fill: #ffffff; }
    .node.has-children circle { fill: #f0f7ff; }
    .node.collapsed circle { fill: #ffe9b0; }
    .node.hover circle { stroke-width: 2.5px; }
    .label { font-size: 12px; dominant-baseline: middle; user-select: none; pointer-events: none; }
    .tooltip {
      position: absolute;
      background: rgba(20,20,20,0.92);
      color: #fff;
      padding: 8px 10px;
      border-radius: 8px;
      font-size: 12px;
      line-height: 1.35;
      max-width: 320px;
      pointer-events: none;
      opacity: 0;
      transform: translateY(4px);
      transition: opacity 120ms ease, transform 120ms ease;
    }
  </style>
</head>
<body>
  <svg id="svg"></svg>
  <div id="tooltip" class="tooltip"></div>

  <script>
    const data = __DATA__;
    const ORIENTATION = __ORIENTATION__; // "horizontal" | "vertical"
    const INITIAL_DEPTH = __INITIAL_DEPTH__;

    const svg = d3.select("#svg");
    const tooltip = d3.select("#tooltip");

    // Containers
    const g = svg.append("g");
    const gLinks = g.append("g");
    const gNodes = g.append("g");

    // Zoom (also hide labels when zoomed far out for performance)
    const zoom = d3.zoom()
      .scaleExtent([0.08, 6])
      .on("zoom", (event) => {
        g.attr("transform", event.transform);
        const k = event.transform.k;
        g.selectAll("text.label").style("display", k < 0.45 ? "none" : null);
      });
    svg.call(zoom);

    // Stratify (requires exactly one root)
    const root = d3.stratify()
      .id(d => String(d.id))
      .parentId(d => d.parentId ? String(d.parentId) : null)(data);

    // Layout sizing
    const dx = 24;
    const dy = 210;
    const treeLayout = d3.tree().nodeSize([dx, dy]);

    // Collapse everything deeper than INITIAL_DEPTH
    function collapse(d) {
      if (d.children) {
        d._children = d.children;
        d._children.forEach(collapse);
        d.children = null;
      }
    }
    root.each(d => {
      // Show INITIAL_DEPTH generations expanded; collapse depth INITIAL_DEPTH+1 and deeper
      if (d.depth > INITIAL_DEPTH) collapse(d);
    });

    // Track last position for transitions
    root.x0 = 0;
    root.y0 = 0;

    let didInitTransform = false;
    const duration = 140; // keep small for 10k nodes

    function nodeTransform(d) {
      return ORIENTATION === "horizontal"
        ? `translate(${d.y},${d.x})`
        : `translate(${d.x},${d.y})`;
    }

    function linkPath() {
      return ORIENTATION === "horizontal"
        ? d3.linkHorizontal().x(d => d.y).y(d => d.x)
        : d3.linkVertical().x(d => d.x).y(d => d.y);
    }

    function update(source) {
      // Recompute layout
      treeLayout(root);

      // Set y by depth for consistent spacing
      root.each(d => { d.y = d.depth * dy; });

      const nodes = root.descendants();
      const links = root.links();

      // Compute bounds for auto-centering (based on x/y depending on orientation)
      let minA = Infinity, maxA = -Infinity;
      nodes.forEach(d => {
        const a = ORIENTATION === "horizontal" ? d.x : d.y;
        if (a < minA) minA = a;
        if (a > maxA) maxA = a;
      });

      // Do the auto-center only once (initial render). Otherwise, expanding a node would
      // keep yanking the camera around.
      if (!didInitTransform) {
        const h = window.innerHeight;
        const pad = 60;
        const initial = d3.zoomIdentity
          .translate(pad, (h - (maxA - minA)) / 2 - minA)
          .scale(1);
        svg.call(zoom.transform, initial);
        didInitTransform = true;
      }

      // ----- Links -----
      const link = gLinks.selectAll("path.link")
        .data(links, d => d.target.id);

      link.join(
        enter => enter.append("path")
          .attr("class", "link")
          .attr("d", () => {
            // draw from source previous position
            const o = {x: source.x0, y: source.y0};
            return linkPath()({source: o, target: o});
          }),
        update => update,
        exit => exit.remove()
      )
      .transition().duration(duration)
      .attr("d", linkPath());

      // ----- Nodes -----
      const node = gNodes.selectAll("g.node")
        .data(nodes, d => d.id);

      const nodeEnter = node.enter().append("g")
        .attr("class", "node")
        .attr("transform", () => nodeTransform({x: source.x0, y: source.y0}))
        .style("cursor", "pointer")
        .on("click", (event, d) => {
          if (d.children) {
            d._children = d.children;
            d.children = null;
          } else {
            d.children = d._children;
            d._children = null;
          }
          update(d);
        })
        .on("mousemove", (event, d) => {
          tooltip
            .style("opacity", 1)
            .style("transform", "translateY(0px)")
            .style("left", (event.pageX + 14) + "px")
            .style("top", (event.pageY + 14) + "px")
            .html(
              `<div style="font-weight:700; margin-bottom:2px;">${d.data.name || d.id}</div>`
              + `<div style="opacity:.85">ID: ${d.id}</div>`
              + `<div style="opacity:.85">Generation: ${d.depth}</div>`
              + (d.parent ? `<div style="opacity:.85">Parent: ${(d.parent.data && d.parent.data.name) ? d.parent.data.name : d.parent.id}</div>` : "")
            );
          d3.select(event.currentTarget).classed("hover", true);
        })
        .on("mouseleave", (event) => {
          tooltip.style("opacity", 0).style("transform", "translateY(4px)");
          d3.select(event.currentTarget).classed("hover", false);
        });

      nodeEnter.append("circle").attr("r", 5.5);

      // Label above the node (not to the side)
      nodeEnter.append("text")
        .attr("class", "label")
        .attr("x", 0)
        .attr("y", -10)
        .attr("text-anchor", "middle")
        .text(d => d.data.name || d.id);

      const nodeMerged = nodeEnter.merge(node);

      nodeMerged
        .classed("has-children", d => !!(d.children || d._children))
        .classed("collapsed", d => !!d._children && !d.children)
        .transition().duration(duration)
        .attr("transform", d => nodeTransform(d));

      node.exit().remove();

      // Stash old positions for transition
      nodes.forEach(d => {
        d.x0 = d.x;
        d.y0 = d.y;
      });
    }

    update(root);
  </script>
</body>
</html>
"""

html = (
    html.replace("__DATA__", json.dumps(norm))
        .replace("__ORIENTATION__", json.dumps(orientation.lower()))
        .replace("__INITIAL_DEPTH__", str(int(initial_depth)))
)

components.html(html, height=900, scrolling=True)
