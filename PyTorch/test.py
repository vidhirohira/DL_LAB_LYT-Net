import os
import sys
import argparse

# Ensure local imports work
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from evaluate import evaluate, build_parser

def main():
    parser = build_parser()
    args = parser.parse_args()
    evaluate(args)

if __name__ == '__main__':
    main()
