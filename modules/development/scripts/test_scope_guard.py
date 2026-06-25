#!/usr/bin/env python3
"""Offline tests for gate_scope_guard (WI-8): code writes vs the frozen contract
scope. Run from modules/development:  python scripts/test_scope_guard.py"""
import importlib.util
import json
import os
import shutil
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATES_DIR = os.path.join(ROOT, ".gigacode", "hooks", "gates")
PASSED = 0


def load_gate(name):
    path = os.path.join(GATES_DIR, name + ".py")
    spec = importlib.util.spec_from_file_location("test_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(name, condition, detail=""):
    global PASSED
    if not condition:
        raise SystemExit(f"FAIL {name}: {detail}")
    PASSED += 1
    print(f"ok: {name}")


CARD = {"feature": "card", "status": "active",
        "scope_globs": ["src/cards/**"], "modules": ["cards"]}
PAY = {"feature": "pay", "status": "active",
       "scope_globs": ["src/payments/**"], "modules": ["payments"]}


def make_root(contracts=None, approved=None):
    tmp = tempfile.mkdtemp(prefix="scope-test-")
    os.makedirs(os.path.join(tmp, ".gigacode", "approvals"))
    for slug, obj in (contracts or {}).items():
        d = os.path.join(tmp, "docs", "development", slug)
        os.makedirs(d)
        with open(os.path.join(d, "contract.json"), "w", encoding="utf-8") as h:
            json.dump(obj, h)
    for slug in (approved or []):
        ad = os.path.join(tmp, ".gigacode", "approvals", slug)
        os.makedirs(ad, exist_ok=True)
        with open(os.path.join(ad, "contract.ok"), "w", encoding="utf-8") as h:
            h.write("{}")
    return tmp


class root_at:
    def __init__(self, tmp):
        self.tmp = tmp

    def __enter__(self):
        self._orig = os.environ.get("GIGACODE_ROOT")
        os.environ["GIGACODE_ROOT"] = self.tmp
        return self.tmp

    def __exit__(self, *exc):
        if self._orig is None:
            os.environ.pop("GIGACODE_ROOT", None)
        else:
            os.environ["GIGACODE_ROOT"] = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


def ev(path, tool="Edit"):
    return {"hook_event_name": "PreToolUse", "tool_name": tool,
            "tool_input": {"file_path": path}}


def decide(g, path, **kw):
    with root_at(make_root(**kw)):
        return g.run(ev(path))["decision"]


def test_scope():
    g = load_gate("gate_scope_guard")

    # contract exists but NOT approved -> guard not armed -> allow
    check("unapproved_not_armed_allow",
          decide(g, "src/payments/Y.kt", contracts={"card": CARD}) == "allow")

    # approved contract, write inside scope -> allow
    check("in_scope_allow",
          decide(g, "src/cards/CardService.kt", contracts={"card": CARD},
                 approved=["card"]) == "allow")
    check("in_scope_nested_allow",
          decide(g, "src/cards/dto/CardStatus.kt", contracts={"card": CARD},
                 approved=["card"]) == "allow")

    # approved contract, write OUTSIDE scope (code) -> ask (overshoot)
    check("out_of_scope_ask",
          decide(g, "src/payments/PaymentService.kt", contracts={"card": CARD},
                 approved=["card"]) == "ask")

    # non-code path -> allow (not governed)
    check("noncode_allow",
          decide(g, "README.md", contracts={"card": CARD}, approved=["card"]) == "allow")

    # excluded trees (docs/openspec/.gigacode) -> allow even for code-ish names
    check("docs_tree_allow",
          decide(g, "docs/development/card/journal.md", contracts={"card": CARD},
                 approved=["card"]) == "allow")
    check("openspec_tree_allow",
          decide(g, "openspec/changes/card/tasks.md", contracts={"card": CARD},
                 approved=["card"]) == "allow")

    # superseded contract does not arm the guard -> out-of-scope allowed
    sup = dict(CARD, status="superseded")
    check("superseded_not_armed_allow",
          decide(g, "src/payments/Y.kt", contracts={"card": sup},
                 approved=["card"]) == "allow")

    # union across two approved contracts: a write in EITHER scope is allowed
    check("union_in_scope_allow",
          decide(g, "src/payments/PaymentService.kt",
                 contracts={"card": CARD, "pay": PAY}, approved=["card", "pay"]) == "allow")
    # ...but still outside BOTH -> ask
    check("union_out_of_scope_ask",
          decide(g, "src/billing/Bill.kt",
                 contracts={"card": CARD, "pay": PAY}, approved=["card", "pay"]) == "ask")

    # no contracts at all -> guard inert
    check("no_contract_allow",
          decide(g, "src/anything/X.kt") == "allow")


def main():
    test_scope()
    print(f"\nAll {PASSED} scope_guard checks passed")


if __name__ == "__main__":
    main()
