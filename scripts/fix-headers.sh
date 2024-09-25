#!/usr/bin/env bash

# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-3.0

shopt -s globstar

reuse annotate --copyright "Copyright (c) 2023-2024, Abilian SAS" \
    src/**/*.py tests/**/*.py scripts/**/*
reuse annotate --license AGPL-3.0 \
    src/**/*.py tests/**/*.py scripts/**/*
