#!/usr/bin/env python3
"""git_guard: block destructive git, repository destruction, and writes to
protected or enforcement-owned paths — including through wrappers, command
chaining, quoting, env-prefixes, and shell redirection.

Detection is segment- and basename-aware: a command is split on shell
separators (`raw_segments`), env-assignments and wrappers (env/nice/bash -c/...)
are peeled (`peel`), and the program is matched by basename (`_prog`) so
`cd x && /usr/bin/git.exe reset --hard` is caught the same as `git reset --hard`.

Path policy: shell writes to `openspec/specs/` and `openspec/changes/archive/`
BLOCK; file-tool (WriteFile/Edit) writes to `openspec/specs/` are intentionally
ALLOWED here — the create-once bootstrap rule for them lives in
`gate_spec_bootstrap`, whose router route must stay `safety_critical: true` to
remain fail-closed. `.gigacode/**` self-protect blocks on both channels; writes
to PROTECTED_PATHS (CI/secrets/infra) ASK.

This gate is self-contained (it does not import _lib) and runs on the
safety-critical PreToolUse Bash/Shell and WriteFile/Edit routes.
"""
import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys

PROTECTED_BRANCHES = [
    "main", "master", "develop", "development", "release", "release/*",
    "hotfix/*", "production", "prod", "staging", "uat",
]
# Writes here require explicit confirmation (ASK). `**/...` variants catch the
# path nested under a subdirectory (fnmatch does not cross '/' without '**').
PROTECTED_PATHS = [
    "**/.github/workflows/**", ".github/workflows/**", ".gitlab-ci.yml",
    "**/Jenkinsfile", "Jenkinsfile", "ci/**", "**/ci/**", "deploy/**",
    "deployment/**", "k8s/**", "helm/**", "terraform/**", "**/terraform/**",
    "infra/**", "**/infra/**", ".env", ".env.*", "**/.env", "**/.env.*",
    "secrets/**", "**/secrets/**", "config/prod/**", "config/production/**",
    "config/staging/**", "config/uat/**",
]
# Enforcement-owned paths: writes here BLOCK (fail-closed).
SELF_PROTECT = [".gigacode/**", ".gigacode"]
# specs/ blocked on the shell channel only; file-tool writes are governed by gate_spec_bootstrap (create-once).
OPENSPEC_ARCHIVE_RE=re.compile(r"(^|/)openspec/changes/archive/",re.IGNORECASE)
OPENSPEC_SPECS_RE=re.compile(r"(^|/)openspec/specs/",re.IGNORECASE)

# Wrappers that prefix another command (the real command is their tail).
PREFIX_WRAPPERS = {"env", "nice", "ionice", "time", "stdbuf", "nohup",
                   "sudo", "doas", "timeout", "xargs"}
# Wrapper short/long flags that consume a separate WORD value (e.g. `sudo -u
# root`, `env -u NAME`). Numeric values (`nice -n 10`, `timeout 30`) are caught
# generically by the isdigit() skip in peel(), so only word-valued flags are
# listed here to avoid swallowing the real command after a boolean flag.
WRAPPER_VALUE_FLAGS = {"-u", "-g", "-U", "--user", "--group"}
# Wrappers that take the command as a -c / -Command / /c string argument.
DASH_C_WRAPPERS = {"bash", "sh", "zsh", "dash", "ash", "ksh",
                   "cmd", "command", "powershell", "pwsh"}
# Non-git verbs that delete; flagged when they target the .git repo.
DESTRUCTIVE_VERBS = {"rm", "rmdir", "del", "erase", "remove-item", "ri", "rd",
                     "truncate", "shred"}
# Verbs whose final positional argument is a write destination.
WRITE_VERBS = {"cp", "mv", "copy", "move", "copy-item", "cpi", "move-item",
               "mi", "tee", "install", "rename-item", "rni"}
ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# Global git flags that consume a following value token (git -C <path> ...).
GIT_GLOBAL_VALUE_FLAGS = {"-c", "-C", "--git-dir", "--work-tree", "--namespace",
                          "--super-prefix", "--exec-path", "--config-env",
                          "--attr-source", "--list-cmds"}
# git subcommands that are inherently irreversible / history-destroying.
# (reflog and gc are handled with action/flag granularity in git_destructive so
# read-only `git reflog show` and routine `git gc --auto` are not blocked.)
DESTRUCTIVE_SUBCMDS = {"update-ref", "filter-branch", "filter-repo"}


