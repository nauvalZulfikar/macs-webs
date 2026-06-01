"""Git-based artifact tracking: snapshot at stream start, diff at any point,
per-hunk revert via `git apply -R`."""
import re
import subprocess
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List


def _run(cwd: Path, *args: str, check: bool = False, input_text: Optional[str] = None) -> tuple[int, str, str]:
    """Run a git command. Returns (returncode, stdout, stderr)."""
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.returncode, proc.stdout, proc.stderr


def is_git_repo(project_path: str | Path) -> bool:
    p = Path(project_path)
    if not p.is_dir():
        return False
    rc, _, _ = _run(p, "rev-parse", "--git-dir")
    return rc == 0


def head_sha(project_path: str | Path) -> Optional[str]:
    p = Path(project_path)
    rc, out, _ = _run(p, "rev-parse", "HEAD")
    if rc != 0:
        return None
    return out.strip() or None


@dataclass
class HunkInfo:
    index: int
    header: str            # "@@ -10,3 +10,5 @@"
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: List[str]       # raw +/-/space lines (without trailing \n)
    patch_text: str        # the full hunk text inc. header


@dataclass
class FileDiff:
    path: str
    status: str            # 'modified' | 'added' | 'deleted' | 'renamed' | 'untracked'
    additions: int = 0
    deletions: int = 0
    hunks: List[HunkInfo] = field(default_factory=list)
    binary: bool = False
    old_path: Optional[str] = None  # set for renames


HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _parse_diff(diff_text: str) -> List[FileDiff]:
    out: List[FileDiff] = []
    cur: Optional[FileDiff] = None
    cur_hunk: Optional[HunkInfo] = None
    hunk_idx_in_file = 0
    lines = diff_text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("diff --git "):
            # close previous
            if cur and cur_hunk:
                cur.hunks.append(cur_hunk)
                cur_hunk = None
            if cur:
                out.append(cur)
            # parse paths
            parts = line.split(" ")
            a = parts[2][2:] if len(parts) >= 4 else ""
            b = parts[3][2:] if len(parts) >= 4 else ""
            cur = FileDiff(path=b or a, status="modified", old_path=(a if a != b else None))
            hunk_idx_in_file = 0
        elif cur is None:
            i += 1
            continue
        elif line.startswith("new file mode"):
            cur.status = "added"
        elif line.startswith("deleted file mode"):
            cur.status = "deleted"
        elif line.startswith("rename from "):
            cur.status = "renamed"
            cur.old_path = line[len("rename from "):]
        elif line.startswith("Binary files"):
            cur.binary = True
        elif line.startswith("@@"):
            # close previous hunk for this file
            if cur_hunk:
                cur.hunks.append(cur_hunk)
            m = HUNK_RE.match(line)
            if not m:
                i += 1
                continue
            os_, ol, ns, nl = m.groups()
            cur_hunk = HunkInfo(
                index=hunk_idx_in_file,
                header=line,
                old_start=int(os_),
                old_lines=int(ol or 1),
                new_start=int(ns),
                new_lines=int(nl or 1),
                lines=[],
                patch_text="",
            )
            hunk_idx_in_file += 1
            cur_hunk.patch_text = line + "\n"
        elif cur_hunk is not None:
            cur_hunk.lines.append(line)
            cur_hunk.patch_text += line + "\n"
            if line.startswith("+") and not line.startswith("+++"):
                cur.additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                cur.deletions += 1
        i += 1
    if cur and cur_hunk:
        cur.hunks.append(cur_hunk)
    if cur:
        out.append(cur)
    return out


