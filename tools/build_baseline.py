"""Generate the organisers' +/-50-frame fallback, without reading any labels.

This is a reproducibility starting point, not our claimed improvement. Emits UTF-8
and LF explicitly, so a rerun on a different OS produces the same CSV bytes.
"""
import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / 'more-than-a-hack-2027-main'
sys.path.insert(0, str(UPSTREAM))
from starter import baseline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'submissions/baseline_fallback.csv')
    args = parser.parse_args()
    labels = baseline.smooth(baseline.build(), 50)
    if len(labels) != 199319:
        raise ValueError('Incorrect tactical frame count')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('w', encoding='utf-8', newline='') as handle:
        handle.write('frame,label\n')
        handle.writelines(f'{frame},{label}\n' for frame, label in enumerate(labels))
    print('Wrote:', args.out)
    print('SHA256:', hashlib.sha256(args.out.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
