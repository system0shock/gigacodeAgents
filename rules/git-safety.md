# Git Safety Rules

Protected branch patterns:

- `main`
- `master`
- `develop`
- `development`
- `release`
- `release/*`
- `hotfix/*`
- `production`
- `prod`
- `staging`
- `uat`

Forbidden git operations by default:

- `git reset --hard`
- any `git clean` command that combines force and directory deletion flags in any order or combined form, including `git clean -df`, `git clean -f -d`, `git clean -fd`, `git clean -ffd`, and `git clean -xffd`
- `git checkout -- <path>`
- `git restore <path>` when it discards uncommitted work
- all force-push variants, including `git push --force`, `git push -f`, and `git push --force-with-lease`
- local branch deletion forms, including `git branch -d <branch>` and `git branch -D <branch>`
- remote branch deletion forms, including `git push origin --delete <branch>` and `git push origin :<branch>`
- `git remote set-url`
- changing remote URLs
- `git rebase` on protected or shared branches
- committing directly to protected branches
- pushing directly to protected branches

Protected paths:

- `.github/workflows/**`
- `.gitlab-ci.yml`
- `Jenkinsfile`
- `ci/**`
- `deploy/**`
- `deployment/**`
- `k8s/**`
- `helm/**`
- `terraform/**`
- `infra/**`
- `.env`
- `.env.*`
- `secrets/**`
- `config/prod/**`
- `config/production/**`
- `config/staging/**`
- `config/uat/**`

Изменения в protected paths требуют явного human confirmation, где названы файлы и объяснен риск.
