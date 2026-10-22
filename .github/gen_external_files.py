#!/usr/bin/env python3
"""Generate external_files.csv for the Rodimus MiSTer custom database.

Reads each core repo's PUSHED releases/ folder via the GitHub API (not local disk)
and pins every URL to the current commit SHA, so the hash the DB CI computes always
matches what users download. Size/MD5 columns are left blank: db_operator.py
downloads each file in CI and fills them in.

Layout on the MiSTer:
    _RodimusCores/_<Category>/<launchers, subfolders>
    _RodimusCores/_<Category>/cores/<Core>_<date>.rbf      (MGL-launched cores)
    _RodimusCores/cores/<Core>_<date>.rbf                  (MRA-launched cores: Main_MiSTer
                                                            looks for the rbf in <first _Folder>/cores)

Usage: python3 .github/gen_external_files.py   (writes external_files.csv in the repo root)
"""
import csv
import json
import os
import re
import sys
import urllib.parse
import urllib.request

OWNER = 'RodimusFVC'
ROOT = '_RodimusCores'

# repo, category (deploy subfolder without '_'), launcher type ('mgl' or 'mra')
CORES = [
    ('InteractiveFiction-Frotz_MiSTer', 'InteractiveFiction', 'mgl'),
]

LAUNCHER_EXTS = ('.mgl', '.mra')
RBF_RE = re.compile(r'^(?:(?P<prefix>[A-Za-z0-9]+)-)?(?P<core>.+)_(?P<date>\d{8})\.rbf$')

HEADER = ['Path in MiSTer', 'URL', 'Size in bytes (optional but recommended)',
          'MD5 Hash (optional but recommended)', 'Filter Terms (optional)']


def api(path):
    req = urllib.request.Request(f'https://api.github.com{path}',
                                 headers={'Accept': 'application/vnd.github+json'})
    token = os.getenv('GITHUB_TOKEN')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def rows_for_core(repo, category, launcher):
    full = f'{OWNER}/{repo}'
    branch = api(f'/repos/{full}')['default_branch']
    sha = api(f'/repos/{full}/commits/{branch}')['sha']
    tree = api(f'/repos/{full}/git/trees/{sha}?recursive=1')
    if tree.get('truncated'):
        sys.exit(f'{full}: git tree truncated, cannot list releases/ reliably')

    files = [e['path'] for e in tree['tree']
             if e['type'] == 'blob' and e['path'].startswith('releases/')]

    def url(path):
        return f'https://raw.githubusercontent.com/{full}/{sha}/{urllib.parse.quote(path)}'

    rows = []

    # latest rbf only, category prefix stripped (InteractiveFiction-Frotz_20261022.rbf -> Frotz_20261022.rbf)
    rbfs = []
    for p in files:
        m = RBF_RE.match(p[len('releases/'):])
        if m:
            rbfs.append((m.group('date'), m.group('core'), p))
    if not rbfs:
        sys.exit(f'{full}: no <Core>_yyyymmdd.rbf in releases/')
    date, core, rbf_path = max(rbfs)
    cores_dir = f'{ROOT}/_{category}/cores' if launcher == 'mgl' else f'{ROOT}/cores'
    rows.append([f'{cores_dir}/{core}_{date}.rbf', url(rbf_path), '', '', ''])

    # launchers, keeping their releases/ subfolder structure (_alternatives/ etc.)
    for p in sorted(files):
        if p.lower().endswith(LAUNCHER_EXTS):
            rows.append([f'{ROOT}/_{category}/{p[len("releases/"):]}', url(p), '', '', ''])

    print(f'{full} @ {sha[:10]}: {core}_{date}.rbf + {len(rows) - 1} launchers', file=sys.stderr)
    return rows


def main():
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'external_files.csv')
    rows = []
    for repo, category, launcher in CORES:
        rows += rows_for_core(repo, category, launcher)
    with open(out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)
    print(f'wrote {len(rows)} rows -> {out}', file=sys.stderr)


if __name__ == '__main__':
    main()
