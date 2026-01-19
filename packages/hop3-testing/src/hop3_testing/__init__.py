# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Hop3 deployment testing framework."""

from __future__ import annotations

import warnings

# Suppress TripleDES deprecation warnings from paramiko
# This happens when paramiko imports the cipher at module load time
# We disable using it in connections via disabled_algorithms config
try:
    from cryptography.utils import CryptographyDeprecationWarning

    warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)
except ImportError:
    # Fallback if CryptographyDeprecationWarning not available
    warnings.filterwarnings("ignore", message=".*TripleDES.*")
