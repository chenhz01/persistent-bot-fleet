#!/usr/bin/env python3
"""persistent-bot-fleet: long-lived bots over a file-backed message bus.

A minimal fleet runtime: bots are persistent entries (name + role), the
"group" is the bus, bot-to-bot messages are the cheapest possible inter-agent
protocol. State lives in one JSON file with an integrity checksum, so the
fleet survives restarts and detects corruption.

Pure stdlib. Atomic writes (tmp + os.replace) prevent torn state files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time

SCHEMA = 1
MAX_TEXT = 1_000_000  # 1 MB per message body
MAX_BOTS = 1000


class FleetError(Exception):
    """Usage errors: unknown bot, duplicate spawn, corrupt state."""


def _now() -> float:
    return time.time()


def _checksum(body: dict) -> str:
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class Fleet:
    def __init__(self, state_path: str):
        self.state_path = state_path
        self.bots: dict[str, dict] = {}
        self.messages: list[dict] = []
        self._seq = 0
        if os.path.exists(state_path):
            self._load()

    # ------------------------------------------------------- persistence ---
    def _load(self):
        try:
            with open(self.state_path, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise FleetError(f"state file corrupted: {exc}") from exc
        body = doc.get("body")
        if not isinstance(body, dict):
            raise FleetError("state file corrupted: missing body")
        if doc.get("checksum") != _checksum(body):
            raise FleetError("state file corrupted: checksum mismatch")
        if doc.get("schema") != SCHEMA:
            raise FleetError(f"unsupported schema {doc.get('schema')!r}")
        self.bots = body.get("bots", {})
        self.messages = body.get("messages", [])
        self._seq = body.get("seq", len(self.messages))

    def save(self):
        body = {"bots": self.bots, "messages": self.messages, "seq": self._seq}
        doc = {"schema": SCHEMA, "checksum": _checksum(body), "body": body}
        d = os.path.dirname(os.path.abspath(self.state_path))
        fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, ensure_ascii=False)
            os.replace(tmp, self.state_path)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    # ------------------------------------------------------------ fleet ---
    def spawn(self, name: str, role: str = "worker") -> None:
        if not name or not name.strip():
            raise FleetError("bot name must be non-empty")
        if len(self.bots) >= MAX_BOTS:
            raise FleetError(f"fleet full ({MAX_BOTS} bots)")
        if name in self.bots:
            raise FleetError(f"bot {name!r} already exists")
        self.bots[name] = {"role": role or "worker", "joined": _now()}

    def _require(self, name: str, what: str) -> None:
        if name not in self.bots:
            raise FleetError(f"{what} {name!r} is not in the fleet")

    def send(self, src: str, dst: str, text: str) -> int:
        self._require(src, "sender")
        self._require(dst, "recipient")
        if src == dst:
            raise FleetError("self-messages are not allowed (use a journal)")
        if not isinstance(text, str) or not text.strip():
            raise FleetError("message text must be a non-empty string")
        if len(text) > MAX_TEXT:
            raise FleetError(f"message exceeds MAX_TEXT ({MAX_TEXT})")
        self._seq += 1
        self.messages.append(
            {"seq": self._seq, "src": src, "dst": dst, "text": text, "ts": _now()})
        return self._seq

    def broadcast(self, src: str, text: str) -> int:
        self._require(src, "sender")
        if not isinstance(text, str) or not text.strip():
            raise FleetError("message text must be a non-empty string")
        if len(text) > MAX_TEXT:
            raise FleetError(f"message exceeds MAX_TEXT ({MAX_TEXT})")
        n = 0
        for dst in self.bots:
            if dst != src:
                self.send(src, dst, text)
                n += 1
        return n

    def inbox(self, name: str) -> list[dict]:
        self._require(name, "bot")
        return [m for m in self.messages if m["dst"] == name]

    def drain(self, name: str) -> list[dict]:
        msgs = self.inbox(name)
        self.messages = [m for m in self.messages if m["dst"] != name]
        return msgs

    def roster(self) -> list[tuple[str, str]]:
        return sorted((n, b["role"]) for n, b in self.bots.items())


# -------------------------------------------------------------------- CLI ---
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="fleet", description="Persistent bot fleet on a file-backed bus.")
    ap.add_argument("--state", default="fleet.json")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("spawn"); p.add_argument("name"); p.add_argument("--role", default="worker")
    p = sub.add_parser("send"); p.add_argument("src"); p.add_argument("dst"); p.add_argument("text")
    p = sub.add_parser("broadcast"); p.add_argument("src"); p.add_argument("text")
    p = sub.add_parser("inbox"); p.add_argument("name"); p.add_argument("--drain", action="store_true")
    sub.add_parser("list")

    args = ap.parse_args(argv)
    try:
        fleet = Fleet(args.state)
        if args.cmd == "spawn":
            fleet.spawn(args.name, args.role)
            fleet.save()
            print(f"spawned {args.name} (role={args.role})")
        elif args.cmd == "send":
            seq = fleet.send(args.src, args.dst, args.text)
            fleet.save()
            print(f"delivered seq={seq}")
        elif args.cmd == "broadcast":
            n = fleet.broadcast(args.src, args.text)
            fleet.save()
            print(f"broadcast to {n} bots")
        elif args.cmd == "inbox":
            msgs = fleet.drain(args.name) if args.drain else fleet.inbox(args.name)
            for m in msgs:
                print(f"[{m['seq']}] {m['src']} -> {m['dst']}: {m['text']}")
            if not msgs:
                print("(empty)")
        elif args.cmd == "list":
            for name, role in fleet.roster():
                print(f"{name}\t{role}")
        return 0
    except (FleetError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
