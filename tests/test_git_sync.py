from subprocess import CompletedProcess

import pytest

from src import git_sync


def result(*args: str, code: int = 0) -> CompletedProcess[str]:
    return CompletedProcess(["git", *args], code, stdout="work\n" if args == ("branch", "--show-current") else "", stderr="bad" if code else "")


def test_push_rejection_rebases_merges_and_retries(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    calls: list[tuple[str, ...]] = []
    responses = [result("branch", "--show-current"), result("add"), result("diff", "--cached", "--quiet", code=1), result("commit"), result("push", code=1), result("pull"), result("add"), result("commit"), result("push")]
    monkeypatch.setattr(git_sync, "run_git", lambda *args: (calls.append(args), responses.pop(0))[1])
    monkeypatch.setattr(git_sync, "load_price_history", lambda: [])
    monkeypatch.setattr(git_sync, "save_price_history", lambda records: None)
    assert git_sync.commit_and_push() is True
    assert ("pull", "--rebase", "origin", "work") in calls
    assert not any(call[:2] == ("reset", "--hard") for call in calls)


def test_push_fails_after_three_attempts(monkeypatch) -> None:
    monkeypatch.setattr(git_sync, "current_branch", lambda: "work")
    monkeypatch.setattr(git_sync, "run_git", lambda *args: result(*args, code=1 if args[0] in {"diff", "push"} else 0))
    monkeypatch.setattr(git_sync, "load_price_history", lambda: [])
    monkeypatch.setattr(git_sync, "save_price_history", lambda records: None)
    with pytest.raises(RuntimeError, match="3 次"):
        git_sync.commit_and_push()
