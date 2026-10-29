---
name: payments
description: Record a payment against an invoice from a bank reference and a date a person gave you, or list what is still unpaid. Use for "X paid", "record the payment", "what is unpaid", "did Cedar Point pay".
argument-hint: "[<invoice number> --amount <usd> --ref <bank reference> --date <YYYY-MM-DD>]"
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep]
user-invocable: true
metadata:
  version: "0.1"
  created: 2026-10-29
  author: keymaker
---

# Payments

Cash is a fact a person tells you with a reference and a date - or a fact Stripe tells you, when the
key is present (`--check`). You never infer a payment; you record one from one of those two sources.

## Rules

- **Identify the operator first.** A `rep` may ask what is unpaid on deals they own and nothing
  else; the finance lead and the principal record payments.
- **Never write without showing the change.** `scripts/ledger.py` prints every write and refuses
  without `--confirm`.
- **A payment needs three things:** the amount, a bank reference, the date. Missing one: ask, do not
  guess. An amount that does not match the invoice total is a person's decision (partial, over-paid,
  two invoices in one transfer): note it on the invoice and ask - never mark Paid.

## Modes

| Mode | Trigger | What you do |
|---|---|---|
| unpaid | "what is unpaid", "what is outstanding", no arguments | `python3 scripts/ledger.py list --status Sent` (a rep: filter to their deals). Show the table; say the total outstanding and how many are overdue. |
| record | "X paid", a number with `--amount --ref --date` | `ledger.py show <number>` first. Then `ledger.py mark-paid <number> --amount N --ref "<ref>" --date YYYY-MM-DD`; show the printed change; re-run with `--confirm`. Tell Delivery nothing - a paid invoice is not an event for them; the Monday review carries it. |
| check | `--check`, "anything paid on Stripe", the Monday review | `python3 scripts/stripe.py payments --since <30 days ago>` (`NO STRIPE` = say so, stop). For each paid row whose `number` matches a `Sent`/`Approved` ledger invoice: `ledger.py mark-paid <number> --amount <amount> --ref "stripe <payment_intent>" --date <paid_at>` - show, then `--confirm`. A checkout payment with no invoice number (a website purchase): tell the orchestrator in your final answer with the product, email and amount - it is a new client for Sales, not a ledger row here. |
| lookup | "did X pay", "what did we invoice X" | `ledger.py list --deal <slug>` and `show`. Answer from the rows. |

## After a write

Run `python3 scripts/ledger.py summary`. If `record_metrics` is available, record `outstanding_usd`,
`overdue_invoices`, `paid_month_usd`; otherwise print the summary at the end.

## Never

Mark an invoice Paid without a reference and a date from a person. Mark a partial payment as Paid.
Create or void an invoice from here (that is `/invoice` and the finance lead). Touch a `Draft` or
`Approved` invoice except to answer a question about it.
