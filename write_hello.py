#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(base_dir, "hello.txt")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("hello word\n")

    print(f"[write_hello.py] Wrote to {output_file}")

if __name__ == "__main__":
    main()
