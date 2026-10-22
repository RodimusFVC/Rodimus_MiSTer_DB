#!/usr/bin/env python3
"""Generate external_files.csv for the Rodimus MiSTer custom database.

Reads each core repo's PUSHED releases/ folder via the GitHub API (not local disk),
pinned to the current commit SHA.
  - latest rbf  -> external_files.csv row (size/MD5 left blank; the DB CI fills them in)
  - .mgl/.mra   -> copied unchanged into this repo (the DB build reads them from the checkout)

Layout on the MiSTer:
    _RodimusCores/_<Category>/<launchers, subfolders>
    _RodimusCores/_<Category>/cores/<rbf>

Usage: python3 .github/gen_external_files.py
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
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# repo, category (deploy subfolder without '_')
CORES = [
    ('InteractiveFiction-Frotz_MiSTer', 'InteractiveFiction'),
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


def rows_for_core(repo, category):
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

    # latest rbf only, filename unchanged -> external_files.csv row
    rbfs = []
    for p in files:
        m = RBF_RE.match(p[len('releases/'):])
        if m:
            rbfs.append((m.group('date'), p))
    if not rbfs:
        sys.exit(f'{full}: no <Core>_yyyymmdd.rbf in releases/')
    _, rbf_path = max(rbfs)
    rows = [[f'{ROOT}/_{category}/cores/{os.path.basename(rbf_path)}', url(rbf_path), '', '', '']]

    # launchers: db_operator.py opens every .mgl/.mra from the checkout, so they must be
    # committed in this repo. Copied byte-for-byte, keeping releases/ subfolders (_alternatives/ etc.)
    dest_root = os.path.join(REPO, ROOT, f'_{category}')
    wanted = set()
    for p in sorted(files):
        if p.lower().endswith(LAUNCHER_EXTS):
            dest = os.path.join(dest_root, p[len('releases/'):])
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with urllib.request.urlopen(url(p)) as r, open(dest, 'wb') as f:
                f.write(r.read())
            wanted.add(dest)

    # drop launchers that are no longer in the core's releases/
    for dirpath, _, names in os.walk(dest_root):
        for n in names:
            path = os.path.join(dirpath, n)
            if n.lower().endswith(LAUNCHER_EXTS) and path not in wanted:
                os.remove(path)
                print(f'removed stale {path}', file=sys.stderr)

    print(f'{full} @ {sha[:10]}: {os.path.basename(rbf_path)} + {len(wanted)} launchers', file=sys.stderr)
    return rows


def main():
    out = os.path.join(REPO, 'external_files.csv')
    rows = []
    for repo, category in CORES:
        rows += rows_for_core(repo, category)
    with open(out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)
    print(f'wrote {len(rows)} rows -> {out}', file=sys.stderr)


if __name__ == '__main__':
    main()
