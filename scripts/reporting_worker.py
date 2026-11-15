"""Periodically verify and refresh accessible reporting; never run forecasts."""
import argparse
import subprocess
import sys
import time
from pathlib import Path

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--interval-hours',type=float,default=24)
    args=parser.parse_args()
    if args.interval_hours<1:parser.error('Interval must be at least one hour')
    while True:
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('update_reporting.py'))],check=False)
        print(f'Reporting check/update exited {result.returncode}; next check in {args.interval_hours} hours',flush=True)
        time.sleep(args.interval_hours*3600)
