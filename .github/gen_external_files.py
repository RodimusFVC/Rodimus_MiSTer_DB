#!/usr/bin/env python3
"""Build db.json.zip for the Rodimus MiSTer custom database.

Every file is referenced by URL straight into its core repo: nothing is copied into this repo.
Reads each core repo's PUSHED releases/ folder via the GitHub API, pinned to the current
commit SHA, downloads each file only to compute its MD5 and size, and writes the database
per docs/custom-databases.md of Downloader_MiSTer.

Layout on the MiSTer:
    _RodimusCores/_<Category>/<launchers, subfolders>
    _RodimusCores/_<Category>/cores/<rbf>

Usage: python3 .github/gen_external_files.py <output db.json.zip>
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

OWNER = 'RodimusFVC'
ROOT = '_RodimusCores'
DB_ID = 'RodimusFVC/Rodimus_MiSTer_DB'   # already published: never change

# repo, category (deploy subfolder without '_')
CORES = [
    ('InteractiveFiction-Frotz_MiSTer', 'InteractiveFiction'),
    ('VCR_Robots', 'VCR'),
]

LAUNCHER_EXTS = ('.mgl', '.mra')
RBF_RE = re.compile(r'^.+_(?P<date>\d{8})\.rbf$')


def api(path):
    req = urllib.request.Request(f'https://api.github.com{path}',
                                 headers={'Accept': 'application/vnd.github+json'})
    token = os.getenv('GITHUB_TOKEN')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def entries_for_core(repo, category):
    """Returns [(path on MiSTer, url)] for the latest rbf and every launcher in releases/."""
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

    rbfs = [(m.group('date'), p) for p in files
            if (m := RBF_RE.match(p[len('releases/'):]))]
    if not rbfs:
        sys.exit(f'{full}: no <Core>_yyyymmdd.rbf in releases/')
    _, rbf_path = max(rbfs)
    entries = [(f'{ROOT}/_{category}/cores/{os.path.basename(rbf_path)}', url(rbf_path))]

    launchers = [p for p in sorted(files) if p.lower().endswith(LAUNCHER_EXTS)]
    entries += [(f'{ROOT}/_{category}/{p[len("releases/"):]}', url(p)) for p in launchers]

    print(f'{full} @ {sha[:10]}: {os.path.basename(rbf_path)} + {len(launchers)} launchers', file=sys.stderr)
    return entries


def describe(entry):
    path, url = entry
    with urllib.request.urlopen(url) as r:
        data = r.read()
    return path, {'hash': hashlib.md5(data).hexdigest(), 'size': len(data), 'url': url}


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    out = sys.argv[1]

    entries = []
    for repo, category in CORES:
        entries += entries_for_core(repo, category)

    with ThreadPoolExecutor(max_workers=8) as pool:
        files = dict(pool.map(describe, entries))

    folders = {}
    for path in files:
        parent = os.path.dirname(path)
        while parent:
            folders[parent] = {}
            parent = os.path.dirname(parent)

    db = {
        'v': 1,
        'db_id': DB_ID,
        'timestamp': int(time.time()),
        'files': dict(sorted(files.items())),
        'folders': dict(sorted(folders.items())),
    }
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('db.json', json.dumps(db, indent=2))
    print(f'wrote {len(files)} files, {len(folders)} folders -> {out}', file=sys.stderr)


if __name__ == '__main__':
    main()