def run_git(args):
    try:
        r = subprocess.run(["git"] + args, cwd=os.getcwd(), text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    except FileNotFoundError:
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def current_branch():
    return run_git(["branch", "--show-current"])


def is_protected_branch(branch):
    return bool(branch) and any(fnmatch.fnmatch(branch, p) for p in PROTECTED_BRANCHES)


def command_from_event(event):
    for key in ("command", "tool_input", "input"):
        v = event.get(key)
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            cmd = v.get("command") or v.get("cmd")
            if isinstance(cmd, str):
                return cmd
    return ""


def _norm(path):
    """Forward-slash, normalized, ./-stripped — collapses //, /./, and .. so a
    path cannot dodge the matchers by spelling itself differently."""
    p = str(path).replace("\\", "/")
    p = os.path.normpath(p).replace("\\", "/")
    return p[2:] if p.startswith("./") else p


def path_from_event(event):
    # Deliberately a self-contained copy, not _lib.path_from_event: this one
    # additionally normpath-canonicalizes via _norm (traversal defense). The
    # extracted key set is kept in sync with _lib so neither channel can be
    # addressed through a field the other guards — notebook_path included so a
    # NotebookEdit write to a protected path is caught on the file-tool channel.
    for key in ("path", "file_path", "filename", "notebook_path"):
        v = event.get(key)
        if isinstance(v, str):
            return _norm(v)
    ti = event.get("tool_input")
    if isinstance(ti, dict):
        for key in ("path", "file_path", "filename", "notebook_path"):
            v = ti.get(key)
            if isinstance(v, str):
                return _norm(v)
    return ""


def protected_path(path):
    if not path:
        return False
    return any(fnmatch.fnmatch(_norm(path), pat) for pat in PROTECTED_PATHS)


def _sq(tok):
    """Strip one layer of matching surrounding quotes."""
    if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in "\"'":
        return tok[1:-1]
    return tok


def _prog(tok):
    """Program identity by basename, lowercased, .exe-stripped — so git.exe,
    /usr/bin/git and "git" all resolve to 'git'."""
    base = os.path.basename(_sq(tok).replace("\\", "/")).lower()
    return base[:-4] if base.endswith(".exe") else base


def _is_dash_c(tok):
    """True for a -c / -ce / -lc / -Command / /c 'run this string' flag — i.e.
    a short-flag cluster containing 'c', or the long/cmd spellings."""
    t = tok.lower()
    return t in ("-command", "/c") or bool(re.match(r"^-[a-z]*c", t))


def _tokenize(s):
    # posix=True removes quotes during tokenization (matching the real shell),
    # so quoted flags like "--hard" are compared as --hard, not '"--hard"'.
    try:
        return shlex.split(s, posix=True)
    except ValueError:
        return [_sq(t) for t in s.split()]


def raw_segments(command):
    """Split a command string into segments on shell separators (; && || | &
    newline), honoring quotes so a separator inside a quoted string does not
    split. Quote-aware at the raw-string level because shlex keeps `;`/`&&`
    glued to adjacent tokens."""
    parts, cur = [], []
    in_s = in_d = False
    i = 0
    while i < len(command):
        c = command[i]
        if c == "'" and not in_d:
            in_s = not in_s
            cur.append(c)
            i += 1
            continue
        if c == '"' and not in_s:
            in_d = not in_d
            cur.append(c)
            i += 1
            continue
        if not in_s and not in_d:
            if command[i:i + 2] in ("&&", "||"):
                parts.append("".join(cur).strip())
                cur = []
                i += 2
                continue
            if c in (";", "|", "&", "\n"):
                parts.append("".join(cur).strip())
                cur = []
                i += 1
                continue
        cur.append(c)
        i += 1
    parts.append("".join(cur).strip())
    return [p for p in parts if p]


def peel(tokens):
    """Strip leading env-assignments and wrappers from a token list and return
    the real command(s) as a list of leaf token-lists. A `-c`/`/c` wrapper's
    argument is re-parsed (it may itself contain separators)."""
    i = 0
    while i < len(tokens):
        tok = tokens[i].strip("()")
        if not tok:
            i += 1
            continue
        if ENV_ASSIGN_RE.match(tok):  # VAR=val prefix
            i += 1
            continue
        prog = _prog(tok)
        if prog in PREFIX_WRAPPERS:  # env / nice / sudo / timeout ... drop wrapper + flags/values
            i += 1
            while i < len(tokens):
                t = tokens[i]
                if t.startswith("-"):
                    i += 1
                    # skip a value belonging to this flag: a word value of a
                    # known value-flag (`sudo -u root`) or any numeric value
                    # (`nice -n 10`, `stdbuf -o 0`)
                    if (i < len(tokens) and not tokens[i].startswith("-")
                            and (t.lower() in WRAPPER_VALUE_FLAGS or tokens[i].isdigit())):
                        i += 1
                elif t.isdigit():  # positional numeric value, e.g. `timeout 30 ...`
                    i += 1
                else:
                    break  # first real command token
            continue
        if prog in DASH_C_WRAPPERS:  # bash -c "..." / bash -ce "..." / cmd /c ...
            k = i + 1
            while k < len(tokens) and not _is_dash_c(tokens[k]):
                k += 1
            rest = tokens[k + 1:] if k < len(tokens) else []
            # No -c found (e.g. `bash script.sh`): the command is in a file we
            # cannot inspect here, so peel yields nothing and the write is left
            # to the file-path gates.
            if len(rest) == 1 and " " in rest[0]:
                return to_leaves(rest[0])      # quoted single-string command
            inner = " ".join(rest)
            return to_leaves(inner) if inner else []
        break
    leaf = [t.strip("()") for t in tokens[i:] if t.strip("()")]
    return [leaf] if leaf else []


def to_leaves(command):
    """Full pipeline: a command string -> list of peeled leaf token-lists."""
    leaves = []
    for seg in raw_segments(command):
        leaves.extend(peel(_tokenize(seg)))
    return leaves


def git_sub_idx(leaf):
    """Index of the git subcommand in a leaf whose [0] is already a git program,
    skipping global value-flags like `-C <path>` / `-c k=v`."""
    i = 1
    while i < len(leaf):
        tok = leaf[i]
        if not tok.startswith("-"):
            return i
        if tok in GIT_GLOBAL_VALUE_FLAGS and "=" not in tok:
            i += 2
        else:
            i += 1
    return -1


def git_destructive(sub, rest):
    """Return a block reason for a destructive git subcommand, else ''."""
    if sub == "reset" and "--hard" in rest:
        return "Blocked `git reset --hard`."
    if sub == "clean":
        combined = "".join(t.lstrip("-") for t in rest if t.startswith("-"))
        # -n (dry-run) overrides force: previewing what -f would delete is safe.
        if "f" in combined and "n" not in combined:
            return "Blocked destructive `git clean -f`."
    if sub == "push":
        if any(t == "-f" or t.startswith("--force") for t in rest):
            return "Blocked force push."
        if "--delete" in rest or "--mirror" in rest:
            return "Blocked remote ref deletion/mirror push."
        # +ref / +src:dst = force-update refspec; :ref = remote ref deletion.
        if any(re.match(r"^\+[^\s]+$", t) or re.match(r"^:[^:\s]+$", t) for t in rest):
            return "Blocked force/delete by refspec."
    if sub == "branch" and any(t in ("-d", "-D", "--delete") for t in rest):
        return "Blocked local branch deletion."
    if sub == "remote" and rest[:1] == ["set-url"]:
        return "Blocked remote URL change."
    if sub == "reflog" and rest[:1] in (["expire"], ["delete"], ["drop"]):
        return f"Blocked potentially irreversible `git reflog {rest[0]}`."
    if sub == "gc" and any(t.startswith("--prune") and t != "--prune=never" for t in rest):
        return "Blocked `git gc --prune` (drops dangling-commit recovery)."
    if sub in DESTRUCTIVE_SUBCMDS:
        return f"Blocked potentially irreversible `git {sub}`."
    if sub == "checkout" and "--" in rest:
        return "Blocked `git checkout --` (discards working-tree edits)."
    if sub == "restore" and "--worktree" in rest:
        return "Blocked `git restore --worktree`."
    if sub == "worktree" and rest[:1] == ["remove"]:
        return "Blocked `git worktree remove`."
    if sub == "stash" and rest[:1] == ["clear"]:
        return "Blocked `git stash clear`."
    return ""


def classify_path(path,shell=False):
    """'block' for enforcement/openspec-truth paths, 'ask' for protected, else ''."""
    p=_norm(path)
    if any(fnmatch.fnmatch(p,pat) or p==pat.rstrip("/*") for pat in SELF_PROTECT): return "block"
    if OPENSPEC_ARCHIVE_RE.search(p): return "block"
    if shell and OPENSPEC_SPECS_RE.search(p): return "block"
    if any(fnmatch.fnmatch(p,pat) for pat in PROTECTED_PATHS): return "ask"
    return ""


def write_targets(tokens):
    """Paths a segment writes to: `>` / `>>` redirection targets and the
    destination of a copy/move/tee verb."""
    targets, i = [], 0
    prog = _prog(tokens[0]) if tokens else ""
    while i < len(tokens):
        t = tokens[i]
        if t in (">", ">>") and i + 1 < len(tokens):
            targets.append(_sq(tokens[i + 1]))
            i += 2
            continue
        if t.startswith(">") and len(t) > 1:  # `>file` glued
            targets.append(_sq(t.lstrip(">")))
            i += 1
            continue
        i += 1
    if prog in WRITE_VERBS:
        args = [a for a in tokens[1:] if not a.startswith("-")]
        if args:
            targets.append(_sq(args[-1]))  # destination = last positional
    return [_norm(p) for p in targets if p]


def _git_in_args(leaf):
    """True if a non-git destructive verb targets the .git repository."""
    for t in leaf[1:]:
        n = _norm(_sq(t))
        if n == ".git" or n.startswith(".git/"):
            return True
    return False


def inspect_command(command):
    """Return (decision, reason) for a shell command: 'block'/'ask'/''."""
    for leaf in to_leaves(command):
        if not leaf:
            continue
        prog = _prog(leaf[0])
        if prog == "git":
            idx = git_sub_idx(leaf)
            if idx >= 0:
                sub = _sq(leaf[idx]).lower()
                rest = [_sq(t).lower() for t in leaf[idx + 1:]]
                reason = git_destructive(sub, rest)
                if reason:
                    return "block", reason
        elif prog in DESTRUCTIVE_VERBS:
            if _git_in_args(leaf):
                return "block", "Blocked deletion of the git repository (.git)."
        worst = ""
        for tgt in write_targets(leaf):
            c=classify_path(tgt,shell=True)
            if c == "block":
                return "block", f"Blocked shell write to enforcement/openspec path '{tgt}'."
            if c == "ask":
                worst = "ask"
        if worst == "ask":
            return "ask", "Shell write to a protected path requires explicit confirmation."
    return "", ""


def is_branch_write(command):
    """True if any segment is a git commit/push/rebase (for protected-branch check)."""
    for leaf in to_leaves(command.lower()):
        if not leaf:
            continue
        if _prog(leaf[0]) == "git":
            idx = git_sub_idx(leaf)
            if idx >= 0 and leaf[idx].lower() in ("commit", "push", "rebase"):
                return True
    return False


def run(event):
    """Gate contract: event dict in, decision dict out."""
    command = command_from_event(event)
    file_path = path_from_event(event)
    if command:
        decision, reason = inspect_command(command)
        if decision == "block":
            return {"decision": "block", "reason": reason + " Use an explicit human-approved recovery workflow."}
        branch = current_branch()
        if is_protected_branch(branch) and is_branch_write(command):
            return {"decision": "block", "reason": f"Blocked git write on protected branch '{branch}'. Use a feature/bugfix branch."}
        if decision == "ask":
            return {"decision": "ask", "reason": reason}
    if file_path:
        cls = classify_path(file_path)
        if cls == "block":
            return {"decision": "block", "reason": f"Write to enforcement-owned path '{file_path}' is blocked. Edit enforcement files via an out-of-band human workflow."}
        if cls == "ask" or protected_path(file_path):
            return {"decision": "ask", "reason": f"Protected path '{file_path}' requires explicit confirmation with risk explanation."}
    return {"decision": "allow"}


def main():
    try:
        # utf-8-sig: PowerShell pipes may prepend a UTF-8 BOM that breaks json.load
        event = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", errors="replace"))
    except json.JSONDecodeError:
        print(json.dumps({"decision": "allow"}, ensure_ascii=False))
        return
    print(json.dumps(run(event), ensure_ascii=False))


if __name__ == "__main__":
    main()
