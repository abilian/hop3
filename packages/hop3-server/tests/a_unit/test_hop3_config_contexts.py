# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the [contexts] section: schema validation and Hop3Config getters.

Covers ADR 042 Step 1 — pure-data parsing of project-level deploy contexts.
The runtime resolution chain (which context is "current", how it surfaces
as a server / app / domains tuple) is wired in later steps and is out of
scope here.
"""

from __future__ import annotations

import pytest

from hop3.project.hop3_config import (
    Hop3Config,
    ResolvedContext,
    UnknownContextError,
)
from hop3.project.schema import Hop3TomlValidationError, validate_hop3_toml

# ---- Positive parsing ------------------------------------------------------


def test_minimal_context_parses():
    """A context with only the required `server` field is valid."""
    cfg = Hop3Config.from_str(
        """
[contexts.dev]
server = "dev"
"""
    )
    assert cfg.context_names == ["dev"]
    assert cfg.get_context("dev") == {"server": "dev"}


def test_full_context_parses():
    """A context with all optional fields populated parses cleanly.

    The context's ``app`` field is deliberately distinct from
    ``[metadata].id`` — otherwise a buggy implementation that returned
    metadata.id instead of the context's app would silently pass.
    """
    cfg = Hop3Config.from_str(
        """
[metadata]
id = "myapp"

[contexts.prod]
server = "prod"
app = "myapp-prod"
domains = ["myapp.example.com", "www.myapp.example.com"]

[contexts.prod.env]
DEBUG = "false"
LOG_LEVEL = "warning"
"""
    )
    ctx = cfg.get_context("prod")
    assert ctx is not None
    assert ctx["server"] == "prod"
    assert ctx["app"] == "myapp-prod"  # distinct from metadata.id
    assert ctx["domains"] == ["myapp.example.com", "www.myapp.example.com"]
    assert ctx["env"] == {"DEBUG": "false", "LOG_LEVEL": "warning"}


def test_multiple_contexts_parse():
    """The dev / staging / prod canonical layout from ADR 042 parses."""
    cfg = Hop3Config.from_str(
        """
[metadata]
id = "myapp"

[contexts.dev]
server = "dev"
app = "myapp-dev"
domains = ["dev.myapp.example.com"]

[contexts.staging]
server = "dev"
app = "myapp-staging"

[contexts.prod]
server = "prod"
app = "myapp"
domains = ["myapp.example.com"]
"""
    )
    # Declaration order is preserved (insertion order from tomllib).
    assert cfg.context_names == ["dev", "staging", "prod"]
    assert cfg.get_context("dev")["app"] == "myapp-dev"
    assert cfg.get_context("staging")["server"] == "dev"
    assert cfg.get_context("prod")["domains"] == ["myapp.example.com"]


def test_no_contexts_section_returns_empty():
    """An app with no [contexts] declared yields empty accessors."""
    cfg = Hop3Config.from_str('[metadata]\nid = "x"')
    assert cfg.contexts == {}
    assert cfg.context_names == []
    assert cfg.get_context("anything") is None


def test_context_with_empty_domains_list():
    """`domains = []` is valid schema-wise (mirrors top-level [domains])."""
    validate_hop3_toml({"contexts": {"dev": {"server": "dev", "domains": []}}})


def test_context_names_with_dashes_and_underscores():
    """Identifier-style context names (with - and _) are accepted."""
    validate_hop3_toml({
        "contexts": {
            "pre-prod": {"server": "s"},
            "qual_2": {"server": "s"},
            "dev1": {"server": "s"},
        }
    })


# ---- Negative parsing ------------------------------------------------------


def test_context_without_server_rejected():
    """`server` is the only required field; omitting it must fail."""
    with pytest.raises(Hop3TomlValidationError) as exc:
        validate_hop3_toml({"contexts": {"dev": {"app": "myapp"}}})
    assert "server" in str(exc.value).lower()


def test_empty_server_rejected():
    """A blank/whitespace `server` value fails validation."""
    with pytest.raises(Hop3TomlValidationError) as exc:
        validate_hop3_toml({"contexts": {"dev": {"server": "   "}}})
    assert "server" in str(exc.value).lower()


def test_unknown_field_in_context_rejected():
    """Extra fields per ConfigDict(extra='forbid') — typo catcher."""
    with pytest.raises(Hop3TomlValidationError) as exc:
        validate_hop3_toml({
            "contexts": {"dev": {"server": "dev", "sevrer": "typo-bait"}}
        })
    msg = str(exc.value)
    assert "sevrer" in msg


def test_invalid_context_name_with_space_rejected():
    """Context names containing spaces won't survive the CLI surface."""
    with pytest.raises(Hop3TomlValidationError) as exc:
        validate_hop3_toml({"contexts": {"has space": {"server": "dev"}}})
    assert "has space" in str(exc.value)


