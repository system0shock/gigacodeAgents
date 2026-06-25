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

Threat model / why two layers. Token-parsing arbitrary shell is inherently
leaky (every shell feature is a potential bypass), so self-protection does NOT
rely on parsing alone: `inspect_command` has a defense-in-depth backstop that
blocks ANY non-read-only command merely *naming* a `.gigacode`/`.git` path
(`_self_protect_catch_all`), regardless of the mechanism (ln, rsync, New-Item,
an interpreter one-liner, a writer this gate does not model). Read-only programs
are allow-listed so inspecting/reading enforcement files still works.

Known, accepted residuals (defense-in-depth, not a perfect sandbox): commands
whose destructive effect is fully hidden from the argument text — e.g. a value
read from an environment variable the shell expands (`rm -rf "$X"`), a here-doc
body, or bytes written by a compiled helper — cannot be classified here and are
caught by the broader settings.json permission layer + human review, not this
gate.

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
    ".qwen/**", "**/.qwen/**",
]
# Enforcement-owned paths and the .git repo: writes/deletes here BLOCK
# (fail-closed). Matched as a path COMPONENT anywhere in the (possibly absolute)
# path — a start-anchored fnmatch let an absolute path like F:/proj/.gigacode/...
# slip past, and Claude Code passes absolute file_path by default. IGNORECASE:
# on case-insensitive filesystems (Windows/macOS) `.GIGACODE` / `.Git` target the
# same protected directory, so the match must not be dodged by altered casing.
SELF_PROTECT_RE = re.compile(r"(^|/)\.gigacode(/|$)", re.IGNORECASE)
GIT_DIR_RE = re.compile(r"(^|/)\.git(/|$)", re.IGNORECASE)
# Looser variants for the defense-in-depth catch-all: match the protected
# component anywhere in an argument token (e.g. inside a quoted interpreter
# one-liner `python -c "open('.gigacode/x','w')"`), not only as a clean path
# component. `(?![A-Za-z0-9_])` keeps `.gigacoder` / `.github` / `.gitignore`
# from matching, so reads/writes of unrelated dot-names are unaffected.
SELF_PROTECT_LOOSE = re.compile(r"\.gigacode(?![A-Za-z0-9_])", re.IGNORECASE)
GIT_DIR_LOOSE = re.compile(r"\.git(?![A-Za-z0-9_])", re.IGNORECASE)
# Mirror of gate_spec_structure.DENY_RE so shell-redirection writes to openspec
# truth are caught here too (gate_spec_structure only sees WriteFile/Edit).
OPENSPEC_TRUTH_RE = re.compile(r"(^|/)openspec/(specs|changes/archive)/", re.IGNORECASE)

# Wrappers that prefix another command (the real command is their tail).
# `command`/`exec`/`builtin` run their argument as a program, so they are
# transparent prefixes, NOT -c string wrappers — listing `command` under
# DASH_C_WRAPPERS made `command git reset --hard` a universal kill-switch.
PREFIX_WRAPPERS = {"env", "nice", "ionice", "time", "stdbuf", "nohup",
                   "sudo", "doas", "timeout", "xargs", "command", "exec",
                   "builtin"}
