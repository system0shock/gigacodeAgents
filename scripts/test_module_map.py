#!/usr/bin/env python3
"""Offline tests for scripts/build_module_map.py. Run from the repo root:
    python scripts/test_module_map.py"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILDER = os.path.join(ROOT, "scripts", "build_module_map.py")
PASSED = 0


def check(name, condition, detail=""):
    # explicit raise (not assert) so python -O cannot neuter the suite
    global PASSED
    if not condition:
        raise SystemExit(f"FAIL {name}: {detail}")
    PASSED += 1
    print(f"ok: {name}")


def sample_graph():
    return {
        "nodes": [
            {"id": "a_PaymentService", "label": "PaymentService",
             "community": 0, "source_file": "src/PaymentService.kt"},
            {"id": "a_PaymentRepo", "label": "PaymentRepo",
             "community": 0, "source_file": "src/PaymentRepo.kt"},
            {"id": "b_FraudCheck", "label": "FraudCheck",
             "community": 1, "source_file": "src/FraudCheck.kt"},
        ],
        "links": [
            {"source": "a_PaymentService", "target": "a_PaymentRepo",
             "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "a_PaymentService", "target": "b_FraudCheck",
             "relation": "shares_data_with", "confidence": "INFERRED"},
        ],
        "hyperedges": [
            {"id": "payment_flow", "label": "Payment flow",
             "nodes": ["a_PaymentService", "a_PaymentRepo", "b_FraudCheck"],
             "relation": "participate_in"},
        ],
    }


def run_builder(tmp, graph=None, extra_args=None):
    """Run the builder CLI; returns (rc, combined_output, map_text)."""
    graph_path = os.path.join(tmp, "graph.json")
    if graph is not None:
        with open(graph_path, "w", encoding="utf-8") as handle:
            json.dump(graph, handle)
    out_path = os.path.join(tmp, "module-map.md")
    cmd = [sys.executable, BUILDER, "--graph", graph_path, "--out", out_path]
    cmd += extra_args or []
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, encoding="utf-8", timeout=30)
    text = ""
    if os.path.exists(out_path):
        with open(out_path, "r", encoding="utf-8") as handle:
            text = handle.read()
    return proc.returncode, proc.stdout, text


def main():
    with tempfile.TemporaryDirectory(prefix="module-map-test-") as tmp:
        rc, out, text = run_builder(tmp, sample_graph())
        check("map_builds", rc == 0, out)
        check("map_header", text.startswith("# Module Map"), text[:80])
        check("map_module_section", "## Module 0 (2 nodes)" in text, text)
        check("map_key_symbol", "PaymentService (src/PaymentService.kt)" in text, text)
        check("map_bridge",
              "PaymentService (M0) --shares_data_with--> FraudCheck (M1)" in text, text)
        check("map_hyperedge", "Payment flow: " in text, text)

    with tempfile.TemporaryDirectory(prefix="module-map-test-") as tmp:
        rc, out, text = run_builder(tmp, sample_graph(), ["--max-lines", "5"])
        check("map_line_cap", rc == 0 and "truncated" in text, text)

    with tempfile.TemporaryDirectory(prefix="module-map-test-") as tmp:
        rc, out, _ = run_builder(tmp, None)  # graph file absent
        check("map_missing_graph_fails", rc != 0, (rc, out))
        rc, out, _ = run_builder(tmp, {"nodes": [], "links": []})
        check("map_empty_graph_fails", rc != 0, (rc, out))
        rc, out, _ = run_builder(tmp, sample_graph(), ["--max-lines", "0"])
        check("map_invalid_max_lines_fails", rc != 0, (rc, out))

    with tempfile.TemporaryDirectory(prefix="module-map-test-") as tmp:
        # null community renders as 'unassigned'; dangling link must not crash
        graph = {"nodes": [{"id": "x_Lone", "label": "Lone"}],
                 "links": [{"source": "x_Lone", "target": "ghost_Node",
                            "relation": "calls"}]}
        rc, out, text = run_builder(tmp, graph)
        check("map_null_community",
              rc == 0 and "## Module unassigned (1 nodes)" in text, (rc, out, text))

    print(f"\nAll {PASSED} module-map checks passed")


if __name__ == "__main__":
    main()
