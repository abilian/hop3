// Simple Express server for Hop3 Nix integration

const express = require("express");
const app = express();

const port = process.env["PORT"] || 3000;
const addr = process.env["BIND_ADDRESS"] || "127.0.0.1";

app.get("/", (req, res) => {
  res.send("Hello World, from Node/Express via Nix!");
});

app.listen(port, addr, () => {
  console.log("Node app listening on " + addr + ":" + port);
});