def test_invalid_context_name_leading_digit_rejected():
    """Names must start with a letter — same rule as most CLI identifiers."""
    with pytest.raises(Hop3TomlValidationError) as exc:
        validate_hop3_toml({"contexts": {"2prod": {"server": "dev"}}})
    assert "2prod" in str(exc.value)


def test_invalid_context_name_special_char_rejected():
    """Slashes, dots, colons would collide with CLI parsing — reject."""
    with pytest.raises(Hop3TomlValidationError) as exc:
        validate_hop3_toml({"contexts": {"prod/eu": {"server": "dev"}}})
    assert "prod/eu" in str(exc.value)


def test_catch_all_alone_ok_in_context():
    """`domains = ["_"]` alone is valid (mirrors top-level [domains])."""
    validate_hop3_toml({"contexts": {"dev": {"server": "dev", "domains": ["_"]}}})


def test_catch_all_mixed_in_context_rejected():
    """The "_" + named-host mix is rejected at the context level too."""
    with pytest.raises(Hop3TomlValidationError) as exc:
        validate_hop3_toml({
            "contexts": {"dev": {"server": "dev", "domains": ["_", "example.com"]}}
        })
    assert "catch-all" in str(exc.value).lower()


# ---- Cross-section behavior -----------------------------------------------


def test_contexts_alongside_other_sections():
    """`[contexts]` coexists with [domains], [env], [build] without conflict."""
    cfg = Hop3Config.from_str(
        """
[metadata]
id = "myapp"

[build]
builder = "local"

[env]
DEBUG = "true"

[domains]
list = ["fallback.example.com"]

[contexts.dev]
server = "dev"
app = "myapp-dev"
"""
    )
    assert cfg.app_id == "myapp"
    assert cfg.domains == ["fallback.example.com"]
    assert cfg.context_names == ["dev"]
    assert cfg.get_context("dev")["app"] == "myapp-dev"


def test_legacy_app_with_no_contexts_still_validates():
    """Existing apps without [contexts] must keep parsing — back-compat."""
    cfg = Hop3Config.from_str(
        """
[metadata]
id = "legacy"

[build]
builder = "local"

[run]
start = "python app.py"
"""
    )
    assert cfg.contexts == {}
    assert cfg.context_names == []


# ---- Hop3Config defensive behavior ----------------------------------------


def test_contexts_property_filters_non_dict_values():
    """If `validate=False`, the getter must still return only dict entries.

    The schema rejects malformed contexts up front, but Hop3Config.from_str
    can be called with validate=False. The accessor stays useful by
    filtering out any non-dict values it finds.
    """
    cfg = Hop3Config.from_str(
        """
[contexts.dev]
server = "dev"
""",
        validate=False,
    )
    # Inject a malformed entry post-load (simulates an exotic TOML edge case
    # or a config that bypassed validation). The accessor should still only
    # return the well-formed `dev` entry.
    cfg._data["contexts"]["bogus"] = "this is a string, not a table"
    assert cfg.context_names == ["dev"]
    assert cfg.get_context("bogus") is None