# Wrapper short/long flags that consume a separate WORD value (e.g. `sudo -u
# root`, `env -u NAME`). Numeric values (`nice -n 10`, `timeout 30`) are caught
# generically by the isdigit() skip in peel(), so only word-valued flags are
# listed here to avoid swallowing the real command after a boolean flag.
WRAPPER_VALUE_FLAGS = {"-u", "-g", "-U", "--user", "--group"}
# xargs flags whose mandatory WORD operand precedes COMMAND. Without skipping the
# operand, `xargs -I {} git reset --hard` leaves the generic flag loop stopping on
# `{}` and treating `git` as the command's own argument, hiding the reset.
# Matched CASE-SENSITIVELY: lowercase `-i`/`-e` take an OPTIONAL value, so
# consuming the next token there would risk eating the real command (fail-open).
XARGS_VALUE_FLAGS = {"-I", "-d", "-E", "-a", "--delimiter", "--arg-file"}
# Per-wrapper word-valued options whose operand is a SEPARATE token. Only flags
# that UNAMBIGUOUSLY take a value are listed — marking a boolean flag here would
# consume the real command as its "value" and open a new bypass. (env -S /
# --split-string carries the command itself and is handled by _env_split_string.)
WRAPPER_VALUE_FLAGS_BY_PROG = {
    "env": {"--unset", "-c", "--chdir"},               # -C chdir (folded), --unset NAME
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "stdbuf": {"-i", "-o", "-e", "--input", "--output", "--error"},
}
# Wrappers that take the command as a -c / -Command / /c string argument.
DASH_C_WRAPPERS = {"bash", "sh", "zsh", "dash", "ash", "ksh",
                   "cmd", "powershell", "pwsh"}
# `eval ...` concatenates its arguments and runs the result as a command.
EVAL_WRAPPERS = {"eval"}
# Bash reserved words / control keywords that PRECEDE a command in a clause
# (`if true; then git reset --hard; fi`). They are peeled like a wrapper so the
# real command after `then`/`do`/`else`/`{`/`!` is still inspected.
SHELL_KEYWORDS = {"if", "then", "elif", "else", "fi", "while", "until", "for",
                  "do", "done", "case", "esac", "in", "select", "function",
                  "coproc", "{", "}", "!"}
# Non-git verbs that delete; flagged when they target a protected path. `find`
# is delete-guarded in _destructive_target (only -delete / -exec rm counts).
DESTRUCTIVE_VERBS = {"rm", "rmdir", "del", "erase", "remove-item", "ri", "rd",
                     "truncate", "shred", "find"}
# `find` actions that WRITE or EXECUTE (vs. a pure-read traversal). A find is NOT
# treated as read-only when any of these is present, so `find . -fprintf
# .gigacode/x` / `find . -exec rm {} ;` reach the self-protect catch-all.
FIND_ACTION_FLAGS = {"-delete", "-exec", "-execdir", "-ok", "-okdir",
                     "-fprintf", "-fprint", "-fprint0", "-fls"}
# Verbs whose final positional argument is a write destination (ln/rsync create
# the link/copy at their last operand).
WRITE_VERBS = {"cp", "mv", "copy", "move", "copy-item", "cpi", "move-item",
               "mi", "tee", "install", "rename-item", "rni", "ln", "rsync"}
# PowerShell write cmdlets: destination is -Path/-FilePath/-LiteralPath or the
# FIRST positional (NOT the last) — Windows is the primary platform.
PS_WRITE_VERBS = {"set-content", "add-content", "out-file", "tee-object",
                  "sc", "ac", "new-item", "ni"}
