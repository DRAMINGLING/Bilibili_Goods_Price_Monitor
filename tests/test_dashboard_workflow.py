"""Exercise the workflow's actual shell steps against a local Git remote."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/sync-price-dashboard.yml'
STEPS = yaml.safe_load(WORKFLOW.read_text(encoding='utf-8'))['jobs']['sync-dashboard']['steps']
TARGET = 'personal_documents/Bilibili_Goods_Price_Monitor/data/price_history.json'


def git(cwd, *args):
    result = subprocess.run(['git', *args], cwd=cwd, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def write(repo, path, content):
    destination = repo / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding='utf-8')


def commit(repo, message):
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', message)


def shell_step(name, root, env):
    step = next(step for step in STEPS if step['name'] == name)
    bash = shutil.which('bash')
    if os.name == 'nt':
        bash = str(Path(shutil.which('git')).resolve().parents[1] / 'bin/bash.exe')
    return subprocess.run([bash, '-c', step['run']], cwd=root / step.get('working-directory', '.'),
                          env=env, text=True, capture_output=True)


@pytest.mark.parametrize('scenario', ['unchanged', 'normal', 'race', 'conflict'])
def test_dashboard_publish_with_shallow_sparse_checkout(tmp_path, monkeypatch, scenario):
    # Configure only child Git processes; do not change the developer's Git config.
    monkeypatch.setenv('GIT_CONFIG_COUNT', '2')
    monkeypatch.setenv('GIT_CONFIG_KEY_0', 'user.name')
    monkeypatch.setenv('GIT_CONFIG_VALUE_0', 'Test')
    monkeypatch.setenv('GIT_CONFIG_KEY_1', 'user.email')
    monkeypatch.setenv('GIT_CONFIG_VALUE_1', 'test@example.test')
    remote = tmp_path / 'remote.git'
    git(tmp_path, 'init', '--bare', '--initial-branch=main', str(remote))
    seed = tmp_path / 'seed'
    git(tmp_path, 'clone', remote.as_uri(), str(seed))
    write(seed, TARGET, 'old\n')
    write(seed, 'index.html', 'original page\n')
    commit(seed, 'initial')
    git(seed, 'push', 'origin', 'main')
    original = git(seed, 'rev-parse', 'HEAD')
    root = tmp_path / 'runner'
    root.mkdir()
    pages = root / 'pages-repo'
    git(root, 'clone', '--depth=1', '--no-checkout', remote.as_uri(), str(pages))
    checkout = next(step for step in STEPS if step['name'] == 'Checkout GitHub Pages repository')['with']
    pattern = checkout['sparse-checkout'].replace('${{ env.TARGET_DIRECTORY }}', str(Path(TARGET).parent.parent).replace('\\', '/')).strip()
    git(pages, 'sparse-checkout', 'set', '--no-cone', pattern)
    git(pages, 'checkout', 'main')
    assert git(pages, 'rev-parse', '--is-shallow-repository') == 'true'
    assert not (pages / 'index.html').exists()
    write(root, 'data/price_history.json', 'old\n' if scenario == 'unchanged' else 'new\n')
    env = dict(os.environ, TARGET_BRANCH='main', TARGET_DIRECTORY='personal_documents/Bilibili_Goods_Price_Monitor',
               GITHUB_OUTPUT=(root / 'outputs').as_posix())
    for name in ['Copy price history only', 'Commit dashboard update']:
        result = shell_step(name, root, env)
        assert result.returncode == 0, result.stderr
    outputs = dict(line.split('=', 1) for line in (root / 'outputs').read_text().splitlines())
    if scenario == 'unchanged':
        assert outputs['changed'] == 'false'
        assert git(pages, 'rev-parse', 'HEAD') == original
        return
    assert outputs['changed'] == 'true'
    env['PUBLISH_BASE'] = outputs['base']
    if scenario in ('race', 'conflict'):
        # More than one concurrent commit leaves the fetched tip disconnected in a depth-1 clone.
        for n in range(3):
            write(seed, 'index.html', f'concurrent page {n}\n')
            if scenario == 'conflict':
                write(seed, TARGET, f'remote data {n}\n')
            commit(seed, f'concurrent {n}')
        git(seed, 'push', 'origin', 'main')
    before_push = git(remote, 'rev-parse', 'main')
    result = shell_step('Push dashboard update', root, env)
    if scenario == 'conflict':
        assert result.returncode != 0
        assert git(remote, 'rev-parse', 'main') == before_push
        assert git(remote, 'show', f'main:{TARGET}') == 'remote data 2'
    else:
        assert result.returncode == 0, result.stderr
        assert git(remote, 'show', f'main:{TARGET}') == 'new'
        assert git(remote, 'show', 'main:index.html') == ('concurrent page 2' if scenario == 'race' else 'original page')
        assert git(remote, 'diff-tree', '--no-commit-id', '--name-only', '-r', 'main') == TARGET
        assert git(remote, 'rev-parse', 'main^') == before_push