def test_contexts_non_dict_at_top_level_returns_empty():
    """When the [contexts] *table itself* is degenerate, accessors stay safe.

    Schema rejects this when validate=True. Accessors must still cope when
    a caller bypasses validation, mirroring the pattern in `domains`.
    """
    cfg = Hop3Config(_data={"contexts": "this is not a table"})
    assert cfg.contexts == {}
    assert cfg.context_names == []
    assert cfg.get_context("anything") is None


# ---- Field-level validators (parity with server) --------------------------


def test_padded_server_rejected():
    """Whitespace-padded server names are rejected (we do not silently strip)."""
    with pytest.raises(Hop3TomlValidationError) as exc:
        validate_hop3_toml({"contexts": {"dev": {"server": " dev "}}})
    assert "whitespace" in str(exc.value).lower()


def test_empty_app_rejected():
    """`app = ""` is rejected — omit the field to fall back to [metadata].id."""
    with pytest.raises(Hop3TomlValidationError) as exc:
        validate_hop3_toml({"contexts": {"dev": {"server": "s", "app": ""}}})
    assert "app" in str(exc.value).lower()


def test_padded_app_rejected():
    """Whitespace-padded app names are rejected, same rule as server."""
    with pytest.raises(Hop3TomlValidationError) as exc:
        validate_hop3_toml({"contexts": {"dev": {"server": "s", "app": "  myapp  "}}})
    assert "whitespace" in str(exc.value).lower()


def test_empty_domain_entry_rejected():
    """A blank or padded entry in `domains` is rejected."""
    with pytest.raises(Hop3TomlValidationError) as exc:
        validate_hop3_toml({
            "contexts": {"dev": {"server": "s", "domains": ["good.com", " "]}}
        })
    assert "domain" in str(exc.value).lower() or "whitespace" in str(exc.value).lower()


# ---- Per-context HOST_NAME vs domains conflict ----------------------------


def test_context_host_name_env_and_domains_mutually_exclusive():
    """The top-level invariant (HOST_NAME in [env] vs [domains]) holds per-context.

    Regression for a real footgun: a developer copies their top-level
    `[env] HOST_NAME` into `[contexts.prod.env]` while keeping `domains`
    set in the same context. Schema must reject; otherwise the resolver
    silently picks one and the user has no breadcrumb.
    """
    with pytest.raises(Hop3TomlValidationError) as exc:
        validate_hop3_toml({
            "contexts": {
                "prod": {
                    "server": "prod",
                    "domains": ["prod.example.com"],
                    "env": {"HOST_NAME": "other.example.com"},
                }
            }
        })
    msg = str(exc.value)
    assert "HOST_NAME" in msg
    assert "domains" in msg.lower()


def test_context_env_alone_with_host_name_ok():
    """A context with HOST_NAME in env but no domains is valid (legacy shape)."""
    validate_hop3_toml({
        "contexts": {
            "legacy": {
                "server": "s",
                "env": {"HOST_NAME": "legacy.example.com"},
            }
        }
    })


# ---- Context env value types ---------------------------------------------


def test_context_env_accepts_toml_scalars():
    """Context env mirrors top-level [env]: any TOML scalar value is accepted.

    Important because users routinely write TOML booleans / ints unquoted
    (DEBUG = false, PORT = 8080). Forcing strings here would diverge from
    top-level [env] with no operational benefit.
    """
    validate_hop3_toml({
        "contexts": {
            "dev": {
                "server": "s",
                "env": {"DEBUG": False, "PORT": 8080, "NAME": "ok"},
            }
        }
    })


# ---- Context-name validation surfaces correctly ---------------------------


def test_invalid_context_name_error_path_includes_contexts():
    """Bad context names should surface with `contexts` in the error path.

    Regression for an earlier shape where dict-key validation lived in a
    top-level model_validator and lost the loc, producing errors with an
    empty path like `  - : Value error, Invalid context name 'has space'.`
    """
    with pytest.raises(Hop3TomlValidationError) as exc:
        validate_hop3_toml({"contexts": {"has space": {"server": "s"}}})
    msg = str(exc.value)
    assert "contexts" in msg.lower()
    assert "has space" in msg


