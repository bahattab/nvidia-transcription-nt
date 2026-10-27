"""Create an isolated, reproducible client environment without saving secrets."""
import argparse
from pathlib import Path
import subprocess
import sys
import venv

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--env', required=True, type=Path)
    a = p.parse_args()
    if sys.version_info < (3, 10):
        p.error('Python 3.10 or newer is required')
    target = a.env.expanduser().resolve()
    if target.exists() and any(target.iterdir()) and not (target / 'pyvenv.cfg').is_file():
        p.error('Refusing to use a nonempty directory that is not a virtual environment')
    if not (target / 'pyvenv.cfg').is_file():
        venv.EnvBuilder(with_pip=True).create(target)
    exe = target / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    root = Path(__file__).resolve().parent.parent
    subprocess.run([str(exe), '-m', 'pip', 'install', '-r', str(root / 'requirements.txt')], check=True)
    subprocess.run([str(exe), '-m', 'pip', 'check'], check=True)
    subprocess.run([str(exe), str(root / 'scripts/transcribe.py'), '--check'], check=True)
    print(f'Environment ready: {exe}')

if __name__ == '__main__':
    main()
