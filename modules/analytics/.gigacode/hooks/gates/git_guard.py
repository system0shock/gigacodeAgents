#!/usr/bin/env python3
"""git_guard: block destructive git, repository destruction, and writes to
protected or enforcement-owned paths — including through wrappers, command
chaining, quoting, env-prefixes, and shell redirection.

Detection is segment- and basename-aware: a command is split on shell
separators (`raw_segments`), env-assignments and wrappers (env/nice/bash -c/...)
are peeled (`peel`), and the program is matched by basename (`_prog`) so
`cd x && /usr/bin/git.exe reset --hard` is caught the same as `git reset --hard`.

Path policy: writes to enforcement-owned paths (`.gigacode/**`) and openspec
truth BLOCK (fail-closed — the layer must not be editable by the agent it
constrains); writes to PROTECTED_PATHS (CI/secrets/infra) ASK.

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
import unicodedata

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
# Enforcement-owned paths and the .git repo: writes/deletes here BLOCK
# (fail-closed). Matched as a path COMPONENT anywhere in the (possibly absolute)
# path — a start-anchored fnmatch let an absolute path like F:/proj/.gigacode/...
# slip past, and Claude Code passes absolute file_path by default.
SELF_PROTECT_RE = re.compile(r"(^|/)\.gigacode(/|$)")
GIT_DIR_RE = re.compile(r"(^|/)\.git(/|$)")
# Loose variants for the defense-in-depth catch-all: match `.gigacode`/`.git`
# wherever they appear as a name (not followed by a word char, so `.gigacoderc`
# / `.gitignore` don't false-match), even through prefixes the component-anchored
# regexes above would miss. Erring toward block is correct for a backstop.
SELF_PROTECT_LOOSE = re.compile(r"\.gigacode(?![A-Za-z0-9_])", re.IGNORECASE)
GIT_DIR_LOOSE = re.compile(r"\.git(?![A-Za-z0-9_])", re.IGNORECASE)
# Analytics create-once split: openspec/specs is blocked on the SHELL channel
# only — file-tool (WriteFile/Edit/NotebookEdit) writes to specs are ALLOWED here
# and governed by gate_spec_bootstrap (create-once, fail-closed on its own route).
# openspec/changes/archive is blocked on BOTH channels.
OPENSPEC_ARCHIVE_RE = re.compile(r"(^|/)openspec/changes/archive/", re.IGNORECASE)
OPENSPEC_SPECS_RE = re.compile(r"(^|/)openspec/specs/", re.IGNORECASE)

# Wrappers that prefix another command (the real command is their tail).
# `command`/`exec`/`builtin` run their argument as a program, so they are
# transparent prefixes, NOT -c string wrappers — listing `command` under
# DASH_C_WRAPPERS made `command git reset --hard` a universal kill-switch.
PREFIX_WRAPPERS = {"env", "nice", "ionice", "time", "stdbuf", "nohup",
                   "sudo", "doas", "timeout", "xargs", "command", "exec",
                   "builtin"}
# Wrapper short/long flags that consume a separate WORD value (e.g. `sudo -u
# root`, `env -u NAME`). Numeric/duration values (`nice -n 10`, `timeout 5s`) are
# caught generically by the _is_duration() skip in peel(); WRAPPER_VALUE_OPTS
# below adds the per-wrapper word-valued options so the real command after them is
# still reached (`timeout -s TERM 5 git …`, `xargs -a FILE git …`).
WRAPPER_VALUE_FLAGS = {"-u", "-g", "-U", "--user", "--group"}
# Per-wrapper options that consume a following WORD value. Enumerated from the
# tools' docs so a value (signal/file/delim/...) is not mistaken for the command.
WRAPPER_VALUE_OPTS = {
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "xargs": {"-a", "--arg-file", "-E", "-e", "--eof", "-I", "-i", "--replace",
              "-L", "-l", "--max-lines", "-n", "--max-args", "-P", "--max-procs",
              "-s", "--max-chars", "-d", "--delimiter", "--process-slot-var"},
    "nice": {"-n", "--adjustment"},
    "ionice": {"-c", "--class", "-n", "--classdata", "-p", "--pid"},
    "stdbuf": {"-i", "--input", "-o", "--output", "-e", "--error"},
    "env": {"-u", "--unset", "-S", "--split-string", "-C", "--chdir"},
    "sudo": {"-u", "--user", "-g", "--group", "-U", "-C", "--close-from", "-h",
             "--host", "-p", "--prompt", "-r", "--role", "-t", "--type",
             "-T", "--command-timeout"},
    "doas": {"-u", "-C", "-a"},
    "time": {"-o", "--output", "-f", "--format"},
}
_DURATION_RE = re.compile(r"^\d+(\.\d+)?[smhd]?$")
# Wrappers that take the command as a -c / -Command / /c string argument.
DASH_C_WRAPPERS = {"bash", "sh", "zsh", "dash", "ash", "ksh",
                   "cmd", "powershell", "pwsh"}
# `eval ...` concatenates its arguments and runs the result as a command.
EVAL_WRAPPERS = {"eval"}
# Shell control / grouping keywords that introduce a command list. They are
# transparent prefixes: the real command follows (`then git reset --hard`,
# `{ git reset --hard; }`, `do git reset --hard`). Matched as exact bare tokens
# (never paths), so a program literally named `do` is not skipped.
SHELL_CONTROL = {"if", "then", "else", "elif", "fi", "do", "done", "while",
                 "until", "for", "in", "case", "esac", "select", "{", "}", "!"}
# Non-git verbs that delete; flagged when they target a protected path. `find`
# is delete-guarded in _destructive_target (only -delete / -exec rm counts).
DESTRUCTIVE_VERBS = {"rm", "rmdir", "del", "erase", "remove-item", "ri", "rd",
                     "truncate", "shred", "find"}
# Verbs whose final positional argument is a write destination.
WRITE_VERBS = {"cp", "mv", "copy", "move", "copy-item", "cpi", "move-item",
               "mi", "tee", "install", "rename-item", "rni"}
# Move/rename verbs REMOVE the source from its location, so moving an
# enforcement-owned file OUT of the protected tree is destructive — every path
# operand (sources AND destination) must be classified, not just the dest.
# Copy verbs are excluded: copying reads the source, it does not remove it.
MOVE_VERBS = {"mv", "move", "move-item", "mi", "rename-item", "rni"}
# GNU coreutils verbs that accept `-t DIR` / `--target-directory[=DIR]`: every
# source operand is written INTO DIR, so DIR is the write destination.
GNU_TARGET_DIR_VERBS = {"cp", "mv", "install"}
# PowerShell write cmdlets: destination is -Path/-FilePath/-LiteralPath or the
# FIRST positional (NOT the last) — Windows is the primary platform.
PS_WRITE_VERBS = {"set-content", "add-content", "out-file", "tee-object",
                  "sc", "ac"}
# Writer programs with a non-positional / in-place destination.
WRITER_PROGS = {"dd", "sed", "perl", "truncate", "ed"}
# Read-only programs: the defense-in-depth catch-all skips these, so reading or
# inspecting an enforcement file (cat/grep/ls/Get-Content ...) is never blocked.
# Programs that can WRITE (cp/mv/touch/mkdir/ln/chmod/tar/dd/sed/python/...) are
# deliberately absent — naming a protected path with one of them is suspect.
READ_ONLY_PROGS = {
    "cat", "bat", "tac", "nl", "less", "more", "head", "tail", "view",
    "grep", "egrep", "fgrep", "rg", "ag", "ack", "git-grep",
    "ls", "dir", "tree", "stat", "file", "wc", "du", "df", "realpath",
    "find",  # delete form (-delete / -exec rm) handled by _destructive_target
    "readlink", "basename", "dirname", "cksum", "md5sum", "sha1sum",
    "sha256sum", "diff", "cmp", "comm", "sort", "uniq", "cut", "column",
    "echo", "printf", "true", "false", "test", "[", "which", "type",
    "whereis", "whatis", "man", "pwd", "cd", "pushd", "popd", "date",
    # PowerShell readers / navigation
    "get-content", "gc", "get-childitem", "gci", "select-string", "sls",
    "get-item", "gi", "test-path", "resolve-path", "get-location", "gl",
    "set-location", "sl", "push-location", "pop-location", "format-hex",
    "measure-object", "write-output", "write-host",
}
ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# A redirection token: optional fd digits, > >> < or <<, optional clobber |, and
# an optional glued operand.  e.g.  >  >>  1>  2>>  >|  1>file  <  <file
REDIR_RE = re.compile(r"^(\d*)(>{1,2}|<{1,2})(\|?)(.*)$")
# Operator glued after a word (`arg>file`, `arg2>>file`): shlex keeps it as one
# token because it is not a real shell. Capture the operand as a write target.
EMBED_REDIR_RE = re.compile(r"(?P<op>>{1,2})(?P<clobber>\|?)(?P<operand>[^>]*)$")
# Zero-width / format chars stripped before tokenizing (NBSP and other Zs spaces
# are folded to a normal space by NFKC + the Zs check in _normalize_ws).
ZERO_WIDTH = {"​", "‌", "‍", "⁠", "﻿"}
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


def _normalize_ws(s):
    """NFKC-normalize, drop zero-width/format chars, and fold every Unicode
    space (Zs) to a plain space. Closes the NBSP / zero-width separator bypass
    (git<NBSP>reset<NBSP>--hard) on PowerShell, which splits on those."""
    s = unicodedata.normalize("NFKC", s)
    out = []
    for ch in s:
        if ch in ZERO_WIDTH:
            continue
        out.append(" " if unicodedata.category(ch) == "Zs" else ch)
    return "".join(out)


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
                # `>|` (clobber) and `>&` (fd-dup) are redirections, not pipes —
                # don't split, or the redirect target lands in its own segment.
                if c in ("|", "&") and "".join(cur).rstrip().endswith(">"):
                    cur.append(c)
                    i += 1
                    continue
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
        raw = tokens[i]                 # function headers are matched pre-strip
        tok = raw.strip("()")
        if not tok:
            i += 1
            continue
        if ENV_ASSIGN_RE.match(tok):  # VAR=val prefix
            i += 1
            continue
        if tok in SHELL_CONTROL:  # then/do/else/{/... — the command follows
            i += 1
            continue
        if tok == "function":  # `function name { body; }` — skip keyword + name
            i += 1
            if i < len(tokens) and re.match(r"^[A-Za-z_][\w-]*(\(\))?[\{\(]?$", tokens[i]):
                i += 1
            continue
        # function definition header — the body runs on invocation, so inspect it.
        # Matched on the RAW token (before paren-strip) so a `{`/`(` body marker
        # isn't lost. Forms: `name()`, `name(){`, `name()(`, or `name` + `()`.
        if re.match(r"^([A-Za-z_][\w-]*)?\(\)[\{\(]?$", raw):
            i += 1
            continue
        if (re.match(r"^[A-Za-z_][\w-]*$", tok) and i + 1 < len(tokens)
                and re.match(r"^\(\)[\{\(]?$", tokens[i + 1].strip())):
            i += 2
            continue
        prog = _prog(tok)
        if prog in PREFIX_WRAPPERS:  # env / nice / sudo / timeout ... drop wrapper + flags/values
            value_opts = WRAPPER_VALUE_OPTS.get(prog, set()) | WRAPPER_VALUE_FLAGS
            i += 1
            while i < len(tokens):
                t = tokens[i]
                if t.startswith("-"):
                    base = t.split("=", 1)[0].lower()
                    i += 1
                    # consume a separate WORD value of a known value-option
                    # (`timeout -s TERM`, `xargs -a FILE`) — glued `--opt=val`
                    # carries its own value, and a value-less boolean is left alone.
                    if ("=" not in t and base in value_opts
                            and i < len(tokens) and not tokens[i].startswith("-")):
                        i += 1
                elif _DURATION_RE.match(t):  # numeric/duration positional (`timeout 5s`)
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
        if prog in EVAL_WRAPPERS:  # eval "cmd" / eval cmd — re-parse the rest
            inner = " ".join(_sq(t) for t in tokens[i + 1:])
            return to_leaves(inner) if inner else []
        break
    leaf = [t.strip("()") for t in tokens[i:] if t.strip("()")]
    # A single quoted blob left by a wrapper that took the command as one WORD
    # (e.g. `env -S 'git reset --hard'`): re-tokenize so it is inspected.
    if len(leaf) == 1 and " " in leaf[0]:
        return to_leaves(leaf[0])
    return [leaf] if leaf else []


def extract_substitutions(command):
    """Inner command strings of $(...), `...`, and process substitutions
    <(...) / >(...), so a destructive command hidden inside one
    (x=$(git reset --hard), cat <(git reset --hard)) is still inspected."""
    inners = []
    i = 0
    while i < len(command) - 1:
        # $(...) command-substitution and <(...) / >(...) process-substitution all
        # run their inner command in a subshell.
        if (command[i] == "$" and command[i + 1] == "(") or (
                command[i] in "<>" and command[i + 1] == "("):
            depth, j = 1, i + 2
            while j < len(command) and depth:
                if command[j] == "(":
                    depth += 1
                elif command[j] == ")":
                    depth -= 1
                j += 1
            inners.append(command[i + 2:j - 1])
            i = j
        else:
            i += 1
    parts = command.split("`")
    for k in range(1, len(parts), 2):  # odd segments are backtick-quoted
        inners.append(parts[k])
    return [s for s in inners if s.strip()]


def to_leaves(command):
    """Full pipeline: a command string -> list of peeled leaf token-lists.
    Normalizes Unicode separators, splits on shell separators, peels wrappers,
    and recurses into command substitutions."""
    command = _normalize_ws(command)
    leaves = []
    for seg in raw_segments(command):
        leaves.extend(peel(_tokenize(seg)))
    for inner in extract_substitutions(command):
        leaves.extend(to_leaves(inner))
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


def git_alias_targets(leaf):
    """If `git -c alias.X=Y ... X` defines a one-shot alias and then invokes it,
    return the command string the alias expands to (for recursive inspection): a
    git subcommand string, or a shell command for a `!`-prefixed alias.

    `git -c alias.wipe='reset --hard' wipe` discards a dirty worktree while the
    subcommand token git_destructive sees is the harmless `wipe`; expanding the
    alias closes that bypass without touching persistent config."""
    aliases = {}
    i = 1
    while i < len(leaf) - 1:
        if leaf[i] == "-c":
            m = re.match(r"alias\.([^=]+)=(.*)$", _sq(leaf[i + 1]), re.IGNORECASE)
            if m:
                aliases[m.group(1).lower()] = m.group(2)
            i += 2
            continue
        i += 1
    if not aliases:
        return []
    idx = git_sub_idx(leaf)
    if idx < 0:
        return []
    exp = aliases.get(_sq(leaf[idx]).lower())
    if exp is None:
        return []
    extra = " ".join(leaf[idx + 1:])
    if exp.startswith("!"):                        # shell alias: run the body verbatim
        return [(exp[1:] + " " + extra).strip()]
    return [("git " + exp + " " + extra).strip()]  # git subcommand alias


def git_unresolvable_alias(leaf):
    """True if a git alias is defined via a mechanism whose VALUE cannot be
    resolved from the argument text — `--config-env=alias.X=ENVVAR` puts the alias
    body in an env var. The construct is an obfuscation (the real command hides in
    the alias), so fail closed. (`-c alias.X=value` IS resolvable and is expanded
    by git_alias_targets; GIT_CONFIG_* env-config is caught in inspect_command.)"""
    i = 1
    while i < len(leaf):
        t = _sq(leaf[i]).lower()
        if t.startswith("--config-env=") and "alias." in t:
            return True
        if t == "--config-env" and i + 1 < len(leaf) and "alias." in _sq(leaf[i + 1]).lower():
            return True
        i += 1
    return False


def _has_force(rest):
    """True if a flag list carries -f / --force, including short clusters (-qf)."""
    return any(t == "--force" or
               (t.startswith("-") and not t.startswith("--") and "f" in t)
               for t in rest)


def git_destructive(sub, rest):
    """Return a block reason for a destructive git subcommand, else ''."""
    if sub == "reset" and "--hard" in rest:
        return "Blocked `git reset --hard`."
    if sub in ("rm", "mv"):
        # git rm <pathspec> removes, git mv <src>... <dst> moves — both mutate
        # the named worktree files. Classify the path operands like the catch-all
        # (git is skipped there), so enforcement/.git/openspec paths are blocked.
        for t in rest:
            if t.startswith("-"):
                continue
            ts = t.replace("\\", "/")
            if (SELF_PROTECT_LOOSE.search(ts) or GIT_DIR_LOOSE.search(ts)
                    or classify_path(ts, shell=True) == "block"):
                return f"Blocked `git {sub}` of an enforcement/.git/openspec path."
    if sub == "clean":
        # Parse flags exactly: short clusters are single-dash alpha runs; long
        # flags whole. An option VALUE (--exclude=node_modules) must not leak its
        # letters into flag detection. -n (dry-run) overrides -f (preview is safe).
        short = "".join(t[1:] for t in rest if re.match(r"^-[A-Za-z]+$", t))
        longs = [t for t in rest if t.startswith("--")]
        dry = ("n" in short) or ("--dry-run" in longs)
        force = ("f" in short) or ("--force" in longs)
        if force and not dry:
            return "Blocked destructive `git clean -f`."
    if sub == "push":
        if any(t == "-f" or t.startswith("--force") for t in rest):
            return "Blocked force push."
        if "--delete" in rest or "--mirror" in rest:
            return "Blocked remote ref deletion/mirror push."
        # +ref / +src:dst = force-update refspec; :ref = remote ref deletion.
        if any(re.match(r"^\+[^\s]+$", t) or re.match(r"^:[^:\s]+$", t) for t in rest):
            return "Blocked force/delete by refspec."
    if sub == "branch" and (any(t in ("-d", "-D", "--delete") for t in rest)
                            or _has_force(rest)):
        # delete (-d/-D) or force-move (-f/--force) a ref can lose commits.
        # Rename (-m/-M) stays allowed: `git branch -M main` is routine/recoverable.
        return "Blocked destructive `git branch` (delete / force-move)."
    if sub == "remote" and rest[:1] == ["set-url"]:
        return "Blocked remote URL change."
    if sub == "reflog" and rest[:1] in (["expire"], ["delete"], ["drop"]):
        return f"Blocked potentially irreversible `git reflog {rest[0]}`."
    if sub == "gc" and any(t.startswith("--prune") and t != "--prune=never" for t in rest):
        return "Blocked `git gc --prune` (drops dangling-commit recovery)."
    if sub in DESTRUCTIVE_SUBCMDS:
        return f"Blocked potentially irreversible `git {sub}`."
    if sub == "checkout":
        if "--" in rest or "." in rest:
            return "Blocked `git checkout` (-- / . discards working-tree edits)."
        if "--force" in rest or any(
                re.match(r"^-[A-Za-z]*f[A-Za-z]*$", t) and not t.startswith("--") for t in rest):
            return "Blocked `git checkout -f/--force` (discards working-tree edits)."
        # Path-form `git checkout <file>` / pathspec restore (incl. magic like
        # `:/README.md`, `:(top)…`) restores from the index, discarding edits. A
        # branch name can't start with ':' and won't exist as a worktree path, so
        # block ':'-pathspecs or args naming a real path; `git checkout <branch>`
        # (no such path) stays allowed.
        if any(not t.startswith("-")
               and (_sq(t).startswith(":") or os.path.exists(_sq(t))) for t in rest):
            return "Blocked `git checkout <path/pathspec>` (discards working-tree edits)."
    if sub == "restore":
        # restore touches the working tree by default; only --staged/-S WITHOUT
        # --worktree/-W leaves the worktree intact.
        def _short(ch):  # case-sensitive short flag inside a cluster, e.g. -S / -SW
            return any(re.match(r"^-[A-Za-z]*" + ch + r"[A-Za-z]*$", t)
                       and not t.startswith("--") for t in rest)
        staged = ("--staged" in rest) or _short("S")
        worktree = ("--worktree" in rest) or _short("W")
        if worktree or not staged:
            return "Blocked `git restore` (discards working-tree edits)."
    if sub == "switch":
        # `-f`/`--force` is an alias for `--discard-changes`; both throw away
        # uncommitted edits on a dirty worktree. `-c`/`-C` (create) are safe.
        if "--discard-changes" in rest or "--force" in rest or any(
                re.match(r"^-[A-Za-z]*f[A-Za-z]*$", t) and not t.startswith("--") for t in rest):
            return "Blocked `git switch -f/--discard-changes` (discards working-tree edits)."
    if sub == "worktree" and rest[:1] == ["remove"]:
        return "Blocked `git worktree remove`."
    if sub == "stash" and rest[:1] in (["clear"], ["drop"]):
        return f"Blocked `git stash {rest[0]}` (discards stashed changes)."
    return ""


def classify_path(path, shell=False):
    """'block' for enforcement/.git paths and openspec/changes/archive (any
    channel), plus openspec/specs on the SHELL channel; 'ask' for protected;
    else ''. The block tier is matched component-wise (regex) so an absolute
    path cannot slip past a start-anchored glob."""
    p = _norm(path)
    if SELF_PROTECT_RE.search(p) or GIT_DIR_RE.search(p) or OPENSPEC_ARCHIVE_RE.search(p):
        return "block"
    if shell and OPENSPEC_SPECS_RE.search(p):
        return "block"
    if any(fnmatch.fnmatch(p, pat) for pat in PROTECTED_PATHS):
        return "ask"
    return ""


def _is_fd_ref(operand):
    """True if a redirection operand is a file-descriptor reference (`1`, `&2`,
    `-`, `&-`) rather than a filename — i.e. `>&1` / `2>&-` duplication/close."""
    s = operand[1:] if operand.startswith("&") else operand
    return s == "" or all(c in "0123456789-" for c in s)


def _redir_file(operand):
    """The file a redirection writes to, or '' when it is an fd dup/close.
    Handles bash's combined-redirect `>&file` (operand `&file` -> `file`)."""
    if operand.startswith("&"):
        return "" if _is_fd_ref(operand) else operand[1:]
    return operand


