#!/usr/bin/env python3
"""
Dev helper: clear __pycache__, run migrations, start runserver.
Usage: python durga.py
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)


def clear_pycache():
    for dirpath, dirnames, _filenames in os.walk(ROOT):
        if '__pycache__' in dirnames:
            p = os.path.join(dirpath, '__pycache__')
            shutil.rmtree(p, ignore_errors=True)


def main():
    clear_pycache()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.dev')
    subprocess.run([sys.executable, 'manage.py', 'migrate'], check=False)
    subprocess.run(
        [sys.executable, 'manage.py', 'runserver', '0.0.0.0:8000'],
        check=False,
    )


if __name__ == '__main__':
    main()