# Writer programs with a non-positional / in-place destination.
WRITER_PROGS = {"dd", "sed", "perl", "truncate", "ed"}
# Read-only programs: the defense-in-depth catch-all skips these, so reading or
# inspecting an enforcement file (cat/grep/ls/Get-Content ...) is never blocked.
# Programs that can WRITE (awk/sed/perl/tee/dd/cp/python/node/tar/...) are
# deliberately absent — naming a protected path with one of them is suspect.
READ_ONLY_PROGS = {
    "cat", "bat", "tac", "nl", "less", "more", "head", "tail", "view",
    "grep", "egrep", "fgrep", "rg", "ag", "ack", "git-grep",
    "ls", "dir", "tree", "stat", "file", "wc", "du", "df", "realpath",
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


_PATH_KEYS = ("path", "file_path", "filename", "notebook_path", "relative_path")


def path_from_event(event):
    # notebook_path: NotebookEdit identifies its target notebook there, not under
    # path/file_path — without it a NotebookEdit to .gigacode/x.ipynb has no
    # recognized path and slips past the write gate.
    for key in _PATH_KEYS:
        v = event.get(key)
        if isinstance(v, str):
            return _norm(v)
    ti = event.get("tool_input")
    if isinstance(ti, dict):
        for key in _PATH_KEYS:
            v = ti.get(key)
            if isinstance(v, str):
                return _norm(v)
    return ""


def _matches_protected(p):
    """True if p matches any PROTECTED_PATHS pattern, repo-relative OR nested
    under an absolute prefix. Each pattern is tested as-is AND with a leading
    `**/`, so a relative `deploy/x.yml` (caught by `deploy/**`) and an absolute
    `/home/u/proj/deploy/x.yml` (caught by `**/deploy/**`) both register without
    needing a hand-written `**/` twin per pattern. Claude Code commonly supplies
    absolute file_path values."""
    return any(fnmatch.fnmatch(p, pat) or fnmatch.fnmatch(p, "**/" + pat)
               for pat in PROTECTED_PATHS)


def protected_path(path):
    if not path:
        return False
    return _matches_protected(_norm(path))


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
    """NFKC-normalize, fold `$IFS` to a space, drop zero-width/format chars, and
    fold every Unicode space (Zs) to a plain space. Closes the NBSP / zero-width
    separator bypass (git<NBSP>reset<NBSP>--hard) on PowerShell and the
    `git${IFS}reset${IFS}--hard` field-splitting bypass on bash (default IFS
    expands to whitespace)."""
    s = unicodedata.normalize("NFKC", s)
    # Bash line continuation: a backslash immediately before a newline is removed
    # and the two lines join. Mimic it so `git reset \<newline>--hard` is seen as
    # `git reset --hard` instead of splitting on the newline.
    s = s.replace("\\\r\n", "").replace("\\\n", "")
    s = s.replace("${IFS}", " ").replace("$IFS", " ")
    out = []
    for ch in s:
        if ch in ZERO_WIDTH:
            continue
        out.append(" " if unicodedata.category(ch) == "Zs" else ch)
    s = "".join(out)
    # Windows path separator: a backslash before a path-ish char is a directory
    # separator on cmd/PowerShell-backed runtimes, not a bash escape. Fold it to
    # "/" so the posix tokenizer (_tokenize -> shlex.split posix=True) does not
    # CONSUME it and erase the separators in `.gigacode\hooks\x` ->
    # `.gigacodehooksx`, which dodged the self-protect catch-all (and the
    # cp/mv/rm path scans, classify_path, write_targets — every consumer reads
    # the already-mangled tokens). The lookahead restricts the fold to a
    # backslash followed by an identifier/dot char, so bash escape semantics are
    # untouched: `\"` (escaped quote), `\ ` (escaped space), `\$`, `\&`, and the
    # `\<newline>` line-continuation (already removed above) are all left intact.
    s = re.sub(r"\\(?=[A-Za-z0-9_.])", "/", s)
    return s


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
        # Backslash outside single quotes escapes the next char (bash): an escaped
        # quote/separator is literal, so `echo \" && git reset --hard` still splits
        # on && — the \" must not open a quoted context that swallows the rest.
        if c == "\\" and not in_s:
            cur.append(c)
            if i + 1 < len(command):
                cur.append(command[i + 1])
                i += 2
            else:
                i += 1
            continue
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
                # Redirections that embed | or & are not separators: `>|`
                # (clobber), `>&` (fd-dup / redirect-both), and `&>` / `&>>`
                # (redirect stdout+stderr). Don't split, or the redirect target
                # lands in its own segment and the write goes uninspected.
                prev_redir = "".join(cur).rstrip().endswith(">")
                next_redir = c == "&" and command[i + 1:i + 2] == ">"
                if c in ("|", "&") and (prev_redir or next_redir):
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


def _env_split_string(tok):
    """env's -S / --split-string option carries the COMMAND in its value. Return
    that value ('' if it is the next token), or None if tok is not the option."""
    if tok in ("-S", "--split-string"):
        return ""
    if tok.startswith("-S") and len(tok) > 2:
        return tok[2:]
    if tok.startswith("--split-string="):
        return tok[len("--split-string="):]
    return None


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
        if tok.lower() in SHELL_KEYWORDS:  # then / do / else / { / ! ... precede a command
            i += 1
            continue
        prog = _prog(tok)
        if prog in PREFIX_WRAPPERS:  # env / nice / sudo / timeout / xargs ... drop wrapper + flags/values
            extra_value_flags = WRAPPER_VALUE_FLAGS_BY_PROG.get(prog, set())
            xargs_flags = XARGS_VALUE_FLAGS if prog == "xargs" else set()
            i += 1
            while i < len(tokens):
                t = tokens[i]
                if prog == "env":  # env -S/--split-string carries the command itself
                    sval = _env_split_string(t)
                    if sval is not None:
                        if sval == "" and i + 1 < len(tokens):
                            sval = tokens[i + 1]
                        return to_leaves(sval)
                if t.startswith("-"):
                    i += 1
                    # skip a value belonging to this flag: a word value of a known
                    # value-flag (`sudo -u root`, `env --unset FOO`, `xargs -I {}`)
                    # or any numeric value (`nice -n 10`, `xargs -n 4`).
                    word_value_flag = (t.lower() in WRAPPER_VALUE_FLAGS
                                       or t.lower() in extra_value_flags
                                       or t in xargs_flags)
                    if (i < len(tokens) and not tokens[i].startswith("-")
                            and (word_value_flag or tokens[i].isdigit())):
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
    """Inner command strings of $(...), <(...), >(...) and `...` substitutions, so
    a destructive command hidden in a command OR process substitution
    (x=$(git reset --hard), cat <(git reset --hard), tee >(git reset --hard)) is
    still inspected — Bash executes the contents of all of these."""
    inners = []
    i = 0
    while i < len(command) - 1:
        two = command[i:i + 2]
        if two in ("$(", "<(", ">(") and not (i > 0 and command[i - 1] == "\\"):
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
    if exp.startswith("!"):                       # shell alias: run the body verbatim
        return [(exp[1:] + " " + extra).strip()]
    return [("git " + exp + " " + extra).strip()]  # git subcommand alias


def _has_force(rest):
    """True if a flag list carries -f / --force, including short clusters like
    -qf. (rest is already lowercased by the caller.)"""
    return any(t == "--force" or
               (t.startswith("-") and not t.startswith("--") and "f" in t)
               for t in rest)


def git_destructive(sub, rest):
    """Return a block reason for a destructive git subcommand, else ''."""
    if sub == "reset" and "--hard" in rest:
        return "Blocked `git reset --hard`."
    if sub == "clean":
        # --[no-]dry-run is last-one-wins, so compute the effective dry-run state
        # in argument order: a later `--no-dry-run` re-arms deletion even after an
        # earlier `-n`/`--dry-run`. force is sticky (once -f/--force).
        force = dry = False
        for t in rest:
            if t == "--force":
                force = True
            elif t == "--dry-run":
                dry = True
            elif t == "--no-dry-run":
                dry = False
            elif re.match(r"^-[a-z]+$", t):   # short cluster, e.g. -fdn
                if "f" in t:
                    force = True
                if "n" in t:
                    dry = True
        if force and not dry:
            return "Blocked destructive `git clean -f`."
    if sub == "push":
        # short clusters too: -uf / -fu (force), -d / -fd (delete). `--force*`
        # also covers --force-with-lease / --force-if-includes.
        if _has_force(rest) or any(t.startswith("--force") for t in rest):
            return "Blocked force push."
        if ("--delete" in rest or "--mirror" in rest
                or any(t.startswith("-") and not t.startswith("--") and "d" in t for t in rest)):
            return "Blocked remote ref deletion/mirror push."
        # +ref / +src:dst = force-update refspec; :ref = remote ref deletion.
        if any(re.match(r"^\+[^\s]+$", t) or re.match(r"^:[^:\s]+$", t) for t in rest):
            return "Blocked force/delete by refspec."
    if sub == "branch" and (any(t in ("-d", "-D", "--delete", "--force")
                                for t in rest) or _has_force(rest)):
        # delete (-d/-D) or force-move a ref (-f/--force) can lose commits.
        # Rename (-m/-M) is left allowed: `git branch -M main` (rename the current
        # branch) is a routine operation and recoverable via reflog.
        return "Blocked destructive `git branch` (delete / force-move)."
    if sub == "remote" and rest[:1] == ["set-url"]:
        return "Blocked remote URL change."
    if sub == "reflog" and rest[:1] in (["expire"], ["delete"], ["drop"]):
        return f"Blocked potentially irreversible `git reflog {rest[0]}`."
    if sub == "gc" and any(t.startswith("--prune") and t != "--prune=never" for t in rest):
        return "Blocked `git gc --prune` (drops dangling-commit recovery)."
    if sub in DESTRUCTIVE_SUBCMDS:
        return f"Blocked potentially irreversible `git {sub}`."
    if sub == "checkout" and ("--" in rest or "." in rest or _has_force(rest)):
        # `git checkout -f <branch>`, `git checkout -- <path>`, and `git checkout .`
        # all throw away local working-tree modifications. (A specific-file
        # `git checkout file.kt` can't be told from a branch name without git, so
        # only the unambiguous `.` / `--` / -f forms are blocked here.)
        return "Blocked `git checkout` (-f / -- / . discards working-tree edits)."
    if sub == "switch" and (_has_force(rest) or "--discard-changes" in rest
                            or "--force-create" in rest):
        # `git switch -f` / `--discard-changes` discard local edits; `--force-create`
        # (long form of -C) resets the target branch ref. (-C short form is
        # case-folded to -c here, so it is caught in inspect_command's git branch.)
        return "Blocked `git switch` (--force / --discard-changes / --force-create)."
    if sub == "restore":
        # --worktree is git restore's DEFAULT, so `git restore .` discards edits
        # even without the flag; only the index-only form (`--staged` WITHOUT a
        # worktree flag) is non-destructive. `-W` is the short worktree flag
        # (case-folded to -w here), so `git restore --staged -W .` still discards.
        worktree = "--worktree" in rest or any(
            re.match(r"^-[a-z]*w[a-z]*$", t) for t in rest)
        if worktree or "--staged" not in rest:
            return "Blocked `git restore` (discards working-tree edits; use --staged to unstage)."
    if sub == "worktree" and rest[:1] == ["remove"]:
        return "Blocked `git worktree remove`."
    if sub == "stash" and rest[:1] in (["clear"], ["drop"]):
        return f"Blocked `git stash {rest[0]}` (discards stashed changes)."
    return ""


def resets_branch_ref(args, short, long_flags=()):
    """True if a force-create/reset branch flag is present: the uppercase short
    flag `short` (checkout -B / switch -C — it CREATES OR RESETS the target ref,
    like `git branch -f`) or any of long_flags. Case-sensitive: the lowercase
    short flag is the harmless create flag, so run on ORIGINAL-case args."""
    for a in args:
        if a in long_flags:
            return True
        if a.startswith("-") and not a.startswith("--") and short in a:
            return True
    return False


def checkout_discards_path(args):
    """True if a `git checkout` argument is a path that EXISTS on disk — git then
    treats it as a pathspec and discards that file's working-tree edits (the `--`
    separator is optional for an unambiguous file). Disk existence is git's own
    branch-vs-path disambiguation, so `git checkout main` (no file `main`) stays a
    branch switch while `git checkout src/Foo.kt` is blocked. (`.` / `--` / -f are
    handled in git_destructive.) args must be ORIGINAL case (paths are
    case-sensitive)."""
    for t in args:
        if t.startswith("-"):
            continue
        p = _sq(t)
        if not p or p == "--":
            continue
        # A git ref name cannot contain : * ? [ (git check-ref-format), so an arg
        # with one is a pathspec — incl. magic `:/`, `:(top)file`, and globs —
        # which discards matching working-tree files.
        if any(ch in p for ch in ":*?["):
            return True
        if os.path.exists(p):
            return True
    return False


def git_external_config(leaf):
    """True if a git leaf loads aliases/config from OUTSIDE the inspectable
    command string: `--config-env=alias.*` (the expansion lives in an env var) or
    `include.path=` / `includeIf.` (config pulled from a file). Their expansion
    can't be read here, so a destructive subcommand can hide behind them
    (`ALIAS='reset --hard' git --config-env=alias.x=ALIAS x`,
    `git -c include.path=/tmp/cfg x`). These forms have no use in the agent flow,
    so block the pattern (fail-closed). Scoped to the global-option region before
    the subcommand to avoid matching a subcommand's own path arguments."""
    idx = git_sub_idx(leaf)
    region = leaf[1:idx] if idx > 0 else leaf[1:]
    for i, t in enumerate(region):
        low = _sq(t).lower()
        if (low.startswith("--config-env=alias.")
                or "include.path=" in low or low.startswith("includeif.")):
            return True
        # space-separated `--config-env alias.x=VAR`: the operand is the next
        # token (its value lives in an env var -> unexpandable -> block). The
        # `-c alias.X=Y` form is NOT blocked here: git_alias_targets expands it,
        # so a benign alias (`git -c alias.st=status st`) is still allowed.
        if low == "--config-env" and i + 1 < len(region):
            nxt = _sq(region[i + 1]).lower()
            if nxt.startswith("alias.") or "include.path=" in nxt or nxt.startswith("includeif."):
                return True
    return False


def push_dst_branch(refspec):
    """Destination branch of a push refspec (src:dst or bare dst), normalized;
    '' when there is no determinate destination (a bare HEAD pushes to the
    same-named remote branch, which the current-branch check already covers)."""
    spec = refspec
    if ":" in spec:
        spec = spec.split(":", 1)[1]
    elif spec.upper() == "HEAD":
        return ""
    spec = re.sub(r"^refs/(heads|remotes)/", "", spec)
    return spec.strip("/")


def push_refspec_protected(leaf, idx):
    """Block reason if a `git push` leaf targets a protected branch BY REFSPEC
    (`git push origin main`, `git push origin HEAD:main`), else ''. The
    current-branch check misses these — they push to a protected branch from a
    feature branch — so local policy (rules/git-safety.md) needs them here too."""
    nonflag = [_sq(t) for t in leaf[idx + 1:] if not t.startswith("-")]
    for refspec in nonflag[1:]:           # nonflag[0] is the remote
        dst = push_dst_branch(refspec)
        if dst and is_protected_branch(dst):
            return f"Blocked push to protected branch '{dst}'. Open a PR or push a feature branch."
    return ""


def classify_path(path):
    """'block' for enforcement (.gigacode) / .git paths, 'ask' for openspec truth
    and other protected paths, else ''. The block tier is matched component-wise
    (regex) so an absolute path cannot slip past a start-anchored glob.

    OpenSpec truth (openspec/specs, openspec/changes/archive) is ASK, not block,
    so the legitimate sync/archive lifecycle (`/opsx:sync`, `/opsx:archive`) can
    write it with a human confirm while a direct fabrication still surfaces;
    .gigacode and .git stay block (the agent must never edit/destroy those)."""
    p = _norm(path)
    if SELF_PROTECT_RE.search(p) or GIT_DIR_RE.search(p):
        return "block"
    if OPENSPEC_TRUTH_RE.search(p) or _matches_protected(p):
        return "ask"
    return ""


def _parse_redirect(tok):
    """Classify a possible redirection token.

    Returns (is_write, operand, needs_next), or None if tok is not a redirection:
      is_write   — writes a FILE (not an fd dup/close like 2>&1 / >&-)
      operand    — glued file operand ('' if the file is the next token)
      needs_next — the operand is the following token

    Handled forms:  n>  n>>  >|  n<  n<<        (operand = file)
                    &>file  &>>file             (stdout+stderr -> file)
                    >&-  n>&m  2>&1             (fd dup / close, NOT a write)
                    >&file  n>&file            (stdout[+stderr] -> file)
    A bare `>& file` (spaced) is treated as a file write — the rare `>& 1`
    (spaced fd dup) erring toward block is the safe direction for a guard."""
    m = re.match(r"^&(>{1,2})(.*)$", tok)            # &>  &>>
    if m:
        operand = m.group(2)
        return (True, operand, operand == "")
    m = re.match(r"^(\d*)(>{1,2}|<{1,2})&(.*)$", tok)  # n>&...  n<&...
    if m:
        rest = m.group(3)
        if rest == "-" or rest.isdigit():            # >&-  >&1  2>&1 : no file
            return (False, "", False)
        if rest == "":                               # `>& file` : file is next token
            return (m.group(2).startswith(">"), "", True)
        return (m.group(2).startswith(">"), rest, False)   # `>&file`
    m = re.match(r"^(\d*)(>{1,2}|<{1,2})(\|?)(.*)$", tok)  # n>  n>>  >|  n<  n<<
    if m:
        operand = m.group(4)
        return (m.group(2).startswith(">"), operand, operand == "")
    return None


def _split_redirects(tokens):
    """(positionals, out_targets): positionals excludes redirect operators and
    their operands; out_targets are files written via > >> n> >| &> >&file (any
    fd, glued or spaced). Input redirects (< << n<) and fd dup/close (2>&1, >&-)
    are consumed but never write-targets, so neither a stdin redirect nor an
    fd-dup can masquerade as a copy/move destination."""
    positionals, out_targets = [], []
    i = 0
    while i < len(tokens):
        pr = _parse_redirect(tokens[i])
        if pr is not None:
            is_write, operand, needs_next = pr
            if needs_next and i + 1 < len(tokens):
                operand = tokens[i + 1]
                i += 1
            if is_write and operand:
                out_targets.append(operand)
            i += 1
            continue
        positionals.append(tokens[i])
        i += 1
    return positionals, out_targets


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
    if prog in WRITE_VERBS and nonflag:
        targets.append(nonflag[-1])              # cp/mv/tee/install dest = last
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
        deleting = "-delete" in low or (
            "-exec" in low and any(_prog(a) in ("rm", "rmdir", "del") for a in args))
        if not deleting:
            return ""
    worst = ""
    for t in args:
        if t.startswith("-"):
            continue
        c = classify_path(_sq(t))
        if c == "block":
            return "block"
        if c == "ask":
            worst = "ask"
    return worst


def _self_protect_catch_all(prog, leaf):
    """Defense-in-depth backstop: block ANY non-read-only command that merely
    NAMES a `.gigacode`/`.git` path in its arguments — even through a writer this
    gate does not model (ln, rsync, New-Item, chmod, tar, an interpreter
    one-liner like `python -c "open('.gigacode/x','w')"`). git is inspected by
    subcommand above; read-only programs (cat/grep/ls/Get-Content/find/...) are
    allow-listed so reading or inspecting enforcement files still works.

    This is the layer that makes self-protection robust against unparsed shell
    structure: the bypass class shrinks from 'every shell feature' to 'effects
    fully hidden from the argument text' (env-var expansion, here-docs, compiled
    helpers) — those are accepted residuals handled by settings.json + review."""
    if prog == "git" or prog in READ_ONLY_PROGS:
        return ""
    # A pure-read `find` (no -delete/-exec/-fprintf/...) is read-only; one with a
    # write/exec action is not, and falls through to the path scan below.
    if prog == "find" and not any(a in FIND_ACTION_FLAGS for a in leaf[1:]):
        return ""
    for tok in leaf[1:]:
        t = _sq(tok).replace("\\", "/")
        if SELF_PROTECT_LOOSE.search(t) or GIT_DIR_LOOSE.search(t):
            return (f"Blocked command '{prog}' that references an enforcement/.git "
                    "path. Enforcement files are edited only via an out-of-band "
                    "human workflow.")
    return ""


def inspect_command(command):
    """Return (decision, reason) for a shell command: 'block'/'ask'/''."""
    pending_ask = ""
    # GIT_CONFIG_* env-vars (GIT_CONFIG_KEY_n/VALUE_n, GIT_CONFIG_GLOBAL/SYSTEM)
    # inject config/aliases into the following git command from the environment.
    # Their definitions live in env-assignment prefixes that peel() strips, so
    # detect them on the raw segment and block a git command configured that way.
    if "GIT_CONFIG" in command:
        for seg in raw_segments(_normalize_ws(command)):
            toks = _tokenize(seg)
            if any(re.match(r"^GIT_CONFIG[A-Za-z0-9_]*=", t) for t in toks):
                for lf in peel(toks):
                    if lf and _prog(lf[0]) == "git":
                        return "block", ("Blocked git configured via GIT_CONFIG_* "
                            "environment variables (cannot be inspected). Use a plain git command.")
    for leaf in to_leaves(command):
        if not leaf:
            continue
        prog = _prog(leaf[0])
        if prog == "git":
            # Aliases/config loaded from env or an include file can't be expanded
            # here — block the (illegitimate) pattern outright.
            if git_external_config(leaf):
                return "block", ("Blocked git command loading aliases/config from "
                                 "the environment or an include file (cannot be "
                                 "inspected). Use a plain git command.")
            # A one-shot `-c alias.X=...` can hide the destructive subcommand
            # behind a benign alias name; expand and inspect it recursively.
            for expansion in git_alias_targets(leaf):
                d, r = inspect_command(expansion)
                if d == "block":
                    return "block", r
                if d == "ask" and not pending_ask:
                    pending_ask = r
            idx = git_sub_idx(leaf)
            if idx >= 0:
                sub = _sq(leaf[idx]).lower()
                rest = [_sq(t).lower() for t in leaf[idx + 1:]]
                reason = git_destructive(sub, rest)
                if reason:
                    return "block", reason
                if sub == "checkout" and checkout_discards_path(leaf[idx + 1:]):
                    return "block", "Blocked `git checkout <path>` (discards working-tree edits to that file)."
                if sub == "checkout" and resets_branch_ref(leaf[idx + 1:], "B"):
                    return "block", "Blocked `git checkout -B` (resets the target branch ref)."
                if sub == "switch" and resets_branch_ref(leaf[idx + 1:], "C", ("--force-create",)):
                    return "block", "Blocked `git switch -C/--force-create` (resets the target branch ref)."
                if sub == "push":
                    reason = push_refspec_protected(leaf, idx)
                    if reason:
                        return "block", reason
        elif prog in DESTRUCTIVE_VERBS:
            d = _destructive_target(prog, leaf)
            if d == "block":
                return "block", "Blocked deletion of an enforcement/.git/openspec path."
            if d == "ask":
                pending_ask = "Deletion of a protected path requires explicit confirmation."
        for tgt in write_targets(leaf):
            c = classify_path(tgt)
            if c == "block":
                return "block", f"Blocked shell write to enforcement/.git path '{tgt}'."
            if c == "ask":
                pending_ask = "Shell write to a protected/openspec-truth path requires explicit confirmation."
        reason = _self_protect_catch_all(prog, leaf)
        if reason:
            return "block", reason
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
