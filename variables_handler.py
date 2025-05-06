#!/usr/bin/env python3
import time
import hal
import os
import re

h = hal.component("variables_handler")
h.newpin("var80", hal.HAL_FLOAT, hal.HAL_IO)  # Changed from OUT to IO
h.newpin("var81", hal.HAL_FLOAT, hal.HAL_IO)  # Changed from IN to IO
h.ready()

vars_path = os.path.expanduser("~/linuxcnc/configs/xzacw/variables.txt")

def read_var(number):
    with open(vars_path, 'r') as f:
        for line in f:
            match = re.match(rf"#\s*{number}\s*=\s*(-?\d+(?:\.\d+)?)", line)
            if match:
                return float(match.group(1))
    return 0.0

def write_var(number, value):
    with open(vars_path, 'r') as f:
        lines = f.readlines()
    updated = False
    with open(vars_path, 'w') as f:
        for line in lines:
            if line.strip().startswith(f"#{number}="):
                f.write(f"#{number}={int(value)}\n")
                updated = True
            else:
                f.write(line)
        if not updated:
            f.write(f"#{number}={int(value)}\n")

while True:
    # Read latest values from file
    file_80 = read_var(80)
    file_81 = read_var(81)

    # Sync HAL input to file (if user changed it externally)
    if abs(file_80 - h['var80']) > 0.01:
        h['var80'] = file_80
    else:
        write_var(80, h['var80'])

    if abs(file_81 - h['var81']) > 0.01:
        h['var81'] = file_81
    else:
        write_var(81, h['var81'])

    time.sleep(0.1)
