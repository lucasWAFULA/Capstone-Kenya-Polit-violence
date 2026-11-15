"""Build the complete daily foundation from the latest verified local API master."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from severity_service.daily_panel import build_daily_dataset

if __name__ == '__main__':
    report, output = build_daily_dataset(ROOT)
    print(json.dumps(report,indent=2))
    print('Dataset directory:',output)
