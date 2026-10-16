"""Compatibility entry for the shared Cloudflare preferred-IP tool."""
from pathlib import Path
import runpy
import sys

root = Path(r'I:\Codes\Proxy\Cloudflare-Preferred-IP')
sys.path.insert(0, str(root))
if __name__ == '__main__':
    runpy.run_path(str(root / 'sync.py'), run_name='__main__')
