(defproject clojure-hello "0.1.0"
  :description "Simple Clojure hello world for Hop3 Nix integration"
  :dependencies [[org.clojure/clojure "1.11.1"]
                 [ring/ring-core "1.10.0"]
                 [ring/ring-jetty-adapter "1.10.0"]]
  :main ^:skip-aot app.core
  :target-path "target/%s"
  :profiles {:uberjar {:aot :all
                       :jvm-opts ["-Dclojure.compiler.direct-linking=true"]}})
