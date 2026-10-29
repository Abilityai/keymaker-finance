#!/usr/bin/env python3
"""Keymaker Finance <-> Stripe. The one way this desk talks to Stripe. Stdlib only.

    python3 scripts/stripe.py whoami
    python3 scripts/stripe.py invoice create <number> --email <to> --name "<client>" \
            --line "description=amount_usd" [--line ...] [--due-days 14] [--confirm]
    python3 scripts/stripe.py invoice status <stripe_invoice_id|number>
    python3 scripts/stripe.py invoice void <stripe_invoice_id> --confirm
    python3 scripts/stripe.py payments [--since YYYY-MM-DD]       # paid invoices + checkout sessions, newest first
    python3 scripts/stripe.py link create --name "<product>" --amount <usd> [--confirm]   # a Payment Link for the website

Needs STRIPE_API_KEY (a restricted key: Customers, Products, Prices, Invoices, Payment Links,
Checkout Sessions write; Charges, PaymentIntents read). Read from the environment or ~/.env.
Every write prints what it is about to do and refuses without --confirm.

`invoice create` makes a Stripe invoice that is FINALIZED but NOT emailed by Stripe
(collection_method=send_invoice, auto_advance=false): the hosted payment page URL comes back and
goes into the covering email a person approves. Stripe never contacts the client on its own.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.stripe.com/v1"


def key():
    k = os.environ.get("STRIPE_API_KEY")
    if not k:
        f = Path.home() / ".env"
        if f.exists():
            for line in f.read_text().splitlines():
                if line.startswith("STRIPE_API_KEY="):
                    k = line.split("=", 1)[1].strip().strip('"')
    if not k:
        sys.exit("NO STRIPE: STRIPE_API_KEY is not on this agent. The invoice is a file; the finance lead collects by bank transfer.")
    return k


def call(method, path, data=None, idem=None):
    body = urllib.parse.urlencode(data, doseq=True).encode() if data else None
    req = urllib.request.Request(API + path, data=body, method=method,
                                 headers={"Authorization": "Bearer " + key(),
                                          "Content-Type": "application/x-www-form-urlencoded",
                                          "User-Agent": "keymaker-finance/0.2",
                                          **({"Idempotency-Key": idem} if idem else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        err = json.loads(e.read() or b"{}").get("error", {})
        sys.exit(f"STRIPE {e.code}: {err.get('message', 'unknown error')} ({err.get('code', '')})")


def gate(desc, confirm):
    print("CHANGE: " + desc)
    if not confirm:
        sys.exit("refused: re-run with --confirm")


def money(cents):
    return f"${cents/100:,.2f}"


# ---------------------------------------------------------------------------------- commands
def cmd_whoami(a):
    acct = call("GET", "/account")
    bal = call("GET", "/balance")
    avail = sum(b["amount"] for b in bal.get("available", []) if b["currency"] == "usd")
    print(f"account: {acct.get('id')} · {acct.get('settings', {}).get('dashboard', {}).get('display_name') or acct.get('business_profile', {}).get('name')} · livemode={acct.get('charges_enabled')}")
    print(f"available USD balance: {money(avail)}")


def find_customer(email, name):
    found = call("GET", "/customers/search?" + urllib.parse.urlencode({"query": f"email:'{email}'", "limit": 1}))
    if found.get("data"):
        return found["data"][0]
    return None


def cmd_invoice_create(a):
    lines = []
    for item in a.line:
        desc, amt = item.rsplit("=", 1)
        lines.append((desc.strip(), int(round(float(amt) * 100))))
    if not lines:
        sys.exit("at least one --line")
    total = sum(c for _, c in lines)
    gate(f"Stripe: customer {a.name} <{a.email}>; invoice {a.number} with {len(lines)} line(s), total {money(total)}, due in {a.due_days} days, finalized, NOT emailed by Stripe", a.confirm)
    cust = find_customer(a.email, a.name) or call("POST", "/customers", {"email": a.email, "name": a.name, "metadata[keymaker]": "1"}, idem=f"cust-{a.email}")
    inv = call("POST", "/invoices", {
        "customer": cust["id"], "collection_method": "send_invoice", "days_until_due": a.due_days,
        "auto_advance": "false", "currency": "usd",
        "metadata[keymaker_number]": a.number, "description": f"Keymaker invoice {a.number}",
        "footer": "Keymaker is a demonstration agency built in public during the Agent-Native Agency workshop.",
    }, idem=f"inv-{a.number}")
    for i, (desc, cents) in enumerate(lines):
        call("POST", "/invoiceitems", {"customer": cust["id"], "invoice": inv["id"], "currency": "usd",
                                       "amount": cents, "description": desc}, idem=f"item-{a.number}-{i}")
    fin = call("POST", f"/invoices/{inv['id']}/finalize", {"auto_advance": "false"}, idem=f"fin-{a.number}")
    print(json.dumps({"stripe_invoice": fin["id"], "number": a.number, "total": money(fin["amount_due"]),
                      "due": time.strftime("%Y-%m-%d", time.gmtime(fin["due_date"])) if fin.get("due_date") else None,
                      "hosted_invoice_url": fin.get("hosted_invoice_url"), "invoice_pdf": fin.get("invoice_pdf"),
                      "status": fin["status"]}, indent=2))


def resolve_invoice(ref):
    if ref.startswith("in_"):
        return call("GET", f"/invoices/{ref}")
    found = call("GET", "/invoices/search?" + urllib.parse.urlencode({"query": f"metadata['keymaker_number']:'{ref}'", "limit": 1}))
    if not found.get("data"):
        sys.exit(f"no Stripe invoice carries keymaker_number {ref}")
    return found["data"][0]


def cmd_invoice_status(a):
    inv = resolve_invoice(a.ref)
    paid_at = None
    if inv.get("status_transitions", {}).get("paid_at"):
        paid_at = time.strftime("%Y-%m-%d", time.gmtime(inv["status_transitions"]["paid_at"]))
    print(json.dumps({"stripe_invoice": inv["id"], "number": inv.get("metadata", {}).get("keymaker_number"),
                      "status": inv["status"], "amount_due": money(inv["amount_due"]), "amount_paid": money(inv["amount_paid"]),
                      "paid_at": paid_at, "payment_intent": inv.get("payment_intent"),
                      "hosted_invoice_url": inv.get("hosted_invoice_url")}, indent=2))


def cmd_invoice_void(a):
    inv = resolve_invoice(a.ref)
    gate(f"Stripe: void invoice {inv['id']} ({inv.get('metadata', {}).get('keymaker_number')}, {money(inv['amount_due'])}, status {inv['status']})", a.confirm)
    out = call("POST", f"/invoices/{inv['id']}/void")
    print(out["status"])


def cmd_payments(a):
    since = int(time.mktime(time.strptime(a.since, "%Y-%m-%d"))) if a.since else int(time.time()) - 30 * 86400
    rows = []
    invs = call("GET", "/invoices?" + urllib.parse.urlencode({"status": "paid", "limit": 50, "created[gte]": since}))
    for inv in invs.get("data", []):
        rows.append({"kind": "invoice", "id": inv["id"], "number": inv.get("metadata", {}).get("keymaker_number"),
                     "email": inv.get("customer_email"), "amount": money(inv["amount_paid"]),
                     "paid_at": time.strftime("%Y-%m-%d", time.gmtime(inv["status_transitions"]["paid_at"])),
                     "ref": inv.get("payment_intent") or inv.get("charge")})
    sess = call("GET", "/checkout/sessions?" + urllib.parse.urlencode({"limit": 50, "created[gte]": since}))
    for s in sess.get("data", []):
        if s.get("payment_status") == "paid":
            rows.append({"kind": "checkout", "id": s["id"], "number": None,
                         "email": (s.get("customer_details") or {}).get("email"), "amount": money(s["amount_total"]),
                         "paid_at": time.strftime("%Y-%m-%d", time.gmtime(s["created"])), "ref": s.get("payment_intent"),
                         "product": (s.get("metadata") or {}).get("product")})
    rows.sort(key=lambda r: r["paid_at"], reverse=True)
    print(json.dumps(rows, indent=2) if rows else "no payments in the window")


def cmd_link_create(a):
    cents = int(round(a.amount * 100))
    gate(f"Stripe: product '{a.name}', one-time price {money(cents)}, Payment Link", a.confirm)
    prod = call("POST", "/products", {"name": a.name, "metadata[keymaker]": "1"}, idem=f"prod-{a.name}")
    price = call("POST", "/prices", {"product": prod["id"], "unit_amount": cents, "currency": "usd"}, idem=f"price-{a.name}-{cents}")
    link = call("POST", "/payment_links", {"line_items[0][price]": price["id"], "line_items[0][quantity]": 1,
                                           "metadata[product]": a.name,
                                           "after_completion[type]": "hosted_confirmation",
                                           "after_completion[hosted_confirmation][custom_message]": "Thank you. Keymaker's finance desk records the payment and our sales desk opens your engagement; you will hear from a person within one business day."},
                idem=f"link-{a.name}-{cents}")
    print(json.dumps({"payment_link": link["url"], "id": link["id"], "price": price["id"], "product": prod["id"]}, indent=2))


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("whoami").set_defaults(fn=cmd_whoami)
    inv = sub.add_parser("invoice").add_subparsers(dest="sub", required=True)
    s = inv.add_parser("create"); s.add_argument("number"); s.add_argument("--email", required=True); s.add_argument("--name", required=True); s.add_argument("--line", action="append", default=[]); s.add_argument("--due-days", type=int, default=14); s.add_argument("--confirm", action="store_true"); s.set_defaults(fn=cmd_invoice_create)
    s = inv.add_parser("status"); s.add_argument("ref"); s.set_defaults(fn=cmd_invoice_status)
    s = inv.add_parser("void"); s.add_argument("ref"); s.add_argument("--confirm", action="store_true"); s.set_defaults(fn=cmd_invoice_void)
    s = sub.add_parser("payments"); s.add_argument("--since"); s.set_defaults(fn=cmd_payments)
    ln = sub.add_parser("link").add_subparsers(dest="sub", required=True)
    s = ln.add_parser("create"); s.add_argument("--name", required=True); s.add_argument("--amount", type=float, required=True); s.add_argument("--confirm", action="store_true"); s.set_defaults(fn=cmd_link_create)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