def test_mixed_case_context_names_accepted():
    """Mixed-case context names are accepted; treated case-sensitively.

    Pins the current decision. If ever changed to lowercase-on-parse,
    this test reverses cheaply.
    """
    validate_hop3_toml({"contexts": {"Prod": {"server": "s"}, "prod": {"server": "s"}}})


# ---- Reserved context names (ADR 042 decision #5) -----------------------


@pytest.mark.parametrize("reserved", ["default", "current", "global", "all", "none"])
def test_reserved_context_name_rejected(reserved: str):
    """Each reserved name is rejected with a message that names the set.

    These collide with current/future CLI keywords (`hop3 context use
    default`, `hop3 context show --all`, etc.) so they cannot appear as
    user-declared context names.
    """
    with pytest.raises(Hop3TomlValidationError) as exc:
        validate_hop3_toml({"contexts": {reserved: {"server": "s"}}})
    msg = str(exc.value)
    assert reserved in msg
    assert "reserved" in msg.lower()


@pytest.mark.parametrize(
    "reserved_variant",
    ["Default", "DEFAULT", "Current", "ALL", "None"],
)
def test_reserved_context_name_case_insensitive(reserved_variant: str):
    """Case variants of reserved names are also rejected.

    The shell may be case-insensitive on the operator's platform (macOS,
    Windows) and the CLI keyword set is case-insensitive too, so
    `Default` and `default` must collide identically.
    """
    with pytest.raises(Hop3TomlValidationError) as exc:
        validate_hop3_toml({"contexts": {reserved_variant: {"server": "s"}}})
    assert "reserved" in str(exc.value).lower()


@pytest.mark.parametrize(
    "name", ["default-app", "current_user", "global-config", "all2", "noneya"]
)
def test_reserved_name_prefix_not_blocked(name: str):
    """Names that *contain* a reserved word as a substring still validate.

    Pins the boundary: `default` is reserved, `default-app` is not.
    Without this test, a future change that loosened the equality to a
    `startswith` check could quietly break user configs.
    """
    validate_hop3_toml({"contexts": {name: {"server": "s"}}})


# ---- ResolvedContext + Hop3Config.resolve_context (ADR 042 Step 2) -------


def test_resolve_minimal_context_inherits_metadata_id():
    """When `app` is absent, it falls back to [metadata].id."""
    cfg = Hop3Config.from_str(
        """
[metadata]
id = "myapp"

[contexts.dev]
server = "dev"
"""
    )
    resolved = cfg.resolve_context("dev")
    assert isinstance(resolved, ResolvedContext)
    assert resolved.name == "dev"
    assert resolved.server == "dev"
    assert resolved.app == "myapp"  # inherited from [metadata].id
    assert resolved.domains == ()
    assert resolved.env == {}


def test_resolve_context_app_override_wins():
    """When the context sets `app`, it wins over [metadata].id."""
    cfg = Hop3Config.from_str(
        """
[metadata]
id = "myapp"

[contexts.staging]
server = "dev"
app = "myapp-staging"
"""
    )
    assert cfg.resolve_context("staging").app == "myapp-staging"


def test_resolve_context_domains_full_replace():
    """Context `domains`, when set, fully replaces top-level [domains].list."""
    cfg = Hop3Config.from_str(
        """
[metadata]
id = "myapp"

[domains]
list = ["fallback.example.com"]

[contexts.prod]
server = "prod"
domains = ["prod.example.com", "www.prod.example.com"]
"""
    )
    resolved = cfg.resolve_context("prod")
    assert resolved.domains == ("prod.example.com", "www.prod.example.com")
    # Specifically: the top-level "fallback.example.com" must NOT be present.
    assert "fallback.example.com" not in resolved.domains


def test_resolve_context_domains_empty_list_blanks_inheritance():
    """`domains = []` is an explicit signal to drop the top-level list.

    Distinct from omitting `domains` (which inherits). The schema accepts
    both shapes; the resolver must distinguish them.
    """
    cfg = Hop3Config.from_str(
        """
[domains]
list = ["fallback.example.com"]

[contexts.bare]
server = "dev"
domains = []
"""
    )
    assert cfg.resolve_context("bare").domains == ()


