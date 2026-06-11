#!/usr/bin/env python3
import fnmatch,json,os,re,shlex,subprocess,sys

PROTECTED_BRANCHES=[
    "main","master","develop","development","release","release/*",
    "hotfix/*","production","prod","staging","uat",
]
PROTECTED_PATHS=[
    "**/.github/workflows/**",".github/workflows/**",".gitlab-ci.yml",
    "**/Jenkinsfile","Jenkinsfile","ci/**","**/ci/**","deploy/**",
    "deployment/**","k8s/**","helm/**","terraform/**","**/terraform/**",
    "infra/**","**/infra/**",".env",".env.*","**/.env","**/.env.*",
    "secrets/**","**/secrets/**","config/prod/**","config/production/**",
    "config/staging/**","config/uat/**",
]
SELF_PROTECT=[".gigacode/**",".gigacode"]
OPENSPEC_TRUTH_RE=re.compile(r"(^|/)openspec/(specs|changes/archive)/",re.IGNORECASE)
PREFIX_WRAPPERS={"env","nice","ionice","time","stdbuf","nohup","sudo","doas","timeout","xargs"}
DASH_C_WRAPPERS={"bash","sh","zsh","dash","ash","ksh","cmd","command","powershell","pwsh"}
DESTRUCTIVE_VERBS={"rm","rmdir","del","erase","remove-item","ri","rd","truncate","shred"}
WRITE_VERBS={"cp","mv","copy","move","copy-item","cpi","move-item","mi","tee","install","rename-item","rni"}
ENV_ASSIGN_RE=re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
GIT_GLOBAL_VALUE_FLAGS={"-c","-C","--git-dir","--work-tree","--namespace",
    "--super-prefix","--exec-path","--config-env","--attr-source","--list-cmds"}
DESTRUCTIVE_SUBCMDS={"update-ref","reflog","gc","filter-branch","filter-repo"}


