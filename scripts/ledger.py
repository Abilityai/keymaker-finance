#!/usr/bin/env python3
"""
The one way Keymaker Finance reads and writes its books.

Backend: ledger/invoices.yaml in this repo (this public cut has no accounting-system adapter).

Commands:
  python3 scripts/ledger.py list [--status Draft|Approved|Sent|Paid|Void] [--overdue] [--deal SLUG]
  python3 scripts/ledger.py show <number>
  python3 scripts/ledger.py create --deal SLUG --client NAME --contact "Name <email>" --offer NAME \
          --line "description=amount" [--line ...] [--credit N] [--due-days 14] [--confirm]
  python3 scripts/ledger.py approve <number> --ask <request_id> [--confirm]
  python3 scripts/ledger.py mark-sent <number> --via "resend <id>"|"by hand" [--confirm]
  python3 scripts/ledger.py mark-paid <number> --amount N --ref TEXT --date YYYY-MM-DD [--confirm]
  python3 scripts/ledger.py remind <number> --stage "Day 1"|"Day 7"|"Day 14" --ask <request_id> [--confirm]
  python3 scripts/ledger.py void <number> --reason TEXT [--confirm]
  python3 scripts/ledger.py note <number> --text "..." [--confirm]
  python3 scripts/ledger.py summary

Every write prints the change it is about to make and refuses without --confirm.
`create` also writes the invoice document invoices/<number>.md from the ledger row.
"""
import argparse
import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "ledger", "invoices.yaml")
INSTRUCTIONS = os.path.join(ROOT, "ledger", "payment_instructions.md")
INVOICES_DIR = os.path.join(ROOT, "invoices")

STATUSES = ["Draft", "Approved", "Sent", "Paid", "Void"]
OPEN = ["Sent"]  # money we are owed
STAGES = ["Day 1", "Day 7", "Day 14"]


def _yaml():
    try:
        import yaml  # type: ignore
        return yaml
    except ImportError:
        sys.exit("PyYAML is not installed: pip install pyyaml")


def load():
    yaml = _yaml()
    with open(LEDGER) as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("invoices", [])
    data.setdefault("next_number", len(data["invoices"]) + 1)
    return data


def save(data):
    yaml = _yaml()
    with open(LEDGER, "w") as f:
        f.write("# File-backed invoice ledger (the only backend of scripts/ledger.py in this public cut).\n")
        f.write("# Sample invoices for a fictional agency - edit freely. Statuses must match CLAUDE.md.\n")
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def today():
    return dt.date.today().isoformat()


def find(data, number):
    for inv in data["invoices"]:
        if inv["number"].lower() == number.lower():
            return inv
    sys.exit(f"no invoice {number}")


def days_overdue(inv, on=None):
    if inv["status"] not in OPEN:
        return 0
    on = on or dt.date.today()
    due = dt.date.fromisoformat(str(inv["due"]))
    return max(0, (on - due).days)


def gate(desc, confirm):
    print("CHANGE: " + desc)
    if not confirm:
        sys.exit("refused: re-run with --confirm to write this change")


def money(n):
    return f"${n:,.0f}" if float(n).is_integer() else f"${n:,.2f}"


# ------------------------------------------------------------------------------------ commands
def cmd_list(a):
    data = load()
    rows = data["invoices"]
    if a.status:
        rows = [r for r in rows if r["status"].lower() == a.status.lower()]
    if a.deal:
        rows = [r for r in rows if r.get("deal") == a.deal]
    if a.overdue:
        rows = [r for r in rows if days_overdue(r) > 0]
    print(f"{'NUMBER':<13} {'STATUS':<9} {'CLIENT':<28} {'TOTAL':>10} {'DUE':<11} {'OVERDUE':>7}  DEAL")
    for r in rows:
        od = days_overdue(r)
        print(f"{r['number']:<13} {r['status']:<9} {r['client'][:28]:<28} {money(r['total_usd']):>10} {str(r['due']):<11} {(str(od)+'d') if od else '-':>7}  {r.get('deal','')}")
    if not rows:
        print("(none)")


def cmd_show(a):
    inv = find(load(), a.number)
    yaml = _yaml()
    print(yaml.safe_dump(inv, sort_keys=False, allow_unicode=True))
    od = days_overdue(inv)
    if od:
        print(f"OVERDUE by {od} days; reminders sent: {len(inv.get('reminders') or [])}")


