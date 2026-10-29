"""
Make a release: the data release the fetched stores are downloaded from, then the package.

Dev tool -- NOT part of the installed package. Run it from an up-to-date `main`:

1. Checks that every fetched store in the manifest `starsim_data/data/fetched.json` is
   downloaded from the data release given, and that the stores in `fetched/` match it.
2. Creates that data release with the stores as assets, unless it already exists (a data
   release is shared by every package version until a store changes), in which case it
   checks the assets are there.
3. Creates the release `v<version>`, with the version from `starsim_data/version.py` and
   the notes from its section of `CHANGELOG.md`. Publishing it triggers
   `.github/workflows/publish.yml`, which publishes the package to PyPI.

Each release also creates its git tag, on GitHub; `git fetch --tags` to get them.

Usage:

```bash
python scripts/publish.py data-2026.10 --dry-run   # check everything, create nothing
python scripts/publish.py data-2026.10
```
"""

import argparse
import hashlib
import json
import pathlib
import re
import subprocess

REPO     = pathlib.Path(__file__).resolve().parent.parent
FETCHED  = REPO / 'fetched'
MANIFEST = REPO / 'starsim_data' / 'data' / 'fetched.json'
GITHUB   = 'starsimhub/starsim_data'
BRANCH   = 'main'


def run(*args, check=True):
    """ Run a command in the repository and return its output """
    result = subprocess.run(args, cwd=REPO, capture_output=True, text=True)
    if check and result.returncode:
        raise RuntimeError(f'{" ".join(args)} failed:\n{result.stderr}')
    return result


def release_exists(tag):
    return run('gh', 'release', 'view', tag, '-R', GITHUB, check=False).returncode == 0


def check_branch():
    """ The local checkout is what gets released, so it must be `main` as it is on GitHub """
    run('git', 'fetch', 'origin', BRANCH)
    branch = run('git', 'branch', '--show-current').stdout.strip()
    if branch != BRANCH:
        raise RuntimeError(f'On branch {branch!r}; release from {BRANCH!r}')
    if run('git', 'status', '--porcelain', '--untracked-files=no').stdout.strip():
        raise RuntimeError('There are uncommitted changes')
    if run('git', 'rev-parse', 'HEAD').stdout != run('git', 'rev-parse', f'origin/{BRANCH}').stdout:
        raise RuntimeError(f'{BRANCH!r} is not the same as on GitHub; pull or push first')
    return


def check_stores(data_tag):
    """ Every store is downloaded from the data release, and fetched/ holds those bytes """
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    paths = []
    for name, entry in manifest.items():
        if f'/download/{data_tag}/' not in entry['url']:
            raise ValueError(f'{name} is downloaded from {entry["url"]}, not release {data_tag}; set RELEASE in scripts/build_hdf5.py')
        path = FETCHED / entry['store']
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError(f'{path} does not match the manifest')
        paths.append(path)
    return paths


def changelog_notes(version):
    """ This version's section of the changelog """
    text = (REPO / 'CHANGELOG.md').read_text(encoding='utf-8')
    match = re.search(rf'^## Version {re.escape(version)}\b.*?\n(.*?)(?=^## |\Z)', text, flags=re.M | re.S)
    if not match:
        raise ValueError(f'CHANGELOG.md has no section for {version}')
    return match[1].strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('data_tag', help='the data release the fetched stores are downloaded from, e.g. data-2026.10')
    parser.add_argument('--dry-run', action='store_true', help='check everything, but create nothing')
    args = parser.parse_args()
    data_tag = args.data_tag
    if not data_tag.startswith('data-'):
        parser.error(f'The data tag must start with "data-", not {data_tag!r}')

    version = re.search(r"__version__ = '(.+)'", (REPO / 'starsim_data' / 'version.py').read_text())[1]
    tag = f'v{version}'
    print(f'Releasing {tag} with data release {data_tag}')

    check_branch()
    paths = check_stores(data_tag)
    notes = changelog_notes(version)
    if release_exists(tag):
        raise RuntimeError(f'Release {tag} already exists; bump the version in starsim_data/version.py')

    if release_exists(data_tag):
        assets = json.loads(run('gh', 'release', 'view', data_tag, '-R', GITHUB, '--json', 'assets').stdout)['assets']
        missing = {path.name for path in paths} - {asset['name'] for asset in assets}
        if missing:
            raise RuntimeError(f'Release {data_tag} exists but lacks {sorted(missing)}')
        print(f'  {data_tag}: exists, with all {len(paths)} stores')
        data_cmd = None
    else:
        data_cmd = ['gh', 'release', 'create', data_tag, *map(str, paths), '-R', GITHUB, '--target', BRANCH,
                    '--latest=false', '--title', f'Data stores {data_tag.removeprefix("data-")}',
                    '--notes', 'The stores `fetch()` downloads; their checksums are in `starsim_data/data/fetched.json`.']
    cmd = ['gh', 'release', 'create', tag, '-R', GITHUB, '--target', BRANCH, '--title', tag, '--notes', notes]

    if args.dry_run:
        print('Checks passed. Would run:')
        for c in [data_cmd, cmd]:
            if c:
                print('  ' + ' '.join(c[:5]) + ' ...')
        return
    if data_cmd:
        run(*data_cmd)
        print(f'  {data_tag}: created, with {len(paths)} stores')
    run(*cmd)
    print(f'  {tag}: created; publishing to PyPI: https://github.com/{GITHUB}/actions/workflows/publish.yml')
    return


if __name__ == '__main__':
    main()
