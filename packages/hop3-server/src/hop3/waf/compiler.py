# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Compile a validated ``[waf]`` policy (ADR 050) into engine-native SecLang.

The output is the per-app *access overlay* fed to the engine via a rules file
(`lewaf-proxy --rules-file`); the OWASP CRS baseline is loaded separately. SecLang
is engine-agnostic among ModSecurity-compatible engines (LeWAF, Coraza).

**Targets LeWAF >= 0.7.5** (all primitives below verified behaviorally):

- Path matching uses ``REQUEST_FILENAME`` (the path, no query string) under
  ``t:none,t:urlDecodeUni,t:normalizePath`` so ``/a/../admin`` and ``%2e%2e``
  encodings can't slip past a pattern (Security invariant 2). ``REQUEST_URI``
  would carry the query string and defeat the full-match anchoring.
- ``allow`` -> a negated-regex deny on the normalized path (positive model).
- ``[[waf.gate]]`` -> a ``chain`` of (path ``@rx``) + (``REMOTE_ADDR !@ipMatch
  <network cidrs>``); reachable only from the named network.
- ``[[waf.tuning]] disable-rule-ids`` -> path-scoped ``ctl:ruleRemoveById`` (or a
  global ``SecRuleRemoveById`` directive when the entry has no ``paths``).
- ``[[waf.tuning]] skip-body-inspection`` -> ``ctl:requestBodyAccess=Off`` (path-
  scoped, or a global ``SecAction`` ctl) — for WebDAV/large-upload clients that
  aren't browsers (e.g. Nextcloud sync).
- ``mode`` is encoded per-rule (``deny`` vs ``pass,log``) — not via
  ``SecRuleEngine DetectionOnly`` (kept ``On`` so it controls the CRS uniformly).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from hop3.project.schema import WafSection

# Hop3 access-overlay rule IDs. Kept well below the OWASP CRS range (9xxxxx) so
# they never collide with the loaded baseline.
_RULE_ID_BASE = 100000

# Single rule id for the L7 ban denylist (distinct from CRS 9xxxxx and the
# overlay 1xxxxx range).
_BAN_RULE_ID = 99000

# Path-matching variable + canonicalization for all access rules. REQUEST_FILENAME
# is the path only (no query string); the transforms resolve dot-segments and one
# layer of percent-encoding so the matched form equals what the backend routes on
# (Security invariant 2). `t:none` clears any inherited default transformations.
_PATH_VAR = "REQUEST_FILENAME"
_PATH_TRANSFORMS = "t:none,t:urlDecodeUni,t:normalizePath"

# CRS preamble: a setup SecAction (must precede REQUEST-901) + anomaly-mode
# default actions, so scoring rules accumulate and only the threshold rule
# (949110) blocks. Mirrors LeWAF's own conformance harness (tests/ftw_tests/
# _crs_stack.py) — the recipe verified to pass clean traffic and block the OWASP
# attack classes via rule 949110. `crs_setup_version` is required or 901001
# denies every request ("deployed without configuration" guard).
_CRS_SETUP_VERSION = 400
# Methods a normal HTTP app uses; without this, CRS 911100 denies every request.
_CRS_ALLOWED_METHODS = "GET HEAD POST OPTIONS PUT PATCH DELETE"


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
    """Compile a ``[waf]`` policy into the per-app *access overlay* (no CRS).

    The overlay is the allow/gate/tuning rules only; the OWASP CRS baseline is
    loaded separately. Use :func:`compile_rules_file` for the full document the
    proxy consumes. Kept as a focused, filesystem-free unit for tests.

    Args:
        app_name: owning app (for the header comment / rule provenance).
        policy: the validated :class:`WafSection`.
        networks: resolved named networks (name -> CIDRs) for gate conditions.

    Returns:
        SecLang text for the access overlay (always ends with a newline).

    Raises:
        WafCompileError: a gate references an undefined network, or a tuning entry
            uses ``skip-body-inspection`` (unsupported by the engine).
    """
    lines = [
        f"# Hop3-generated WAF access overlay for '{app_name}' (ADR 050). DO NOT EDIT.",
        # Engine stays On; `mode` is encoded per-rule because LeWAF's
        # SecRuleEngine DetectionOnly historically didn't neutralise `deny`.
        "SecRuleEngine On",
        *_overlay_lines(policy, networks),
    ]
    return "\n".join(lines) + "\n"


def compile_rules_file(
    app_name: str,
    policy: WafSection,
    networks: Mapping[str, list[str]],
    crs_dir: Path | None,
) -> str:
    """Compile the full ``--rules-file`` the proxy loads: CRS baseline + overlay.

    ``lewaf-proxy`` takes a single rules file, so the OWASP CRS baseline and the
    per-app access overlay are concatenated into one document. Order matters: the
    CRS setup SecAction precedes REQUEST-901, the REQUEST-9xx files load
    901-first/949-last (so the threshold rule sees every score), and the overlay
    (incl. ``SecRuleRemoveById`` tuning) comes last so its removals target
    already-loaded rules.

    Args:
        app_name: owning app (header / provenance).
        policy: the validated :class:`WafSection`.
        networks: resolved named networks for gate conditions.
        crs_dir: directory of vendored OWASP CRS ``REQUEST-*.conf`` files.

    Raises:
        WafCompileError: ``ruleset = "owasp-crs"`` but the CRS bundle is missing,
            plus the :func:`compile_policy` failure modes.
    """
    lines = [
        f"# Hop3-generated WAF rules for '{app_name}' (ADR 050). DO NOT EDIT.",
        "SecRuleEngine On",
    ]
    if policy.ruleset == "owasp-crs":
        lines += _crs_baseline_lines(crs_dir, policy.paranoia)
    lines += _overlay_lines(policy, networks)
    return "\n".join(lines) + "\n"


