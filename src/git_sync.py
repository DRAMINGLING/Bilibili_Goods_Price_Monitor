"""Git persistence with finite retry and semantic JSON-record merging."""
from __future__ import annotations
import subprocess
from pathlib import Path
from src.storage import HISTORY_FILE, cleanup_old_history, load_price_history, merge_price_records, save_price_history
from src.visualization import generate_visualization

TRACKED = (HISTORY_FILE, Path("docs/price_history.json"), Path("docs/index.html"))

def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], check=False, text=True, capture_output=True)

def current_branch() -> str:
    result = run_git("branch", "--show-current")
    if result.returncode or not result.stdout.strip(): raise RuntimeError("无法确定当前 Git branch")
    return result.stdout.strip()

def sync_before_write(branch: str) -> None:
    for command in (("fetch", "origin"), ("pull", "--rebase", "origin", branch)):
        result = run_git(*command)
        if result.returncode: raise RuntimeError(f"git {' '.join(command)} 失败：{result.stderr}")

def commit_and_push(max_attempts: int = 3) -> bool:
    branch = current_branch()
    for attempt in range(max_attempts):
        run_git("add", *(str(path) for path in TRACKED))
        if run_git("diff", "--cached", "--quiet").returncode == 0: return True
        committed = run_git("commit", "-m", "chore: update price history")
        if committed.returncode: raise RuntimeError(committed.stderr)
        if run_git("push", "origin", branch).returncode == 0: return True
        # Preserve our raw records, replace the rejected commit with remote state,
        # then regenerate derived files from remote + local observations.
        local_records = load_price_history()
        sync = run_git("fetch", "origin")
        if sync.returncode: raise RuntimeError(sync.stderr)
        if run_git("reset", "--hard", f"origin/{branch}").returncode: raise RuntimeError("无法重置到远程最新状态")
        save_price_history(cleanup_old_history(merge_price_records(load_price_history(), local_records)))
        generate_visualization()
    raise RuntimeError(f"git push 在 {max_attempts} 次尝试后仍失败")


def main() -> None:
    """Commit generated history and retry rejected pushes at most three times."""
    commit_and_push()


if __name__ == "__main__":
    main()
