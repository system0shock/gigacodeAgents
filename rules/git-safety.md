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
- `git clean -fd`
- `git clean -ffd`
- `git checkout -- <path>`
- `git restore <path>` when it discards uncommitted work
- `git push --force`
- `git push --force-with-lease`
- deleting local or remote branches
- changing remote URLs
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
