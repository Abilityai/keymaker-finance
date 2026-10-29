#!/usr/bin/env python3
"""Send ONE approved draft. The only way Keymaker Finance sends anything.

    python3 scripts/mail.py check <draft.md>                    # parse + show, sends nothing
    python3 scripts/mail.py send <draft.md> --approved <request_id> [--confirm]

The draft is a markdown file with a front-matter block:

    ---
    to: someone@example.com
    subject: Invoice INV-KM-0004 from Keymaker
    from: Keymaker Finance <finance@keymaker.agency>
    reply_to: finance@keymaker.agency
    cc: eugene@ability.ai
    request_id: approval-INV-KM-0004-send
    ---
    Hi ...

`send` refuses unless the operator queue holds the ask named by --approved, answered
"send as written", AND that ask's request_id matches the draft's. A person pressed send; this
script only carries the letter. Needs RESEND_API_KEY (a sending-only key for the agency domain).
Without it: says so and sends nothing - the finance lead sends the draft by hand.
"""
import json, os, re, sys, urllib.request
from pathlib import Path

QUEUE = Path.home() / ".trinity" / "operator-queue.json"
APPROVE = "send as written"


def parse(path):
    text = Path(path).read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        sys.exit("draft has no front-matter block")
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    for k in ("to", "subject", "request_id"):
        if not meta.get(k):
            sys.exit(f"draft is missing '{k}'")
    return meta, m.group(2).strip()


def env_file_value(name):
    """Credentials injected as ~/.env are not always exported to the shell."""
    f = Path.home() / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"')
    return None


def find_ask(request_id):
    if not QUEUE.exists():
        return None
    data = json.loads(QUEUE.read_text() or "{}")
    stack = [data]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            if x.get("id") == request_id or x.get("request_id") == request_id:
                return x
            stack.extend(x.values())
        elif isinstance(x, list):
            stack.extend(x)
    return None


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("check", "send"):
        sys.exit(__doc__)
    cmd, path = sys.argv[1], sys.argv[2]
    meta, body = parse(path)
    print(f"to: {meta['to']}\ncc: {meta.get('cc', '-')}\nsubject: {meta['subject']}\nrequest_id: {meta['request_id']}\n\n{body}\n")
    if cmd == "check":
        return
    args = sys.argv[3:]
    if "--approved" not in args:
        sys.exit("REFUSED: no --approved <request_id>. A person approves every send.")
    rid = args[args.index("--approved") + 1]
    if rid != meta["request_id"]:
        sys.exit(f"REFUSED: approval {rid} is for a different draft ({meta['request_id']}).")
    ask = find_ask(rid)
    answer = (ask or {}).get("response")
    if not ask or ask.get("status") != "responded" or str(answer).strip().lower() != APPROVE:
        sys.exit(f"REFUSED: ask {rid} is not answered '{APPROVE}' (status={ask and ask.get('status')}, response={answer!r}).")
    if "--confirm" not in args:
        sys.exit("approved - re-run with --confirm to send")
    key = os.environ.get("RESEND_API_KEY") or env_file_value("RESEND_API_KEY")
    if not key:
        sys.exit("NOT SENT: no RESEND_API_KEY on this agent. The draft is approved - the deal owner sends it by hand.")
    payload = {
        "from": meta.get("from", "Keymaker Finance <finance@keymaker.agency>"),
        "to": [a.strip() for a in meta["to"].split(",")],
        "subject": meta["subject"],
        "text": body,
        "headers": {"X-Keymaker-Approval": rid},
    }
    if meta.get("cc"):
        payload["cc"] = [a.strip() for a in meta["cc"].split(",")]
    if meta.get("reply_to"):
        payload["reply_to"] = meta["reply_to"]
    req = urllib.request.Request("https://api.resend.com/emails", data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                          "Idempotency-Key": rid, "User-Agent": "keymaker-finance/0.1"})
    with urllib.request.urlopen(req, timeout=20) as r:
        out = json.loads(r.read())
    print(f"SENT: resend id {out.get('id')}")


if __name__ == "__main__":
    main()
