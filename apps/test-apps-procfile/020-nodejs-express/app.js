// This is the server

const express = require("express");
const fs = require("fs");
const app = express();

const port = process.env["PORT"] || 3000;
const addr = process.env["BIND_ADDRESS"] || "127.0.0.1";

app.get("/", (req, res) => {
  res.send("Hello World, from Node/Express on port " + port + " !");
});

// Listen to the port provided
app.listen(port, addr, () => {
  console.log("Node app listening on " + addr + ":" + port);
});