def write_document(inv):
    os.makedirs(INVOICES_DIR, exist_ok=True)
    instructions = open(INSTRUCTIONS).read().strip() if os.path.exists(INSTRUCTIONS) else "(payment instructions missing - add ledger/payment_instructions.md)"
    lines = "\n".join(f"| {l['description']} | {money(l['amount_usd'])} |" for l in inv["lines"])
    doc = f"""# Invoice {inv['number']}

**From:** Keymaker Agency - finance@keymaker.agency
**To:** {inv['client']} - {inv['billing_contact']}
**Deal:** {inv.get('deal','')} · **Offer:** {inv['offer']}
**Issued:** {inv['issued']} · **Due:** {inv['due']} · **Status:** {inv['status']}

| Line | Amount |
|---|---|
{lines}
| **Total due** | **{money(inv['total_usd'])}** |

{instructions}
"""
    path = os.path.join(INVOICES_DIR, f"{inv['number']}.md")
    with open(path, "w") as f:
        f.write(doc)
    return path


def cmd_create(a):
    data = load()
    for r in data["invoices"]:
        if r.get("deal") == a.deal and r["status"] not in ("Void", "Paid") and r["offer"] == a.offer:
            sys.exit(f"refused: {r['number']} already covers {a.offer} for {a.deal} ({r['status']}). Void it first or record a payment.")
    lines = []
    for item in a.line:
        if "=" not in item:
            sys.exit(f"--line needs description=amount, got {item!r}")
        desc, amt = item.rsplit("=", 1)
        lines.append({"description": desc.strip(), "amount_usd": float(amt)})
    if not lines:
        sys.exit("at least one --line is required")
    credit = float(a.credit or 0)
    if credit:
        lines.append({"description": f"Credit (approved on the deal)", "amount_usd": -credit})
    total = sum(l["amount_usd"] for l in lines)
    number = f"INV-KM-{data['next_number']:04d}"
    issued = dt.date.today()
    due = issued + dt.timedelta(days=a.due_days)
    inv = {
        "number": number, "client": a.client, "deal": a.deal, "billing_contact": a.contact,
        "offer": a.offer, "lines": lines, "credit_usd": credit, "total_usd": total,
        "issued": issued.isoformat(), "due": due.isoformat(), "status": "Draft",
        "approval": None, "sent_at": None, "sent_via": None, "paid_at": None, "payment_ref": None,
        "reminders": [], "notes": [f"{issued.isoformat()} Drafted from the won deal {a.deal}."],
    }
    gate(f"create {number} for {a.client} ({a.offer}) total {money(total)} due {due}, status Draft; write invoices/{number}.md", a.confirm)
    data["invoices"].append(inv)
    data["next_number"] += 1
    save(data)
    path = write_document(inv)
    print(f"created {number} -> {os.path.relpath(path, ROOT)}")


def cmd_approve(a):
    data = load()
    inv = find(data, a.number)
    if inv["status"] != "Draft":
        sys.exit(f"refused: {inv['number']} is {inv['status']}, only a Draft can be approved")
    gate(f"{inv['number']} Draft -> Approved (ask {a.ask} answered 'send as written')", a.confirm)
    inv["status"] = "Approved"
    inv["approval"] = a.ask
    inv["notes"].append(f"{today()} Approved by the finance lead ({a.ask}).")
    save(data)
    write_document(inv)
    print("ok")


def cmd_mark_sent(a):
    data = load()
    inv = find(data, a.number)
    if inv["status"] != "Approved":
        sys.exit(f"refused: {inv['number']} is {inv['status']}; only an Approved invoice can be marked Sent")
    gate(f"{inv['number']} Approved -> Sent via {a.via}", a.confirm)
    inv["status"] = "Sent"
    inv["sent_at"] = today()
    inv["sent_via"] = a.via
    inv["notes"].append(f"{today()} Sent ({a.via}).")
    save(data)
    write_document(inv)
    print("ok")


def cmd_mark_paid(a):
    data = load()
    inv = find(data, a.number)
    if inv["status"] not in ("Sent", "Approved"):
        sys.exit(f"refused: {inv['number']} is {inv['status']}")
    amount = float(a.amount)
    if abs(amount - float(inv["total_usd"])) > 0.01:
        sys.exit(f"refused: payment {money(amount)} does not match total {money(inv['total_usd'])}. A partial payment or an over-payment is a person's decision - note it and ask.")
    gate(f"{inv['number']} {inv['status']} -> Paid, {money(amount)} ref {a.ref!r} on {a.date}", a.confirm)
    inv["status"] = "Paid"
    inv["paid_at"] = a.date
    inv["payment_ref"] = a.ref
    inv["notes"].append(f"{a.date} Paid in full, {a.ref}.")
    save(data)
    write_document(inv)
    print("ok")


