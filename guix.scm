;; Use this to build a Guix package from the current git checkout.
;; Note that uncommitted changes will not be included!

;; Use like this:
;;    guix build -f guix.scm
;; or:
;     guix shell -C -f guix.scm
;; or:
;;    guix time-machine -C channels.scm -- build -f guix.scm


(use-modules (guix build-system pyproject)
    (guix git)
    (guix gexp)
    (guix packages)
    (guix licenses)
    (gnu packages base))

;; (include "manifest.scm")

(package
    (name "hop3")
    (version "0.1.0")
    (source (git-checkout (url (dirname (current-filename)))))
    (build-system pyproject-build-system)
    ;; (propagated-inputs %packages)
    ;; (native-inputs %dev-packages)
    (home-page "https://github.com/abilian/hop3")
    (synopsis "Simple PaaS - Deploy and manage web applications on a single server")
    (description "Simple PaaS - Deploy and manage web applications on a single server")
    (license agpl3))