def test_resolve_context_domains_inherits_when_absent():
    """When the context omits `domains`, it inherits the top-level list."""
    cfg = Hop3Config.from_str(
        """
[domains]
list = ["a.example.com", "b.example.com"]

[contexts.dev]
server = "dev"
"""
    )
    assert cfg.resolve_context("dev").domains == ("a.example.com", "b.example.com")


def test_resolve_context_env_merges_with_top_level():
    """Context env keys override matching top-level; unmatched top-level inherits."""
    cfg = Hop3Config.from_str(
        """
[env]
DEBUG = "true"
LOG_LEVEL = "info"
APP_NAME = "myapp"

[contexts.prod]
server = "prod"

[contexts.prod.env]
DEBUG = "false"
LOG_LEVEL = "warning"
"""
    )
    resolved = cfg.resolve_context("prod")
    # Context wins on matched keys
    assert resolved.env["DEBUG"] == "false"
    assert resolved.env["LOG_LEVEL"] == "warning"
    # Unmatched top-level key still inherits
    assert resolved.env["APP_NAME"] == "myapp"


def test_resolve_context_env_drops_top_level_policy_and_computed():
    """The env merge consumes the *filtered* top-level view.

    `_policy` and `[env.computed]` are top-level concerns; they must not
    leak into the resolved env map.
    """
    cfg = Hop3Config.from_str(
        """
[env]
DEBUG = "true"
_policy = "override"

[env.computed]
URL = "https://${HOST}/"

[contexts.dev]
server = "dev"
"""
    )
    resolved = cfg.resolve_context("dev")
    assert "_policy" not in resolved.env
    assert "computed" not in resolved.env
    assert resolved.env["DEBUG"] == "true"


def test_resolve_context_env_accepts_scalars():
    """Context env can contain TOML booleans/ints; merge preserves types."""
    cfg = Hop3Config.from_str(
        """
[env]
DEBUG = "false"

[contexts.dev]
server = "dev"

[contexts.dev.env]
DEBUG = true
PORT = 8080
"""
    )
    resolved = cfg.resolve_context("dev")
    assert resolved.env["DEBUG"] is True
    assert resolved.env["PORT"] == 8080


def test_resolve_unknown_context_raises_with_declared_names():
    """Unknown context name raises UnknownContextError listing declared names."""
    cfg = Hop3Config.from_str(
        """
[contexts.dev]
server = "dev"

[contexts.prod]
server = "prod"
"""
    )
    with pytest.raises(UnknownContextError) as exc:
        cfg.resolve_context("staging")
    msg = str(exc.value)
    assert "staging" in msg
    assert "dev" in msg
    assert "prod" in msg


def test_resolve_unknown_context_is_a_keyerror_subclass():
    """`except KeyError` still catches UnknownContextError — useful for callers."""
    cfg = Hop3Config.from_str('[contexts.dev]\nserver = "s"\n')
    with pytest.raises(KeyError):
        cfg.resolve_context("missing")


def test_resolved_context_is_frozen():
    """ResolvedContext is a frozen dataclass — mutation must fail."""
    cfg = Hop3Config.from_str('[contexts.dev]\nserver = "s"\n')
    resolved = cfg.resolve_context("dev")
    with pytest.raises((AttributeError, Exception)):
        resolved.server = "mutated"  # type: ignore[misc]


def test_resolve_context_no_metadata_id_no_app_returns_empty_app():
    """Edge case: no metadata.id and no context.app → app is empty string.

    Caller's responsibility to surface the missing-app error. Not the
    resolver's job to invent a name.
    """
    cfg = Hop3Config.from_str('[contexts.dev]\nserver = "s"\n')
    resolved = cfg.resolve_context("dev")
    assert resolved.app == ""


