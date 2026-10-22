#!/usr/bin/env python3
"""Build db.json.zip for the Rodimus MiSTer custom database.

Every file is referenced by URL straight into its core repo: nothing is copied into this repo.
Reads each core repo's PUSHED releases/ folder via the GitHub API, pinned to the current
commit SHA, downloads each file only to compute its MD5 and size, and writes the database
per docs/custom-databases.md of Downloader_MiSTer.

Layout on the MiSTer:
    _RodimusCores/_<Category>/<launchers, subfolders>
    _RodimusCores/cores/<rbf>                  (MRA repos)
    _RodimusCores/_<Category>/cores/<rbf>      (MGL-only repos)
    rbf installed without its <Category>- prefix

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
    ('Arcade-Arabian_MiSTer', 'Arcade'),
    ('Arcade-BluePrint_MiSTer', 'Arcade'),
    ('Arcade-Centipede_MiSTer', 'Arcade'),
    ('Arcade-ChampionBaseball_MiSTer', 'Arcade'),
    ('Arcade-CrazyClimber_MiSTer', 'Arcade'),
    ('Arcade-DECOCassette_MiSTer', 'Arcade'),
    ('Arcade-Exidy_MiSTer', 'Arcade'),
    ('Arcade-Galaga_MiSTer', 'Arcade'),
    ('Arcade-Galaxian_MiSTer', 'Arcade'),
    ('Arcade-Gottlieb_MiSTer', 'Arcade'),
    ('Arcade-Kangaroo_MiSTer', 'Arcade'),
    ('Arcade-Konami82_MiSTer', 'Arcade'),
    ('Arcade-Kyugo_MiSTer', 'Arcade'),
    ('Arcade-LaserdiscGames_MiSTer', 'Arcade'),
    ('Arcade-Nintendo_MiSTer', 'Arcade'),
    ('Arcade-Pacman_MiSTer', 'Arcade'),
    ('Arcade-PolePosition_MiSTer', 'Arcade'),
    ('Arcade-Qix_MiSTer', 'Arcade'),
    ('Arcade-SegaG80_MiSTer', 'Arcade'),
    ('Arcade-SegaSystem1-2_MiSTer', 'Arcade'),
    ('Arcade-SNK6502_MiSTer', 'Arcade'),
    ('Arcade-SpaceInvaders_MiSTer', 'Arcade'),
    ('Arcade-Universal_MiSTer', 'Arcade'),
    ('Arcade-UPLFramebuffer_MiSTer', 'Arcade'),
    ('Arcade-Vastar_MiSTer', 'Arcade'),
    ('Arcade-Williams_MiSTer', 'Arcade'),
]

LAUNCHER_EXTS = ('.mgl', '.mra')
# newest <Core>_yyyymmdd.rbf; cores still in development ship <Core>_TestBuild.rbf instead
RBF_RE = re.compile(r'^.+_(?P<date>\d{8}|TestBuild)\.rbf$')


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
    sha = api(f'/repos/{full}/commits/HEAD')['sha']   # HEAD = default branch
    tree = api(f'/repos/{full}/git/trees/{sha}?recursive=1')
    if tree.get('truncated'):
        sys.exit(f'{full}: git tree truncated, cannot list releases/ reliably')

    files = [e['path'] for e in tree['tree']
             if e['type'] == 'blob' and e['path'].startswith('releases/')]

    def url(path):
        return f'https://raw.githubusercontent.com/{full}/{sha}/{urllib.parse.quote(path)}'

    rbfs = [(m.group('date'), p) for p in files
            if (m := RBF_RE.match(p[len('releases/'):]))]
    dated = [r for r in rbfs if r[0] != 'TestBuild']
    if not rbfs:
        sys.exit(f'{full}: no <Core>_yyyymmdd.rbf or <Core>_TestBuild.rbf in releases/')
    _, rbf_path = max(dated) if dated else rbfs[0]

    launchers = [p for p in sorted(files) if p.lower().endswith(LAUNCHER_EXTS)]

    # installed name drops the <Category>- prefix: InteractiveFiction-Frotz_20261022.rbf -> Frotz_20261022.rbf
    rbf_name = os.path.basename(rbf_path)
    if rbf_name.startswith(f'{category}-'):
        rbf_name = rbf_name[len(category) + 1:]
    # Main_MiSTer resolves an MRA's rbf in <first _Folder>/cores = _RodimusCores/cores (HW-confirmed with VCR)
    uses_mra = any(p.lower().endswith('.mra') for p in launchers)
    cores_dir = f'{ROOT}/cores' if uses_mra else f'{ROOT}/_{category}/cores'
    entries = [(f'{cores_dir}/{rbf_name}', url(rbf_path))]
    entries += [(f'{ROOT}/_{category}/{p[len("releases/"):]}', url(p)) for p in launchers]

    print(f'{full} @ {sha[:10]}: {cores_dir}/{rbf_name} + {len(launchers)} launchers', file=sys.stderr)
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

    # several repos share _RodimusCores/_Arcade/: a path clash would silently drop a file
    seen = {}
    for path, url in entries:
        if path.lower() in seen:
            sys.exit(f'path clash: {path}\n  {seen[path.lower()]}\n  {url}')
        seen[path.lower()] = url

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
