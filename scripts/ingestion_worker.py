"""Weekly worker for a dedicated process/container; training is a separate operation."""
import argparse
import subprocess
import sys
import time
from pathlib import Path

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--interval-hours',type=float,default=168)
    args = parser.parse_args()
    if args.interval_hours < 1:
        parser.error('Interval must be at least one hour')
    job = Path(__file__).with_name('update_forecasts.py')
    while True:
        result = subprocess.run([sys.executable, str(job)], check=False)
        print(f'Update job exited {result.returncode}; next attempt in {args.interval_hours} hours', flush=True)
        time.sleep(args.interval_hours * 3600)
