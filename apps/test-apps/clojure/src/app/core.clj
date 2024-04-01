(ns app.core
  (:require [clj-time.core :as t]
            [aleph.http :as http])
  (:gen-class))

(defn app [req]
  {:status  200
   :headers {"Content-Type" "text/html"}
   :body    "Hello world!"})

(defn -main
  "I don't do a whole lot ... yet."
  [& args]
  (let [port (Integer/parseInt (or (System/getenv "PORT") "9500"))]
  (http/start-server app {:port port})
  (println (str "Running server at http://127.0.0.1:" port "/"))))