def diff_since(project_path: str | Path, base_sha: Optional[str]) -> List[FileDiff]:
    """Return diff of tracked files since base_sha (or HEAD if base missing)."""
    p = Path(project_path)
    if not is_git_repo(p):
        return []
    # Tracked changes: compare base..working tree (no --cached so includes dirty)
    target = base_sha if base_sha else "HEAD"
    rc, out, err = _run(p, "diff", "--no-color", "--no-prefix", target)
    # --no-prefix doesn't add a/ b/ — but our parser expects diff --git form.
    # Use default prefix:
    rc, out, err = _run(p, "diff", "--no-color", target)
    files = _parse_diff(out) if rc == 0 else []
    # Untracked files: surface as 'untracked' entries
    rc2, ut_out, _ = _run(p, "ls-files", "--others", "--exclude-standard")
    if rc2 == 0:
        for f in ut_out.strip().split("\n"):
            if not f:
                continue
            full = p / f
            if full.is_file() and full.stat().st_size < 200_000:
                try:
                    content = full.read_text(errors="replace")
                    additions = content.count("\n") + 1
                except Exception:
                    additions = 0
                files.append(FileDiff(path=f, status="untracked", additions=additions))
    return files


def diff_as_dicts(files: List[FileDiff]) -> List[dict]:
    return [
        {
            **{k: v for k, v in asdict(f).items() if k != "hunks"},
            "hunks": [asdict(h) for h in f.hunks],
        }
        for f in files
    ]


def reject_hunks(project_path: str | Path, file_path: str, hunk_patches: List[str]) -> tuple[bool, str]:
    """Apply reverse on selected hunk patch texts. Each hunk patch must be a
    full unified diff (with --- /+++ headers). Returns (ok, message)."""
    p = Path(project_path)
    # Build a unified diff with --- /+++ headers for the single file
    header = f"--- a/{file_path}\n+++ b/{file_path}\n"
    body = "".join(hunk_patches)
    patch = header + body
    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False) as f:
        f.write(patch)
        patch_path = f.name
    try:
        rc, out, err = _run(p, "apply", "--reverse", "--whitespace=nowarn", patch_path)
        if rc != 0:
            # Try 3-way
            rc2, _, err2 = _run(p, "apply", "--reverse", "--3way", "--whitespace=nowarn", patch_path)
            if rc2 != 0:
                return False, (err + err2).strip()
        return True, "ok"
    finally:
        try:
            Path(patch_path).unlink()
        except Exception:
            pass


def stash_create(project_path: str | Path, message: str = "macs-checkpoint") -> Optional[str]:
    """Create a stash WITHOUT popping it from working tree. Returns SHA."""
    p = Path(project_path)
    if not is_git_repo(p):
        return None
    rc, _, _ = _run(p, "add", "-N", ".")  # include untracked in stash
    rc, out, err = _run(p, "stash", "create", "-u", message)
    sha = out.strip() or None
    if not sha:
        return None
    # Keep a ref so it's not GC'd
    _run(p, "update-ref", f"refs/macs/checkpoints/{sha[:12]}", sha)
    return sha


def stash_apply(project_path: str | Path, sha: str) -> tuple[bool, str]:
    p = Path(project_path)
    rc, out, err = _run(p, "stash", "apply", "--quiet", sha)
    if rc != 0:
        return False, err.strip()
    return True, "applied"


def list_changed_files(project_path: str | Path, base_sha: Optional[str]) -> list[str]:
    p = Path(project_path)
    if not is_git_repo(p):
        return []
    target = base_sha if base_sha else "HEAD"
    rc, out, _ = _run(p, "diff", "--name-only", target)
    files = out.strip().splitlines() if rc == 0 else []
    rc2, ut, _ = _run(p, "ls-files", "--others", "--exclude-standard")
    if rc2 == 0:
        files += [f for f in ut.strip().splitlines() if f]
    return files[:200]


def restore_file(project_path: str | Path, file_path: str) -> tuple[bool, str]:
    """Restore a tracked file to HEAD. For untracked files, delete."""
    p = Path(project_path)
    if (p / file_path).exists():
        rc, out, err = _run(p, "ls-files", "--error-unmatch", file_path)
        if rc != 0:
            # untracked → delete
            try:
                (p / file_path).unlink()
                return True, "untracked file deleted"
            except Exception as e:
                return False, str(e)
        rc2, _, err2 = _run(p, "checkout", "HEAD", "--", file_path)
        if rc2 != 0:
            return False, err2.strip()
        return True, "restored"
    return False, "file missing"
