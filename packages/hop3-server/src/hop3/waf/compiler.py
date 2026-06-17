# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Compile a validated ``[waf]`` policy (ADR 048) into engine-native SecLang.

The output is the per-app *access overlay* fed to the engine via a rules file
(`lewaf-proxy --rules-file`); the OWASP CRS baseline is loaded separately. SecLang
is engine-agnostic among ModSecurity-compatible engines (LeWAF, Coraza).

**Targets LeWAF >= 0.7.5** (all primitives below verified behaviorally):

- ``allow`` -> a negated-regex deny on ``REQUEST_URI`` (positive model).
- ``[[waf.gate]]`` -> a ``chain`` of (path ``@rx``) + (``REMOTE_ADDR !@ipMatch
  <network cidrs>``); reachable only from the named network.
- ``[[waf.tuning]] disable-rule-ids`` -> path-scoped ``ctl:ruleRemoveById`` (or a
  global ``SecRuleRemoveById`` directive when the entry has no ``paths``).
- ``mode`` is encoded per-rule (``deny`` vs ``pass,log``) — not via
  ``SecRuleEngine DetectionOnly`` (kept ``On`` so it controls the CRS uniformly).

Still unsupported by the engine (fails loud rather than silently no-op):

- ``[[waf.tuning]] skip-body-inspection`` — ``ctl:requestBodyAccess`` is a no-op
  in LeWAF 0.7.5 (see local-notes/lewaf bug report). Raises WafCompileError.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hop3.project.schema import WafSection

# Hop3 access-overlay rule IDs. Kept well below the OWASP CRS range (9xxxxx) so
# they never collide with the loaded baseline.
_RULE_ID_BASE = 100000


class WafCompileError(Exception):
    """A declared WAF policy can't be expressed on the target engine."""


def _anchored_alternation(patterns: list[str]) -> str:
    """Full-match regex over the patterns: ``^(?:p1|p2|...)$``.

    Patterns are validated by the schema to be compilable regexes containing no
    double quote, so they embed directly in the SecLang operator argument.
    """
    return "^(?:" + "|".join(patterns) + ")$"


def compile_policy(
    app_name: str, policy: WafSection, networks: Mapping[str, list[str]]
) -> str:
    """Compile a validated ``[waf]`` policy into a SecLang rules document.

    Args:
        app_name: owning app (for the header comment / rule provenance).
        policy: the validated :class:`WafSection`.
        networks: resolved named networks (name -> CIDRs) for gate conditions.

    Returns:
        SecLang text for ``--rules-file`` (always ends with a newline).

    Raises:
        WafCompileError: a gate references an undefined network, or a tuning entry
            uses ``skip-body-inspection`` (unsupported by the engine).
    """
    lines = [
        f"# Hop3-generated WAF access overlay for '{app_name}' (ADR 048). DO NOT EDIT.",
        # Engine stays On; `mode` is encoded per-rule because LeWAF's
        # SecRuleEngine DetectionOnly historically didn't neutralise `deny`.
        "SecRuleEngine On",
    ]
    # block -> deny (interrupt); detect -> pass,log (log-only rollout).
    action = "pass,log" if policy.mode == "detect" else "deny,status:403,log"
    rule_id = _RULE_ID_BASE

    # --- CRS tuning (rule exclusions), emitted first so removals apply early ---
    for tuning in policy.tuning or []:
        if tuning.skip_body_inspection:
            msg = (
                "[[waf.tuning]] skip-body-inspection is not supported: the WAF "
                "engine (LeWAF 0.7.5) ignores ctl:requestBodyAccess. Use "
                "disable-rule-ids, or wait for engine support (ADR 048)."
            )
            raise WafCompileError(msg)
        ids = tuning.disable_rule_ids or []
        if not ids:
            continue
        if tuning.paths:
            ctls = ",".join(f"ctl:ruleRemoveById={i}" for i in ids)
            lines.append(
                f'SecRule REQUEST_URI "@rx {_anchored_alternation(tuning.paths)}" '
                f'"id:{rule_id},phase:1,pass,nolog,{ctls}"'
            )
            rule_id += 1
        else:
            # Global (unscoped) exclusion — a directive, not a per-request ctl.
            lines += [f"SecRuleRemoveById {i}" for i in ids]

    # --- conditional gates (use case 2): chain path-match AND not-in-network ---
    for gate in policy.gate or []:
        cidrs = networks.get(gate.require)
        if not cidrs:
            msg = (
                f"[[waf.gate]] references network '{gate.require}', which is not "
                f"defined. Create it with: hop3 network add {gate.require} <cidr>"
            )
            raise WafCompileError(msg)
        starter = (
            f'SecRule REQUEST_URI "@rx {_anchored_alternation(gate.paths)}" '
            f'"id:{rule_id},phase:1,chain,{action},'
            f"msg:'hop3 gate: requires network {gate.require}'\""
        )
        child = f'    SecRule REMOTE_ADDR "!@ipMatch {",".join(cidrs)}" "t:none"'
        lines += [starter, child]
        rule_id += 1

    # --- positive model (use case 1): deny any path not in the allowlist ---
    if policy.allow:
        rule = (
            f'SecRule REQUEST_URI "!@rx {_anchored_alternation(policy.allow)}" '
            f'"id:{rule_id},phase:1,{action},'
            "msg:'hop3 allow: path not permitted'\""
        )
        lines += ["# positive model: deny any path not in the allowlist", rule]
        rule_id += 1

    return "\n".join(lines) + "\n"
