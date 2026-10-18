"""python -m lab.data FILE.csv [--all]  ->  JSON on stdout; exit 1 if the data is not analyzable."""
import sys

from .analytics import DataNotAnalyzableError, analyze_csv


def main(argv: list[str]) -> int:
    args = [a for a in argv if a != "--all"]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        analysis = analyze_csv(args[0])
    except DataNotAnalyzableError as e:
        print(e.result.model_dump_json(indent=2))
        return 1
    if "--all" not in argv:  # overall only by default; by-channel/campaign/date can be thousands of rows
        analysis = analysis.model_copy(update={"metrics": [m for m in analysis.metrics if m.scope == "overall"]})
    print(analysis.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
