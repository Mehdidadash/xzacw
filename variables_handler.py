#!/usr/bin/env python3
import hal
import time

FILE_PATH = '/home/cnc/linuxcnc/configs/xzacw/variables.txt'

def read_values():
    try:
        with open(FILE_PATH, 'r') as f:
            lines = f.readlines()
            values = {}
            for line in lines:
                key, value = line.strip().split('=')
                values[key] = float(value)
            return values
    except Exception as e:
        print(f"Failed to read file: {e}")
        return {"wearc": 0.0, "partcount": 0.0}

def write_values(values):
    try:
        with open(FILE_PATH, 'w') as f:
            for key, value in values.items():
                f.write(f"{key}={value}\n")
    except Exception as e:
        print(f"Failed to write file: {e}")

def main():
    h = hal.component("variables_handler")
    h.newpin("wearc", hal.HAL_FLOAT, hal.HAL_IN)
    h.newpin("partcount", hal.HAL_FLOAT, hal.HAL_IN)
    h.ready()

    values = read_values()
    h['wearc'] = values.get("wearc", 0.0)
    h['partcount'] = values.get("partcount", 0.0)

    print(f"Initialized variables: wearc={h['wearc']}, partcount={h['partcount']}")

    try:
        prev_values = values.copy()
        while True:
            values["wearc"] = h['wearc']
            values["partcount"] = h['partcount']
            if values != prev_values:
                write_values(values)
                prev_values = values.copy()
            time.sleep(1)

    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()