def _split_redirects(tokens):
    """(positionals, out_targets): out_targets are files written via > >> n> >|
    >& — leading-operator OR glued after a word (`x>file`). Input redirects
    (< << n<) are consumed but never write-targets, so a stdin redirect cannot
    masquerade as a copy/move destination. `>&`/`n>&` to an fd (`2>&1`) is a
    duplication, not a write, so it yields no target."""
    positionals, out_targets = [], []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        m = REDIR_RE.match(t)
        if m:  # token starts with [fd]> / >> / >| / >& / <
            op, operand = m.group(2), m.group(4)
            is_write = op.startswith(">")
            if operand in ("", "&"):  # operator-only token: file is the next token
                if i + 1 < len(tokens):
                    nxt = tokens[i + 1]
                    i += 1
                    # `>& 1` duplicates an fd; `>& file` / `> file` writes a file
                    if is_write and not (operand == "&" and _is_fd_ref(nxt)):
                        out_targets.append(nxt)
                i += 1
                continue
            f = _redir_file(operand)
            if is_write and f:
                out_targets.append(f)
            i += 1
            continue
        if ">" in t:  # operator glued after a word: `arg>file`, `arg>&file`
            em = EMBED_REDIR_RE.search(t)
            if em:
                f = _redir_file(em.group("operand"))
                if not f and not em.group("operand") and i + 1 < len(tokens):
                    f = tokens[i + 1]
                    i += 1
                if f:
                    out_targets.append(f)
                prefix = t[:em.start()].rstrip("0123456789")  # drop trailing fd digits
                if prefix:
                    positionals.append(prefix)
                i += 1
                continue
        positionals.append(t)
        i += 1
    return positionals, out_targets


