# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Producer↔consumer round-trip for the catalog (ADR 049).

Publishes a catalog with a throwaway key via ``publish.py``, then feeds the
result through the *real* node path (``install_catalog_tarball`` →
``verify_minisign`` + ``verify_tree_against_index`` + atomic publish). If the
producer and the verifier disagree about the minisign/index format, this fails.
"""

from __future__ import annotations

import pytest

from hop3.server.catalog.publish import (
    PublishError,
    generate_keypair,
    main,
    publish,
)
from hop3.server.catalog.sync import install_catalog_tarball, read_high_water_mark
from hop3.server.catalog.verify import CatalogVerificationError

APP_TOML = '[metadata]\nid = "nextcloud"\ntitle = "Nextcloud"\n'


def _content(tmp_path, toml=APP_TOML):
    app = tmp_path / "content" / "nextcloud"
    app.mkdir(parents=True)
    (app / "hop3.toml").write_text(toml)
    (app / "readme.md").write_text("# Nextcloud\nHello.\n")
    return tmp_path / "content"


def test_published_catalog_installs_and_verifies(tmp_path):
    pub_text, sec_text = generate_keypair()
    content = _content(tmp_path)
    out = publish(content, sec_text, tmp_path / "dist", serial=7)

    catalog_root = tmp_path / "home" / "catalog"
    state_root = tmp_path / "home" / "catalog-state"
    result = install_catalog_tarball(
        out["tarball"],
        out["signature"].read_text(),
        pub_text,
        catalog_root,
        state_root,
    )

    assert result.serial == 7
    assert catalog_root.resolve().name == "catalog-7"
    assert (catalog_root / "nextcloud" / "hop3.toml").read_text() == APP_TOML
    assert read_high_water_mark(state_root) == 7


def test_wrong_key_is_rejected(tmp_path):
    _signer_pub, signer_sec = generate_keypair()
    attacker_pub, _attacker_sec = generate_keypair()
    out = publish(_content(tmp_path), signer_sec, tmp_path / "dist", serial=1)

    with pytest.raises(CatalogVerificationError):
        install_catalog_tarball(
            out["tarball"],
            out["signature"].read_text(),
            attacker_pub,  # not the key that signed it
            tmp_path / "home" / "catalog",
            tmp_path / "home" / "catalog-state",
        )


def test_publish_rejects_catchall_host_before_signing(tmp_path):
    # The catch-all "_" host would hijack the proxy default server — the publish
    # gate (F7) must refuse it before anything is signed.
    bad = APP_TOML + '\n[domains]\nlist = ["_"]\n'
    with pytest.raises(PublishError, match="catch-all"):
        publish(_content(tmp_path, toml=bad), generate_keypair()[1], tmp_path / "d", 1)


def test_publish_rejects_app_without_toml(tmp_path):
    content = tmp_path / "content"
    (content / "broken").mkdir(parents=True)
    (content / "broken" / "readme.md").write_text("orphan")
    with pytest.raises(PublishError, match=r"no hop3\.toml"):
        publish(content, generate_keypair()[1], tmp_path / "dist", serial=1)


def test_validate_cli_accepts_good_content(tmp_path):
    # The content-repo CI gate: validate runs the coexistence check, no signing.
    assert main(["validate", str(_content(tmp_path))]) == 0


def test_validate_cli_rejects_bad_spec(tmp_path):
    bad = APP_TOML + '\n[domains]\nlist = ["_"]\n'
    assert main(["validate", str(_content(tmp_path, toml=bad))]) == 1
