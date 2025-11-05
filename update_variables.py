#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_variables.py

Usage:
    python3 update_variables.py <name> <value>

Keeps variables.txt consistent and writes variables_pipe.json for GladeVCP.
"""

import os
import sys
import json

if len(sys.argv) != 3:
    print("Usage: python3 update_variables.py <name> <value>")
    sys.exit(1)

name, value = sys.argv[1], sys.argv[2]

base_dir = "/home/cnc/linuxcnc/configs/xzacw"
vars_file = os.path.join(base_dir, "variables.txt")
pipe_file = os.path.join(base_dir, "variables_pipe.json")

# --- Update variables.txt ---
vars_dict = {}

# Read existing lines
if os.path.exists(vars_file):
    with open(vars_file, "r") as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                vars_dict[k.strip()] = v.strip()

# Update target variable
vars_dict[name] = value

# Write back all
with open(vars_file, "w") as f:
    for k, v in vars_dict.items():
        f.write(f"{k}={v}\n")

# --- Write pipe file ---
try:
    with open(pipe_file, "w") as f:
        json.dump(vars_dict, f)
    print(f"Updated {pipe_file}: {vars_dict}")
except Exception as e:
    print(f"Error writing {pipe_file}: {e}")