def run_git(args):
    try:
        r=subprocess.run(["git"]+args,cwd=os.getcwd(),text=True,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    except FileNotFoundError:
        return ""
    return r.stdout.strip() if r.returncode==0 else ""

def current_branch():
    return run_git(["branch","--show-current"])

def is_protected_branch(branch):
    return bool(branch) and any(fnmatch.fnmatch(branch,p) for p in PROTECTED_BRANCHES)

def command_from_event(event):
    for key in ("command","tool_input","input"):
        v=event.get(key)
        if isinstance(v,str): return v
        if isinstance(v,dict):
            cmd=v.get("command") or v.get("cmd")
            if isinstance(cmd,str): return cmd
    return ""

def _norm(path):
    p=str(path).replace("\\","/")
    p=os.path.normpath(p).replace("\\","/")
    return p[2:] if p.startswith("./") else p

def path_from_event(event):
    for key in ("path","file_path","filename"):
        v=event.get(key)
        if isinstance(v,str): return _norm(v)
    ti=event.get("tool_input")
    if isinstance(ti,dict):
        for key in ("path","file_path","filename"):
            v=ti.get(key)
            if isinstance(v,str): return _norm(v)
    return ""

def protected_path(path):
    if not path: return False
    return any(fnmatch.fnmatch(_norm(path),pat) for pat in PROTECTED_PATHS)

def _sq(tok):
    if len(tok)>=2 and tok[0]==tok[-1] and tok[0] in "\"'": return tok[1:-1]
    return tok

def _prog(tok):
    base=os.path.basename(_sq(tok).replace("\\","/")).lower()
    return base[:-4] if base.endswith(".exe") else base

def _tokenize(s):
    try: return shlex.split(s,posix=True)
    except ValueError: return [_sq(t) for t in s.split()]

def raw_segments(command):
    parts,cur=[],[]
    in_s=in_d=False
    i=0
    while i<len(command):
        c=command[i]
        if c=="'" and not in_d: in_s=not in_s; cur.append(c); i+=1; continue
        if c=='"' and not in_s: in_d=not in_d; cur.append(c); i+=1; continue
        if not in_s and not in_d:
            if command[i:i+2] in("&&","||"): parts.append("".join(cur).strip()); cur=[]; i+=2; continue
            if c in(";","|","&","\n"): parts.append("".join(cur).strip()); cur=[]; i+=1; continue
        cur.append(c); i+=1
    parts.append("".join(cur).strip())
    return [p for p in parts if p]

def peel(tokens):
    """Strip wrappers from a token list; return list-of-token-lists (leaves)."""
    i=0
    while i<len(tokens):
        tok=tokens[i].strip("()")
        if not tok: i+=1; continue
        if ENV_ASSIGN_RE.match(tok): i+=1; continue
        prog=_prog(tok)
        if prog in PREFIX_WRAPPERS:
            i+=1
            while i<len(tokens) and tokens[i].startswith("-"): i+=1
            continue
        if prog in DASH_C_WRAPPERS:
            k=i+1
            while k<len(tokens) and tokens[k].lower() not in("-c","-command","/c"): k+=1
            rest=tokens[k+1:] if k<len(tokens) else []
            if len(rest)==1 and " " in rest[0]:
                return to_leaves(rest[0])
            inner=" ".join(rest)
            return to_leaves(inner) if inner else []
        break
    leaf=[t.strip("()") for t in tokens[i:] if t.strip("()")]
    return [leaf] if leaf else []

def to_leaves(command):
    leaves=[]
    for seg in raw_segments(command):
        tokens=_tokenize(seg)
        leaves.extend(peel(tokens))
    return leaves

def split_command(cmd):
    try: return shlex.split(cmd,posix=False)
    except ValueError: return cmd.split()

def git_sub_idx(leaf):
    i=1
    while i<len(leaf):
        tok=leaf[i]
        if not tok.startswith("-"): return i
        if tok in GIT_GLOBAL_VALUE_FLAGS and "=" not in tok: i+=2
        else: i+=1
    return -1

def git_destructive(sub,rest):
    if sub=="reset" and "--hard" in rest: return "Blocked `git reset --hard`."
    if sub=="clean":
        combined="".join(t.lstrip("-") for t in rest if t.startswith("-"))
        if "f" in combined: return "Blocked destructive `git clean -f`."
    if sub=="push":
        if any(t=="-f" or t.startswith("--force") for t in rest): return "Blocked force push."
        if "--delete" in rest or "--mirror" in rest: return "Blocked remote ref deletion/mirror push."
        if any(re.match(r"^[+:][^:\s]+$",t) for t in rest): return "Blocked force/delete by refspec."
    if sub=="branch" and any(t in("-d","-D","--delete") for t in rest): return "Blocked local branch deletion."
    if sub=="remote" and rest[:1]==["set-url"]: return "Blocked remote URL change."
    if sub in DESTRUCTIVE_SUBCMDS: return f"Blocked potentially irreversible `git {sub}`."
    if sub=="checkout" and "--" in rest: return "Blocked `git checkout --` (discards working-tree edits)."
    if sub=="restore" and "--worktree" in rest: return "Blocked `git restore --worktree`."
    if sub=="worktree" and rest[:1]==["remove"]: return "Blocked `git worktree remove`."
    if sub=="stash" and rest[:1]==["clear"]: return "Blocked `git stash clear`."
    return ""

def classify_path(path):
    p=_norm(path)
    if any(fnmatch.fnmatch(p,pat) or p==pat.rstrip("/*") for pat in SELF_PROTECT): return "block"
    if OPENSPEC_TRUTH_RE.search(p): return "block"
    if any(fnmatch.fnmatch(p,pat) for pat in PROTECTED_PATHS): return "ask"
    return ""

def write_targets(tokens):
    targets,i=[],0
    prog=_prog(tokens[0]) if tokens else ""
    while i<len(tokens):
        t=tokens[i]
        if t in(">",">>") and i+1<len(tokens): targets.append(_sq(tokens[i+1])); i+=2; continue
        if t.startswith(">") and len(t)>1: targets.append(_sq(t.lstrip(">"))); i+=1; continue
        i+=1
    if prog in WRITE_VERBS:
        args=[a for a in tokens[1:] if not a.startswith("-")]
        if args: targets.append(_sq(args[-1]))
    return [_norm(p) for p in targets if p]

def _git_in_args(leaf):
    for t in leaf[1:]:
        n=_norm(_sq(t))
        if n==".git" or n.startswith(".git/"): return True
    return False

def inspect_command(command):
    for leaf in to_leaves(command):
        if not leaf: continue
        prog=_prog(leaf[0])
        if prog=="git":
            idx=git_sub_idx(leaf)
            if idx>=0:
                sub=_sq(leaf[idx]).lower()
                rest=[_sq(t).lower() for t in leaf[idx+1:]]
                reason=git_destructive(sub,rest)
                if reason: return "block",reason
        elif prog in DESTRUCTIVE_VERBS:
            if _git_in_args(leaf): return "block","Blocked deletion of the git repository (.git)."
        worst=""
        for tgt in write_targets(leaf):
            c=classify_path(tgt)
            if c=="block": return "block",f"Blocked shell write to enforcement/openspec path '{tgt}'."
            if c=="ask": worst="ask"
        if worst=="ask": return "ask","Shell write to a protected path requires explicit confirmation."
    return "",""

def is_branch_write(command):
    for leaf in to_leaves(command.lower()):
        if not leaf: continue
        if _prog(leaf[0])=="git":
            idx=git_sub_idx(leaf)
            if idx>=0 and leaf[idx].lower() in("commit","push","rebase"): return True
    return False

def run(event):
    command=command_from_event(event)
    file_path=path_from_event(event)
    if command:
        decision,reason=inspect_command(command)
        if decision=="block":
            return {"decision":"block","reason":reason+" Use an explicit human-approved recovery workflow."}
        branch=current_branch()
        if is_protected_branch(branch) and is_branch_write(command):
            return {"decision":"block","reason":f"Blocked git write on protected branch '{branch}'. Use a feature/bugfix branch."}
        if decision=="ask":
            return {"decision":"ask","reason":reason}
    if file_path:
        cls=classify_path(file_path)
        if cls=="block":
            return {"decision":"block","reason":f"Write to enforcement-owned path '{file_path}' is blocked. Edit enforcement files via an out-of-band human workflow."}
        if cls=="ask" or protected_path(file_path):
            return {"decision":"ask","reason":f"Protected path '{file_path}' requires explicit confirmation with risk explanation."}
    return {"decision":"allow"}

def main():
    try:
        event=json.loads(sys.stdin.buffer.read().decode("utf-8-sig",errors="replace"))
    except json.JSONDecodeError:
        print(json.dumps({"decision":"allow"},ensure_ascii=False)); return
    print(json.dumps(run(event),ensure_ascii=False))

if __name__=="__main__":
    main()
