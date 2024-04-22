#!/usr/bin/env fish

# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

reuse annotate --copyright "Copyright (c) 2023-2024, Abilian SAS" \
    src/**/*.py tests/**/*.py scripts/**/*
reuse annotate --license AGPL-3.0 \
    src/**/*.py tests/**/*.py scripts/**/*
