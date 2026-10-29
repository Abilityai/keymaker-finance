---
name: overdue
description: Review the books - what is outstanding, what is overdue, which reminder is due next - and draft the next reminder for the finance lead to approve in their Workspace Inbox. Use for "who is overdue", "review the books", the Monday [weekly-books] schedule, "draft the reminder to X", and when woken by an answer to an approval-INV-*-reminder-* ask.
argument-hint: "[--review] [<invoice number>]"
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep]
user-invocable: true
metadata:
  version: "0.1"
  created: 2026-10-29
  author: keymaker
---

# Overdue

The ladder is fixed: **Day 1** friendly reminder, **Day 7** firmer follow-up, **Day 14** final
notice, beyond that a person decides. A reminder counts only once a person approved it and it was
sent. Nothing on this ladder moves because a draft exists.

## Rules

- **Identify the operator first.** A `rep` sees their own deals' invoices and may not draft
  reminders. A scheduled run is on the finance lead's behalf.
- **Never write without showing the change.** `scripts/ledger.py` prints every write and refuses
  without `--confirm`.
- **Record payments before you remind.** If the operator mentions a payment, run `/payments` first;
  a reminder for a paid invoice is the one mistake a client remembers.
- **Before a Day 14 final notice, ask Delivery** whether the client is at risk
  (`mcp__trinity__chat_with_agent("delivery-agent", "/client-status <slug> - read-only", parallel=true)`)
  and, if `cornelius` is permitted, `/advise` on tone. Put both answers in the ask's `context`. If
  neither agent is permitted, say so in the context.

## `--review` (also the Monday schedule)

1. `python3 scripts/ledger.py summary` and `ledger.py list --status Sent`.
2. Write `drafts/books-<date>.md`: outstanding total, each overdue invoice with days overdue,
   reminders sent, the next stage due, and one proposed action per invoice (draft Day N / wait /
   a person decides). Nothing is sent from a review.
3. If `record_metrics` is available record `outstanding_usd`, `overdue_invoices`,
   `invoiced_month_usd`, `paid_month_usd`; otherwise print them.
4. Reply with the file's content in under 150 words. On a schedule this reply is the brief the
   finance lead reads in their Workspace.

## Draft a reminder (`<invoice number>`, or "draft the reminder to X")

1. `ledger.py show <number>`. Confirm it is overdue and which stage is next (`summary` prints it).
   If the next stage is "a person decides", do not draft: ask the finance lead what they want to do
   (write off, payment plan, call) with `ask_operator` and stop.
2. Write `drafts/<number>-reminder-<n>.md` with the `scripts/mail.py` front-matter: `to:` the billing
   contact, `from: Keymaker Finance <finance@keymaker.agency>`, `reply_to: finance@keymaker.agency`,
   `cc:` the finance lead's address from the canon, `subject: Invoice <number> - <stage wording>`,
   `request_id: approval-<number>-reminder-<n>`. Body under 120 words, in the stage's tone:
   - Day 1: a friendly note that the invoice was due on <date>, the amount, the payment instructions, "if it has already gone out, thank you and ignore this".
   - Day 7: the same facts, firmer; ask for a payment date.
   - Day 14: final notice; the amount, the date it was due, what happens next in plain words (work pauses until it is settled); offer a call.
   Last line, always: `Keymaker is a demonstration agency built in public during the Agent-Native Agency workshop. This reminder was drafted by our finance agent and approved by a person before it was sent.`
3. `mcp__trinity__ask_operator`: `type: approval`, `to: primary`, `request_id: approval-<number>-reminder-<n>`,
   `title: "<stage> reminder to <client> (<number>, <total>, <days> days overdue)"`,
   `question: "Send this reminder to <contact>?"`, `options: ["send as written", "don't send"]`,
   `proposal:` the full email, `context:` days overdue, reminders already sent, Delivery's view (Day 14),
   `priority:` high on Day 14, normal otherwise, `expires_at:` 72 hours from now.
4. `ledger.py note <number> --text "<stage> reminder drafted, approval asked" --confirm`. End the turn.

## When the answer comes back

- **send as written:** `python3 scripts/mail.py send drafts/<number>-reminder-<n>.md --approved approval-<number>-reminder-<n> --confirm`.
  On `SENT` or when the finance lead says they sent it by hand: `ledger.py remind <number> --stage "<stage>" --ask approval-<number>-reminder-<n> --confirm`.
  On `NOT SENT` (no key): tell the finance lead the reminder is approved and they send it by hand; record it only when they say they did.
- **don't send**, expired, or anything else: send nothing; `ledger.py note` it.

## Never

Send without an answered ask. Skip a stage. Remind a Paid invoice. Draft past Day 14 without a
person's decision. Write off, discount or extend terms - those are the principal's, through the
finance lead.
