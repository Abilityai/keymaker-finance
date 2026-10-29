# Keymaker Finance

The finance desk of **Keymaker**, an agency that sets up automation on Trinity for other
companies. One of the Keymaker agency starter templates, built in public during the
[Agent-Native Agency workshop](https://www.ability.ai/trinity/workshops/agent-native-agency-workshop).

It turns a won deal into an invoice, records payments against bank references, chases what is
overdue on a fixed ladder - and nothing reaches a client until the finance lead approves that
exact document in their Workspace Inbox.

## Install

On any Trinity instance: **Library → Agents → Keymaker Finance → Create**. No credentials needed.

Or from a manifest / the API: `template: github:Abilityai/keymaker-finance`.

## What it runs on

| Credentials | What changes |
|---|---|
| none (default) | invoices and reminders are files; the finance lead sends an approved one by hand and records bank transfers |
| `STRIPE_API_KEY` | `scripts/stripe.py` puts a real Stripe payment page on every invoice (finalized, never emailed by Stripe) and `/payments --check` reads what was paid |
| `RESEND_API_KEY` | `scripts/mail.py` sends an approved document from your agency domain - and only an approved one |

`scripts/ledger.py` is the only path to the books. Every write prints the change and needs
`--confirm`. There is no accounting-system adapter in this public cut; the ledger is
`ledger/invoices.yaml`.

## Playbooks

- `/invoice <deal slug>` - invoice a won deal; the approval goes to the finance lead's Inbox
- `/payments` - record a payment, or list what is unpaid
- `/overdue` - review the books and draft the next reminder (also the Monday schedule)

## The canon

When the agency has a canon (see `Abilityai/keymaker-canon`), `.trinity/setup.sh` clones it into
`canon/` on every container start and the desk reads `canon/domains/org-context/ORGANISATION.md`
(who is the finance lead), `canon/domains/approvals/approvals.yaml` (what they decide alone) and
`canon/domains/pricing/pricing.md` (the price list) instead of the sample copies here. Change
`CANON_REPO` in that script to point at yours.

## Make it yours

1. `operators.yaml` - who may operate it and in which role
2. `pricing.md` - your offers (or let the canon supply them)
3. `ledger/payment_instructions.md` - your bank details, once
4. `ledger/invoices.yaml` - replace the sample invoices

## Licence

Apache 2.0.
