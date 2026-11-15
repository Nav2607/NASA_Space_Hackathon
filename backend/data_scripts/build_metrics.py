"""Build versioned continuous rotation diagnostics without overwriting old datasets.

Old crop_year_metrics.csv and anchor_summary.json are retained as legacy artifacts;
the corrected API never uses independent crop-year averages for rotation scoring.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import recommend as R, rotations
from engine.weather import load_anchors, load_reference


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--anchor', choices=list(load_anchors()), default='guelph')
    p.add_argument('--soil', choices=['loam','clay','clay_loam','sandy_loam'], default='loam')
    p.add_argument('--output', type=Path, default=Path('backend/data/processed/rotation_metrics_v2.json'))
    args = p.parse_args()
    # Do not overwrite preserved pre-correction datasets, even through --output.
    preserved = {'crop_year_metrics.csv','anchor_summary.json'}
    if args.output.name in preserved:
        p.error('Use a new output filename; legacy cached datasets are preserved')
    rows = []
    rejected = []
    for rotation in rotations.all_candidates(load_reference('rotation_rules')):
        try:
            entry = R.build_entry(args.anchor,args.soil,rotation)
            future = R._future(args.anchor,args.soil,rotation)
            rows.append({'rotation':rotation,'time_machine':R._time_machine(args.anchor,args.soil,rotation,future),
                         'historical_2005_2024':entry['historical_run']})
        except (ValueError,KeyError,OSError) as err:
            rejected.append({'rotation':rotation,'reason':str(err)})
    doc = {'schema_version':2,'anchor':args.anchor,'soil':args.soil,'et0_method':R.ET0_METHOD,
           'assumptions':R.ASSUMPTIONS,'rotations':rows,'rejected':rejected}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    tmp=args.output.with_suffix('.tmp')
    tmp.write_text(json.dumps(doc,allow_nan=False,indent=2)+'\n')
    tmp.replace(args.output)
    print(f'Saved {len(rows)} continuous rotations; {len(rejected)} rejected: {args.output}')


if __name__ == '__main__':
    main()
