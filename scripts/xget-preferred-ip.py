"""Compatibility entry for the shared Cloudflare preferred-IP tool."""
from pathlib import Path
import runpy
import sys

root = Path(r'I:\Codes\Proxy\Cloudflare-Preferred-IP')
sys.path.insert(0, str(root))
if __name__ == '__main__':
    sys.argv[1:1] = ['--service', 'xget']
    runpy.run_path(str(root / 'engine.py'), run_name='__main__')
