(ns app.core
  (:require [ring.adapter.jetty :refer [run-jetty]])
  (:gen-class))

(defn handler [req]
  {:status 200
   :headers {"Content-Type" "text/plain"}
   :body "Hello World, from Clojure via Nix!"})

(defn -main
  [& args]
  (let [port (Integer/parseInt (or (System/getenv "PORT") "3000"))]
    (run-jetty handler {:port port :join? true})
    (println (str "Server running on port " port))))