def compile_bans(banned: list[str]) -> str:
    """Compile the active L7 ban denylist into SecLang (ADR 050 §4).

    A single ``@ipMatch`` deny rule over all banned sources, written to a
    separate file the ban scorer rewrites and loaded *before* the CRS/overlay so
    a banned source is rejected first (and cheaply). An empty list yields a
    header-only file (no rule), so the proxy's ``rule_files`` reference stays
    valid with no bans in effect.

    Args:
        banned: banned source IPs/CIDRs (validated as real addresses upstream).
    """
    header = (
        "# Hop3-generated WAF ban denylist (ADR 050 §4). Managed by the ban "
        "scorer — DO NOT EDIT."
    )
    if not banned:
        return header + "\n"
    rule = (
        f'SecRule REMOTE_ADDR "@ipMatch {",".join(banned)}" '
        f"\"id:{_BAN_RULE_ID},phase:1,deny,status:403,log,msg:'hop3 ban'\""
    )
    return f"{header}\n{rule}\n"


def _overlay_lines(policy: WafSection, networks: Mapping[str, list[str]]) -> list[str]:
    """The access-overlay rules: tuning exclusions, gates, positive allowlist."""
    # block -> deny (interrupt); detect -> pass,log (log-only rollout).
    action = "pass,log" if policy.mode == "detect" else "deny,status:403,log"
    rule_id = _RULE_ID_BASE
    lines: list[str] = []

    # --- CRS tuning (exclusions), emitted first so removals apply early ---
    for tuning in policy.tuning or []:
        ctls = [f"ctl:ruleRemoveById={i}" for i in (tuning.disable_rule_ids or [])]
        if tuning.skip_body_inspection:
            ctls.append("ctl:requestBodyAccess=Off")
        if not ctls:
            continue
        if tuning.paths:
            # Path-scoped: one phase-1 rule applies all ctls when the path matches.
            lines.append(
                f'SecRule {_PATH_VAR} "@rx {_anchored_alternation(tuning.paths)}" '
                f'"id:{rule_id},phase:1,pass,nolog,{_PATH_TRANSFORMS},{",".join(ctls)}"'
            )
            rule_id += 1
        else:
            # Global: rule removals are directives; a global body-skip is an
            # unconditional phase-1 ctl SecAction.
            lines += [f"SecRuleRemoveById {i}" for i in (tuning.disable_rule_ids or [])]
            if tuning.skip_body_inspection:
                lines.append(
                    f'SecAction "id:{rule_id},phase:1,pass,nolog,'
                    'ctl:requestBodyAccess=Off"'
                )
                rule_id += 1

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
            f'SecRule {_PATH_VAR} "@rx {_anchored_alternation(gate.paths)}" '
            f'"id:{rule_id},phase:1,chain,{action},{_PATH_TRANSFORMS},'
            f"msg:'hop3 gate: requires network {gate.require}'\""
        )
        child = f'    SecRule REMOTE_ADDR "!@ipMatch {",".join(cidrs)}" "t:none"'
        lines += [starter, child]
        rule_id += 1

    # --- positive model (use case 1): deny any path not in the allowlist ---
    if policy.allow:
        rule = (
            f'SecRule {_PATH_VAR} "!@rx {_anchored_alternation(policy.allow)}" '
            f'"id:{rule_id},phase:1,{action},{_PATH_TRANSFORMS},'
            "msg:'hop3 allow: path not permitted'\""
        )
        lines += ["# positive model: deny any path not in the allowlist", rule]
        rule_id += 1

    return lines


def _crs_request_files(crs_dir: Path) -> list[Path]:
    """Every ``REQUEST-*.conf``, ordered 901-first / 949-last, rest between.

    901 seeds anomaly defaults; 949 sums the score and applies the threshold —
    so it must run after every scoring rule (LeWAF ``_crs_stack`` ordering).
    """
    files = sorted(p for p in crs_dir.glob("REQUEST-*.conf"))
    first = [p for p in files if p.name.startswith("REQUEST-901")]
    last = [p for p in files if p.name.startswith("REQUEST-949")]
    middle = [p for p in files if p not in first and p not in last]
    return first + middle + last


def _crs_baseline_lines(crs_dir: Path | None, paranoia: int) -> list[str]:
    """The CRS setup preamble + ordered ``Include`` directives for the bundle."""
    if crs_dir is None or not crs_dir.is_dir():
        msg = (
            "ruleset = 'owasp-crs' but the CRS bundle was not found"
            f"{f' at {crs_dir}' if crs_dir else ''}. This is a packaging bug — "
            "the vendored OWASP CRS rules ship under hop3/waf/crs/."
        )
        raise WafCompileError(msg)
    request_files = _crs_request_files(crs_dir)
    if not request_files:
        msg = f"CRS bundle at {crs_dir} contains no REQUEST-*.conf rule files."
        raise WafCompileError(msg)
    setvars = ",".join([
        "pass",
        "nolog",
        f"setvar:tx.crs_setup_version={_CRS_SETUP_VERSION}",
        f"setvar:tx.detection_paranoia_level={paranoia}",
        f"setvar:tx.blocking_paranoia_level={paranoia}",
        f"setvar:tx.allowed_methods={_CRS_ALLOWED_METHODS}",
    ])
    lines = [
        "# --- OWASP CRS baseline (anomaly-scoring mode) ---",
        f'SecAction "id:900000,phase:1,{setvars}"',
        'SecDefaultAction "phase:1,pass,log"',
        'SecDefaultAction "phase:2,pass,log"',
    ]
    lines += [f"Include {p}" for p in request_files]
    return lines
