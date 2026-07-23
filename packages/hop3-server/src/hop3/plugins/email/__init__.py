# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Email (SMTP relay) addon for Hop3 — EXPERIMENTAL.

Hop3 never runs a mail server. This addon holds the operator's existing SMTP
submission credentials (any provider — Resend, SES, Postmark, Brevo, a corporate
relay, …) and injects them into attached apps under every common env-var spelling
so a stock Django / Flask / Node app can send mail with no code changes.

The surface is experimental and may change — see
``notes/ngi-2024/release-plan-0.7.md``. It is transport only: outbound
transactional email, never inbound; deliverability (SPF/DKIM/DMARC on the
From-domain) is the operator's job at their provider.
"""
