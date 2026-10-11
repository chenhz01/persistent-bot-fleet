#!/usr/bin/env python3
"""Self-test for persistent-bot-fleet (ALIGNMENT rule 97 three families).

Run:  python self_test.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fleet as fl  # noqa: E402

results = []


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))


# ------------------------------------------------------------- functional ---
def test_functional(tmp):
    path = os.path.join(tmp, "fleet.json")
    f = fl.Fleet(path)
    f.spawn("lead", role="coordinator")
    f.spawn("scout")
    f.send("lead", "scout", "go east")
    f.save()

    # Restart: persistence roundtrip
    f2 = fl.Fleet(path)
    record("functional: bots survive restart",
           f2.roster() == [("lead", "coordinator"), ("scout", "worker")])
    inbox = f2.inbox("scout")
    record("functional: message survives restart",
           len(inbox) == 1 and inbox[0]["text"] == "go east")

    n = f2.broadcast("lead", "standby")
    record("functional: broadcast reaches others only", n == 1)

    drained = f2.drain("scout")
    record("functional: drain removes from bus",
           len(drained) == 2 and f2.inbox("scout") == [])
    f2.save()
    record("functional: drained state persists", fl.Fleet(path).inbox("scout") == [])


# ----------------------------------------------------------- error paths ---
def test_errors(tmp):
    path = os.path.join(tmp, "err.json")
    f = fl.Fleet(path)
    f.spawn("a")

    for name, fn in [
        ("send to unknown bot", lambda: f.send("a", "ghost", "hi")),
        ("send from unknown bot", lambda: f.send("ghost", "a", "hi")),
        ("duplicate spawn", lambda: (f.spawn("a"), f.save())),
        ("empty text", lambda: f.send("a", "a", "  ")),
        ("self-message", lambda: f.send("a", "a", "note")),
    ]:
        try:
            fn()
            record(f"error: {name} raises FleetError", False)
        except fl.FleetError:
            record(f"error: {name} raises FleetError", True)

    # Corrupted state (bit-flip inside body)
    path2 = os.path.join(tmp, "corrupt.json")
    g = fl.Fleet(path2)
    g.spawn("x")
    g.save()
    with open(path2, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["body"]["bots"]["x"]["role"] = "hacked"
    with open(path2, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    try:
        fl.Fleet(path2)
        record("error: tampered state rejected by checksum", False)
    except fl.FleetError:
        record("error: tampered state rejected by checksum", True)


# ------------------------------------------------------------ edge cases ---
def test_edges(tmp):
    path = os.path.join(tmp, "edge.json")
    f = fl.Fleet(path)
    record("edge: empty fleet roster", f.roster() == [])

    f.spawn("big")
    long_text = "x" * (fl.MAX_TEXT + 1)
    try:
        f.send("big", "big", long_text)  # will hit self-send first; bypass:
        record("edge: oversized text rejected", False)
    except fl.FleetError:
        record("edge: oversized text rejected (self-send guard first)", True)

    f.spawn("b")
    try:
        f.send("big", "b", long_text)
        record("edge: oversized text rejected", False)
    except fl.FleetError:
        record("edge: oversized text rejected", True)

    # 200KB message is accepted and persists
    f.send("big", "b", "y" * 200_000)
    f.save()
    f2 = fl.Fleet(path)
    record("edge: 200KB message roundtrip",
           len(f2.inbox("b")[0]["text"]) == 200_000)

    # 10k messages: fan-in throughput sanity (in-memory, before save)
    f3 = fl.Fleet(os.path.join(tmp, "scale.json"))
    f3.spawn("s")
    f3.spawn("sink")
    for i in range(10_000):
        f3.send("s", "sink", f"m{i}")
    record("edge: 10k messages delivered", len(f3.inbox("sink")) == 10_000)

    # Garbage state file
    garbage = os.path.join(tmp, "garbage.json")
    with open(garbage, "w", encoding="utf-8") as fh:
        fh.write("not json at all {{{")
    try:
        fl.Fleet(garbage)
        record("edge: garbage state file raises", False)
    except fl.FleetError:
        record("edge: garbage state file raises", True)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        test_functional(tmp)
        test_errors(tmp)
        test_edges(tmp)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
