"""App specs registry.

Each spec is imported here and registered in the SPECS dict under the
app's pname. In the real implementation, specs will be parsed from
hop3.toml files in app source directories.
"""

from hop3_nix_gen.spec import AppSpec
from hop3_nix_gen.specs.focalboard import SPEC as FOCALBOARD_SPEC
from hop3_nix_gen.specs.gitea import SPEC as GITEA_SPEC
from hop3_nix_gen.specs.grafana import SPEC as GRAFANA_SPEC
from hop3_nix_gen.specs.mattermost import SPEC as MATTERMOST_SPEC
from hop3_nix_gen.specs.miniflux import SPEC as MINIFLUX_SPEC
from hop3_nix_gen.specs.vikunja import SPEC as VIKUNJA_SPEC

SPECS: dict[str, AppSpec] = {
    MINIFLUX_SPEC.pname: MINIFLUX_SPEC,
    GITEA_SPEC.pname: GITEA_SPEC,
    FOCALBOARD_SPEC.pname: FOCALBOARD_SPEC,
    GRAFANA_SPEC.pname: GRAFANA_SPEC,
    MATTERMOST_SPEC.pname: MATTERMOST_SPEC,
    VIKUNJA_SPEC.pname: VIKUNJA_SPEC,
}
