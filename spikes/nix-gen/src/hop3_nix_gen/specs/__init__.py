"""App specs registry.

Each spec is imported here and registered in the SPECS dict under the
app's pname. In the real implementation, specs will be parsed from
hop3.toml files in app source directories.
"""

from hop3_nix_gen.spec import AppSpec
from hop3_nix_gen.specs.adminer import SPEC as ADMINER_SPEC
from hop3_nix_gen.specs.bookstack import SPEC as BOOKSTACK_SPEC
from hop3_nix_gen.specs.dolibarr import SPEC as DOLIBARR_SPEC
from hop3_nix_gen.specs.easy_appointments import SPEC as EASY_APPOINTMENTS_SPEC
from hop3_nix_gen.specs.focalboard import SPEC as FOCALBOARD_SPEC
from hop3_nix_gen.specs.gitea import SPEC as GITEA_SPEC
from hop3_nix_gen.specs.grafana import SPEC as GRAFANA_SPEC
from hop3_nix_gen.specs.invoice_ninja import SPEC as INVOICE_NINJA_SPEC
from hop3_nix_gen.specs.isso import SPEC as ISSO_SPEC
from hop3_nix_gen.specs.jenkins import SPEC as JENKINS_SPEC
from hop3_nix_gen.specs.kanboard import SPEC as KANBOARD_SPEC
from hop3_nix_gen.specs.limesurvey import SPEC as LIMESURVEY_SPEC
from hop3_nix_gen.specs.matomo import SPEC as MATOMO_SPEC
from hop3_nix_gen.specs.mattermost import SPEC as MATTERMOST_SPEC
from hop3_nix_gen.specs.miniflux import SPEC as MINIFLUX_SPEC
from hop3_nix_gen.specs.nextcloud import SPEC as NEXTCLOUD_SPEC
from hop3_nix_gen.specs.radicale import SPEC as RADICALE_SPEC
from hop3_nix_gen.specs.vikunja import SPEC as VIKUNJA_SPEC
from hop3_nix_gen.specs.wiki_js import SPEC as WIKI_JS_SPEC
from hop3_nix_gen.specs.wordpress import SPEC as WORDPRESS_SPEC

SPECS: dict[str, AppSpec] = {
    # prebuilt-binary (2)
    MINIFLUX_SPEC.pname: MINIFLUX_SPEC,
    GITEA_SPEC.pname: GITEA_SPEC,
    # prebuilt-archive (4)
    FOCALBOARD_SPEC.pname: FOCALBOARD_SPEC,
    GRAFANA_SPEC.pname: GRAFANA_SPEC,
    MATTERMOST_SPEC.pname: MATTERMOST_SPEC,
    VIKUNJA_SPEC.pname: VIKUNJA_SPEC,
    # php-app (10)
    ADMINER_SPEC.pname: ADMINER_SPEC,
    BOOKSTACK_SPEC.pname: BOOKSTACK_SPEC,
    DOLIBARR_SPEC.pname: DOLIBARR_SPEC,
    EASY_APPOINTMENTS_SPEC.pname: EASY_APPOINTMENTS_SPEC,
    INVOICE_NINJA_SPEC.pname: INVOICE_NINJA_SPEC,
    KANBOARD_SPEC.pname: KANBOARD_SPEC,
    LIMESURVEY_SPEC.pname: LIMESURVEY_SPEC,
    MATOMO_SPEC.pname: MATOMO_SPEC,
    NEXTCLOUD_SPEC.pname: NEXTCLOUD_SPEC,
    WORDPRESS_SPEC.pname: WORDPRESS_SPEC,
    # node-prebuilt (1)
    WIKI_JS_SPEC.pname: WIKI_JS_SPEC,
    # java-war (1)
    JENKINS_SPEC.pname: JENKINS_SPEC,
    # python-venv (1)
    ISSO_SPEC.pname: ISSO_SPEC,
    # nixpkgs-wrapper (1)
    RADICALE_SPEC.pname: RADICALE_SPEC,
}
