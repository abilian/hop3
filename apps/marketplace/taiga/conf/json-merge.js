#!/usr/bin/env node

'use strict';

var fs = require('fs');

var target = JSON.parse(fs.readFileSync(process.argv[2]));
var source = JSON.parse(fs.readFileSync(process.argv[3]));
target = Object.assign({}, source, target);
fs.writeFileSync(process.argv[2], JSON.stringify(target, null, 4));
