#!/usr/bin/env python3
"""Build .gigacode/context/module-map.md from graphify-out/graph.json.

The map is injected into agent context by gate_context_inject (SessionStart /
SubagentStart), so it must stay compact: communities with their key symbols,
cross-module links and named flows, capped at --max-lines.

Stdlib-only and offline: reads the JSON graphify already wrote; never calls
graphify itself. A missing or empty graph exits 1 so humans and smoke runs
notice, while the gate simply skips the absent map file at runtime."""
import argparse
import json
import os
import sys
from collections import defaultdict


def load_graph(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        sys.exit(f"module-map: cannot read graph: {exc}")
    except json.JSONDecodeError as exc:
        sys.exit(f"module-map: graph is not valid JSON: {exc}")
    if not isinstance(data, dict) or not data.get("nodes"):
        sys.exit("module-map: graph has no nodes; run /graphify first")
    return data


def build_lines(data, graph_path):
    nodes = {n["id"]: n for n in data.get("nodes", [])
             if isinstance(n, dict) and "id" in n}
    links = [l for l in data.get("links", []) if isinstance(l, dict)]
    degree = defaultdict(int)
    for link in links:
        degree[link.get("source")] += 1
        degree[link.get("target")] += 1
    communities = defaultdict(list)
    for node in nodes.values():
        communities[node.get("community")].append(node)

    lines = ["# Module Map", "",
             f"Generated from {graph_path}: {len(nodes)} nodes, "
             f"{len(links)} edges, {len(communities)} communities.", ""]
    for cid, members in sorted(communities.items(),
                               key=lambda kv: (-len(kv[1]), str(kv[0]))):
        members.sort(key=lambda n: -degree[n["id"]])
        lines.append(f"## Module {cid} ({len(members)} nodes)")
        for node in members[:8]:
            label = node.get("label") or node["id"]
            src = node.get("source_file") or ""
            lines.append(f"- {label}" + (f" ({src})" if src else ""))
        lines.append("")

    bridges = []
    for link in links:
        a = nodes.get(link.get("source"))
        b = nodes.get(link.get("target"))
        if not a or not b or a.get("community") == b.get("community"):
            continue
        bridges.append(f"- {a.get('label') or a['id']} (M{a.get('community')}) "
                       f"--{link.get('relation', '?')}--> "
                       f"{b.get('label') or b['id']} (M{b.get('community')})")
    if bridges:
        lines.append("## Cross-module links")
        lines.extend(bridges[:10])
        lines.append("")

    hyper = [h for h in data.get("hyperedges", []) if isinstance(h, dict)]
    if hyper:
        lines.append("## Flows / groups")
        for edge in hyper[:10]:
            participants = [(nodes.get(nid) or {}).get("label", nid)
                            for nid in edge.get("nodes", [])[:6]]
            lines.append(f"- {edge.get('label') or edge.get('id', '?')}: "
                         + ", ".join(participants))
        lines.append("")
    return lines


def main():
    parser = argparse.ArgumentParser(
        description="Render graphify graph.json into .gigacode/context/module-map.md")
    parser.add_argument("--graph", default=os.path.join("graphify-out", "graph.json"))
    parser.add_argument("--out",
                        default=os.path.join(".gigacode", "context", "module-map.md"))
    parser.add_argument("--max-lines", type=int, default=120)
    args = parser.parse_args()

    data = load_graph(args.graph)
    lines = build_lines(data, args.graph.replace("\\", "/"))
    if len(lines) > args.max_lines:
        lines = lines[:max(args.max_lines, 1)] + ["", "(truncated: --max-lines reached)"]
    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    print(f"module-map: wrote {args.out} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