def _target_dir_opt(args):
    """GNU `-t DIR` / `-tDIR` / `--target-directory[=DIR]`: the directory all
    sources are written into. Returns DIR or ''."""
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-t", "--target-directory") and i + 1 < len(args):
            return args[i + 1]
        if a.startswith("--target-directory="):
            return a.split("=", 1)[1]
        if a.startswith("-t") and len(a) > 2 and not a.startswith("--"):
            return a[2:]  # glued -tDIR
        i += 1
    return ""


def _ps_dest(args):
    """Destination of a PowerShell write cmdlet: -Path/-FilePath/-LiteralPath
    value, else the FIRST positional argument."""
    i = 0
    while i < len(args):
        if args[i].lower() in ("-path", "-filepath", "-literalpath") and i + 1 < len(args):
            return args[i + 1]
        i += 1
    for a in args:
        if not a.startswith("-"):
            return a
    return ""


def write_targets(tokens):
    """Every path a segment writes to: redirection targets (> >> n> >|, glued or
    spaced), plus the destination of a copy/move/tee verb, a PowerShell write
    cmdlet (first positional / -Path), or a writer program (dd of=, sed/perl -i,
    truncate)."""
    if not tokens:
        return []
    prog = _prog(tokens[0])
    positionals, targets = _split_redirects(tokens)
    rest = positionals[1:]                       # arguments after the program
    nonflag = [a for a in rest if not a.startswith("-")]
    tdir = _target_dir_opt(rest) if prog in GNU_TARGET_DIR_VERBS else ""
    if tdir:
        targets.append(tdir)                     # -t DIR: sources copied INTO DIR
    if prog == "tee":
        targets.extend(nonflag)                  # tee writes EVERY file operand
    elif prog in MOVE_VERBS:
        targets.extend(nonflag)                  # move removes source(s) + writes dest
    elif prog in WRITE_VERBS and nonflag and not tdir:
        targets.append(nonflag[-1])              # cp/install dest = last (no -t DIR)
    elif prog in PS_WRITE_VERBS:
        dest = _ps_dest(rest)
        if dest:
            targets.append(dest)
    elif prog == "dd":
        for a in rest:
            if a.lower().startswith("of="):
                targets.append(a[3:])
    elif prog in ("sed", "perl"):
        if any(a == "-i" or a.startswith(("-i", "--in-place")) for a in rest) and nonflag:
            targets.append(nonflag[-1])          # the file edited in place
    elif prog in ("truncate", "ed") and nonflag:
        targets.append(nonflag[-1])
    return [_norm(_sq(p)) for p in targets if p]


