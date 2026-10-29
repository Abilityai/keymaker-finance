---
name: invoice
description: Turn a won deal into an invoice document and ask the finance lead to approve it in their Workspace Inbox; on their answer send exactly the approved document or nothing. Use for "X signed, invoice the Pilot", "/invoice <slug>" from the orchestrator, and when woken by an answer to an approval-INV-* ask.
argument-hint: "<deal slug> [--offer <name>] [--amount <usd>] [--credit <usd>]"
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep]
user-invocable: true
metadata:
  version: "0.1"
  created: 2026-10-29
  author: keymaker
---

# Invoice

A won deal becomes an invoice here, and nothing else does. The orchestrator calls `/invoice
thorne-ridley-healthcare`; a person may say "they signed, invoice the Pilot". Either way the facts
come from files and the approval comes from a person.

## Rules

- **Identify the operator first** (`operators.yaml`; the canon's `ORGANISATION.md` wins when `canon/`
  exists). A `rep` cannot invoice. A call from the `orchestrator` is on the finance lead's behalf.
- **Never write without showing the change.** `scripts/ledger.py` prints every write and refuses
  without `--confirm`.
- **Every number traces.** The offer and its list price: `canon/domains/pricing/pricing.md`
  (`pricing.md` here is a sample). The deal, the client, the billing contact and any approved credit:
  the handoff Sales wrote. Nothing else is a source.

## Steps

1. **Get the handoff.** Look for `<slug>-handoff.md` in the sales desk's shared folder (`ls` the
   mounted shared folders; the path is printed in your execution context). If it is not mounted, ask
   `sales` once, read-only:
   `mcp__trinity__chat_with_agent("sales", "paste drafts/<slug>-handoff.md verbatim; no writes", parallel=true)`.
   If `sales` is not in your permitted agents or has no handoff: ask the operator for the facts
   (client, billing contact, offer, approved credit) and say the invoice carries `[NEEDS-HANDOFF]`
   until a handoff exists. **Never invoice a deal that is not Won** - if the handoff is missing
   because the deal is still open, say so and stop.
2. **Check the amount.** The offer's list price from the price list; the credit from the handoff
   (a discount is an invoice credit line, at most the `sales-rep` limit in
   `canon/domains/approvals/approvals.yaml` unless the handoff names the principal's approval). A Build
   invoices 50% on signature unless the handoff says otherwise. If the handoff's price and the list
   disagree, or an `--amount` was passed that matches neither, write `[NEEDS-AMOUNT]`, tell the
   operator exactly which two numbers disagree, and stop.
3. **Check the ledger.** `python3 scripts/ledger.py list --deal <slug>` - an open invoice for the same
   offer means you add a note, never a second invoice.
4. **Create the draft.**
   `python3 scripts/ledger.py create --deal <slug> --client "<client>" --contact "<Name <email>>" --offer <offer> --line "<description>=<amount>" [--credit <usd>] [--due-days 14]`
   Show the printed change, then re-run with `--confirm`. The invoice document is now
   `invoices/INV-KM-NNNN.md`.
5. **Draft the covering email** to `drafts/INV-KM-NNNN-send.md` with the front-matter
   `scripts/mail.py` documents: `to:` the billing contact, `from: Keymaker Finance <finance@keymaker.agency>`,
   `reply_to: finance@keymaker.agency`, `cc:` the finance lead's address from the canon,
   `subject: Invoice INV-KM-NNNN from Keymaker - <offer>`, `request_id: approval-INV-KM-NNNN-send`.
   Body, under 120 words: thank them, one line on what was sold, the total and the due date, the
   payment instructions, the full invoice document pasted below a `---` line. Last line, always:
   `Keymaker is a demonstration agency built in public during the Agent-Native Agency workshop. This invoice was drafted by our finance agent and approved by a person before it was sent.`
6. **Ask the finance lead.** `mcp__trinity__ask_operator` with `type: approval`, `to: primary`,
   `request_id: approval-INV-KM-NNNN-send`, `title: "Invoice <client> <total> (INV-KM-NNNN)"`,
   `question: "Send this invoice to <contact> at <client>?"`, `options: ["send as written", "don't send"]`,
   `proposal:` the full email (to / cc / subject / body, exactly), `context:` the deal and how the
   amount was derived (list price, credit, handoff line), `priority: high`, `expires_at:` 72 hours
   from now (canon `approvals.yaml`).
7. **Record and end the turn.** `ledger.py note INV-KM-NNNN --text "Approval asked (approval-INV-KM-NNNN-send)" --confirm`.
   Tell the caller: the invoice number, the total, and that it waits for the finance lead. Do not
   wait for the answer.

## When the answer comes back

You are woken with the answer (or read it with `get_my_ask approval-INV-KM-NNNN-send`).
- **send as written:** `python3 scripts/ledger.py approve INV-KM-NNNN --ask approval-INV-KM-NNNN-send --confirm`, then
  `python3 scripts/mail.py send drafts/INV-KM-NNNN-send.md --approved approval-INV-KM-NNNN-send --confirm`.
  Exactly the approved file - if you would change one word, you need a new ask. On `SENT`:
  `ledger.py mark-sent INV-KM-NNNN --via "resend <id>" --confirm`. On `NOT SENT` (no key): leave it
  Approved, tell the finance lead the document is approved and they send it by hand; when they say
  they did, `mark-sent --via "by hand"`.
- **don't send**, expired, or anything else: send nothing. `ledger.py note` it. Tell the caller.

## Never

Send without an answered ask. Edit an approved document and send it. Invoice a deal that is not
Won. Put an amount on an invoice that is not on the price list or the handoff. Void a Paid invoice.