def cmd_remind(a):
    data = load()
    inv = find(data, a.number)
    if days_overdue(inv) == 0:
        sys.exit(f"refused: {inv['number']} is not overdue")
    done = [r["stage"] for r in inv.get("reminders") or []]
    if a.stage in done:
        sys.exit(f"refused: {a.stage} reminder already recorded for {inv['number']}")
    expected = STAGES[len(done)] if len(done) < len(STAGES) else None
    if expected and a.stage != expected:
        sys.exit(f"refused: next stage for {inv['number']} is {expected!r}, not {a.stage!r}")
    gate(f"{inv['number']} record {a.stage} reminder sent (ask {a.ask})", a.confirm)
    inv.setdefault("reminders", []).append({"date": today(), "stage": a.stage, "approval": a.ask})
    inv["notes"].append(f"{today()} {a.stage} reminder sent after approval ({a.ask}).")
    save(data)
    print("ok")


def cmd_void(a):
    data = load()
    inv = find(data, a.number)
    if inv["status"] == "Paid":
        sys.exit("refused: a Paid invoice is never voided; a refund is the principal's decision, outside this desk")
    gate(f"{inv['number']} {inv['status']} -> Void: {a.reason}", a.confirm)
    inv["status"] = "Void"
    inv["notes"].append(f"{today()} Voided: {a.reason}")
    save(data)
    write_document(inv)
    print("ok")


def cmd_note(a):
    data = load()
    inv = find(data, a.number)
    gate(f"{inv['number']} add note: {a.text}", a.confirm)
    inv["notes"].append(f"{today()} {a.text}")
    save(data)
    print("ok")


def cmd_summary(a):
    data = load()
    month = today()[:7]
    outstanding = sum(float(r["total_usd"]) for r in data["invoices"] if r["status"] in OPEN)
    overdue = [r for r in data["invoices"] if days_overdue(r) > 0]
    invoiced = sum(float(r["total_usd"]) for r in data["invoices"] if r["status"] in ("Approved", "Sent", "Paid") and str(r["issued"]).startswith(month))
    paid = sum(float(r["total_usd"]) for r in data["invoices"] if r["status"] == "Paid" and str(r.get("paid_at") or "").startswith(month))
    print(f"outstanding_usd: {outstanding:.0f}")
    print(f"overdue_invoices: {len(overdue)}")
    print(f"invoiced_month_usd: {invoiced:.0f}")
    print(f"paid_month_usd: {paid:.0f}")
    for r in overdue:
        nxt = STAGES[len(r.get('reminders') or [])] if len(r.get('reminders') or []) < len(STAGES) else "a person decides"
        print(f"  {r['number']} {r['client']} {money(r['total_usd'])} overdue {days_overdue(r)}d, reminders {len(r.get('reminders') or [])}, next: {nxt}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("list"); s.add_argument("--status"); s.add_argument("--overdue", action="store_true"); s.add_argument("--deal"); s.set_defaults(fn=cmd_list)
    s = sub.add_parser("show"); s.add_argument("number"); s.set_defaults(fn=cmd_show)
    s = sub.add_parser("create"); s.add_argument("--deal", required=True); s.add_argument("--client", required=True); s.add_argument("--contact", required=True); s.add_argument("--offer", required=True); s.add_argument("--line", action="append", default=[]); s.add_argument("--credit", type=float, default=0); s.add_argument("--due-days", type=int, default=14); s.add_argument("--confirm", action="store_true"); s.set_defaults(fn=cmd_create)
    s = sub.add_parser("approve"); s.add_argument("number"); s.add_argument("--ask", required=True); s.add_argument("--confirm", action="store_true"); s.set_defaults(fn=cmd_approve)
    s = sub.add_parser("mark-sent"); s.add_argument("number"); s.add_argument("--via", required=True); s.add_argument("--confirm", action="store_true"); s.set_defaults(fn=cmd_mark_sent)
    s = sub.add_parser("mark-paid"); s.add_argument("number"); s.add_argument("--amount", required=True); s.add_argument("--ref", required=True); s.add_argument("--date", required=True); s.add_argument("--confirm", action="store_true"); s.set_defaults(fn=cmd_mark_paid)
    s = sub.add_parser("remind"); s.add_argument("number"); s.add_argument("--stage", required=True, choices=STAGES); s.add_argument("--ask", required=True); s.add_argument("--confirm", action="store_true"); s.set_defaults(fn=cmd_remind)
    s = sub.add_parser("void"); s.add_argument("number"); s.add_argument("--reason", required=True); s.add_argument("--confirm", action="store_true"); s.set_defaults(fn=cmd_void)
    s = sub.add_parser("note"); s.add_argument("number"); s.add_argument("--text", required=True); s.add_argument("--confirm", action="store_true"); s.set_defaults(fn=cmd_note)
    s = sub.add_parser("summary"); s.set_defaults(fn=cmd_summary)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
