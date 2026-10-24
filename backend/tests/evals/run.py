"""CLI evals: `python -m tests.evals.run from-csv <in.csv> <out.jsonl>`.

Сами прогоны — `make evals` (pytest -m evals): им нужна мигрированная БД со справочником.
"""

import argparse
from pathlib import Path

from tests.evals.dataset import from_csv


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("from-csv")
    c.add_argument("src", type=Path)
    c.add_argument("out", type=Path)
    args = ap.parse_args()
    print(f"{from_csv(args.src, args.out)} rows → {args.out}")


if __name__ == "__main__":
    main()