def _destructive_target(prog, leaf):
    """For a deleting command, classify its path arguments: 'block' if it targets
    the enforcement tree / .git / openspec truth, 'ask' for a protected path,
    else ''. `find` only counts when it actually deletes (-delete / -exec rm)."""
    args = leaf[1:]
    if prog == "find":
        low = [a.lower() for a in args]
        # ACTIVE when find can mutate: -delete, OR any executor (-exec/-execdir/
        # -ok/-okdir) — the executor may delete indirectly (`-exec sh -c 'rm …'`),
        # so the exact'd program isn't necessarily a literal rm. Inactive find
        # (-name/-type/...) is a read/list and stays allowed.
        active = ("-delete" in low
                  or any(e in low for e in ("-exec", "-execdir", "-ok", "-okdir")))
        if not active:
            return ""
    worst = ""
    for t in args:
        if t.startswith("-"):
            continue
        ts = _sq(t).replace("\\", "/")
        # LOOSE catch (same backstop as the catch-all) closes the glob-literal
        # form `find . -path '*.gigacode*' -exec rm` where classify_path's
        # component anchor would miss the predicate value.
        if SELF_PROTECT_LOOSE.search(ts) or GIT_DIR_LOOSE.search(ts):
            return "block"
        c = classify_path(ts, shell=True)
        if c == "block":
            return "block"
        if c == "ask":
            worst = "ask"
    return worst