def test_resolve_context_env_drops_context_side_policy_and_computed():
    """Context env must also be filtered — _policy and nested sub-tables go.

    Regression for the blocker in the Step 2 review: the env merge used to
    filter only the top-level (base) view, letting context-level
    ``[contexts.<n>.env]._policy`` and ``[contexts.<n>.env.computed]``
    leak into ResolvedContext.env. ADR 042 says those sentinels are
    top-level-only — both sides of the merge must drop them.
    """
    cfg = Hop3Config.from_str(
        """
[env]
DEBUG = "false"

[contexts.dev]
server = "dev"

[contexts.dev.env]
LOG_LEVEL = "warning"
_policy = "override"

[contexts.dev.env.computed]
URL = "https://${HOST}/"
"""
    )
    resolved = cfg.resolve_context("dev")
    assert "_policy" not in resolved.env
    assert "computed" not in resolved.env
    # The actual env vars survive the filter
    assert resolved.env["DEBUG"] == "false"
    assert resolved.env["LOG_LEVEL"] == "warning"


def test_resolved_context_env_is_immutable():
    """ResolvedContext.env is a MappingProxyType — mutation must fail.

    Sibling guarantee to ``domains`` being a tuple. Frozen-dataclass alone
    only prevents rebinding; without MappingProxyType a caller could write
    ``resolved.env['KEY'] = 'oops'`` and pollute the view.
    """
    cfg = Hop3Config.from_str(
        """
[env]
KEY = "original"

[contexts.dev]
server = "s"
"""
    )
    resolved = cfg.resolve_context("dev")
    with pytest.raises(TypeError):
        resolved.env["KEY"] = "mutated"  # type: ignore[index]


def test_resolve_context_missing_server_raises_named_error():
    """A context dict missing `server` raises UnknownContextError, not KeyError.

    The schema rejects this, but validate=False / direct _data construction
    can bypass it. The error names the bad context to aid debugging.
    """
    cfg = Hop3Config(_data={"contexts": {"bad": {"app": "x"}}})
    with pytest.raises(UnknownContextError) as exc:
        cfg.resolve_context("bad")
    assert "bad" in str(exc.value)
    assert "server" in str(exc.value)


# ---- ADR fidelity --------------------------------------------------------


def test_unknown_server_name_does_not_fail_validation():
    """Cross-file refs to servers are deliberately not validated by the schema.

    Pins ADR 042's "the schema does not validate cross-file references"
    contract — a server name unknown at parse time may still be valid
    at runtime once ~/.config/hop3-cli/servers.toml is consulted.
    """
    validate_hop3_toml({"contexts": {"dev": {"server": "nonexistent-server-name"}}})


def test_adr_canonical_example_parses():
    """The ADR 042 §File layout example is the contract. Pin it.

    Drift between this test and the ADR means one of them must be updated
    deliberately — preferable to silently diverging.
    """
    cfg = Hop3Config.from_str(
        """
[metadata]
id = "myapp"

[contexts.dev]
server = "dev"
app = "myapp-dev"
domains = ["dev.myapp.example.com"]

[contexts.staging]
server = "dev"
app = "myapp-staging"
domains = ["staging.myapp.example.com"]

[contexts.prod]
server = "prod"
app = "myapp"
domains = ["myapp.example.com"]

[contexts.prod.env]
DEBUG = "false"
LOG_LEVEL = "warning"
"""
    )
    # Declaration order preserved (insertion-order from tomllib).
    assert cfg.context_names == ["dev", "staging", "prod"]
    assert cfg.get_context("staging")["server"] == "dev"
    assert cfg.get_context("prod")["env"]["LOG_LEVEL"] == "warning"


# ---- to_dict() round-trip ------------------------------------------------


def test_to_dict_includes_contexts():
    """`to_dict()` must surface contexts so --json / --why don't silently drop them."""
    cfg = Hop3Config.from_str(
        """
[metadata]
id = "myapp"

[contexts.dev]
server = "dev"
app = "myapp-dev"
"""
    )
    serialized = cfg.to_dict()
    assert "contexts" in serialized
    assert serialized["contexts"]["dev"]["app"] == "myapp-dev"
