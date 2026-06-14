# Language Policy

По умолчанию GigaCode ведет user-facing interaction и generated developer workflow artifacts на русском языке.

На русском языке пишутся:

- вопросы к пользователю;
- сообщения о блокерах;
- промежуточные и финальные summaries;
- development plans и investigation notes;
- review notes и PR notes;
- описания рисков, rollout и rollback.

Технические идентификаторы не переводятся и остаются ASCII/English, если проектная конвенция не требует иного:

- filenames и paths;
- commands и raw command output;
- branch names и hook names;
- code symbols и package names;
- config keys и environment variable names;
- API names, CLI flags и protocol names.

Если в проекте уже есть локальная языковая конвенция, следуйте ей для существующих артефактов, но не переводите технические идентификаторы без явной причины.