def _self_protect_catch_all(prog, leaf):
    """Defense-in-depth backstop: block ANY non-read-only, non-git command that
    merely NAMES an enforcement/.git/openspec path in its arguments — even
    through a writer this gate does not model (touch, mkdir, ln, rsync, chmod,
    tar, New-Item, an interpreter one-liner like `python -c "open('.gigacode/x','w')"`).
    git is inspected by subcommand above; read-only programs (cat/grep/ls/
    Get-Content/find/...) are allow-listed so reading enforcement files still works.

    This is the layer that makes self-protection robust against unparsed shell
    structure: the bypass class shrinks from 'every shell feature' to 'effects
    fully hidden from the argument text' (env-var expansion, here-docs, compiled
    helpers) — those are accepted residuals handled by settings.json + review.
    Returns 'block' / 'ask' / ''."""
    if prog == "git" or prog in READ_ONLY_PROGS:
        return ""
    worst = ""
    for tok in leaf[1:]:
        t = _sq(tok).replace("\\", "/")
        if SELF_PROTECT_LOOSE.search(t) or GIT_DIR_LOOSE.search(t):
            return "block"
        c = classify_path(t, shell=True)
        if c == "block":
            return "block"
        if c == "ask":
            worst = "ask"
    return worst


def inspect_command(command):
    """Return (decision, reason) for a shell command: 'block'/'ask'/''."""
    pending_ask = ""
    # GIT_CONFIG_* env-config can define an alias whose body runs a destructive
    # command (GIT_CONFIG_COUNT/KEY_n/VALUE_n) without ever appearing as a git
    # flag. peel drops env assignments, so detect the construct on the raw text.
    # Legit GIT_CONFIG_GLOBAL/SYSTEM/NOSYSTEM are NOT matched.
    if re.search(r"\bGIT_CONFIG_(KEY|VALUE|COUNT)\w*\s*=", command):
        return "block", ("Blocked git env-config alias mechanism (GIT_CONFIG_*). "
                         "Use plain git subcommands.")
    for raw_leaf in to_leaves(command):
        if not raw_leaf:
            continue
        # Strip redirections FIRST so the program is the first POSITIONAL, not a
        # leading redirect token (`>/tmp/out git reset --hard` runs git, not `out`).
        leaf, redir_targets = _split_redirects(raw_leaf)
        for tgt in redir_targets:
            t = _norm(_sq(tgt))
            c = classify_path(t, shell=True)
            if c == "block":
                return "block", f"Blocked shell write to enforcement/.git path '{t}'."
            if c == "ask":
                pending_ask = "Shell write to a protected/openspec-truth path requires explicit confirmation."
        if not leaf:
            continue
        prog = _prog(leaf[0])
        if prog == "git":
            # A one-shot `-c alias.X=...` can hide the destructive subcommand
            # behind a benign alias name; expand and inspect it recursively.
            for expansion in git_alias_targets(leaf):
                d, r = inspect_command(expansion)
                if d == "block":
                    return "block", r
                if d == "ask" and not pending_ask:
                    pending_ask = r
            # …and an alias defined via --config-env hides its body in an env var.
            if git_unresolvable_alias(leaf):
                return "block", ("Blocked git inline alias via --config-env (body hidden "
                                 "in an env var; cannot verify). Use plain git subcommands.")
            idx = git_sub_idx(leaf)
            if idx >= 0:
                sub = _sq(leaf[idx]).lower()
                rest = [_sq(t) for t in leaf[idx + 1:]]  # original case: -S != -s, -W != -w
                reason = git_destructive(sub, rest)
                if reason:
                    return "block", reason
        elif prog in DESTRUCTIVE_VERBS:
            d = _destructive_target(prog, leaf)
            if d == "block":
                return "block", "Blocked deletion of an enforcement/.git/openspec path."
            if d == "ask":
                pending_ask = "Deletion of a protected path requires explicit confirmation."
        for tgt in write_targets(leaf):              # verb dests (redirects stripped)
            c = classify_path(tgt, shell=True)
            if c == "block":
                return "block", f"Blocked shell write to enforcement/.git path '{tgt}'."
            if c == "ask":
                pending_ask = "Shell write to a protected/openspec-truth path requires explicit confirmation."
        # Structural backstop after the modelled writers (see docstring).
        catch = _self_protect_catch_all(prog, leaf)
        if catch == "block":
            return "block", (f"Blocked command '{prog}' referencing an enforcement/"
                             ".git/openspec path. Enforcement files are edited only "
                             "via an out-of-band human workflow.")
        if catch == "ask" and not pending_ask:
            pending_ask = "Command references a protected path; explicit confirmation required."
    if pending_ask:
        return "ask", pending_ask
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
    # UTF-8 stdout so a self-contained run (echo ... | python git_guard.py) emits
    # any non-ASCII reason cleanly on a cp1251 Windows console.
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass
    try:
        # utf-8-sig: PowerShell pipes may prepend a UTF-8 BOM that breaks json.load
        event = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", errors="replace"))
    except json.JSONDecodeError:
        print(json.dumps({"decision": "allow"}, ensure_ascii=False))
        return
    print(json.dumps(run(event), ensure_ascii=False))


if __name__ == "__main__":
    main()
