# Build Tools Cheat Sheet

## Digest

- Detection: `build.gradle`/`build.gradle.kts`/`settings.gradle*` -> Gradle; `pom.xml` -> Maven.
- Wrapper first: `./gradlew` over `gradle`, `./mvnw` over `mvn` (`.bat`/`.cmd` on Windows).
- Compile check: `./gradlew -q testClasses` or `mvn -q test-compile`.
- Single test: `./gradlew test --tests "com.example.FooTest"` or `mvn -Dtest=FooTest test`.
- Lint only if the plugin is configured in the build file: `ktlintCheck`, `detekt`, `checkstyleMain`, `spotlessCheck`.
- CI-safe flags: `--no-daemon -q` (Gradle), `-q -B` (Maven).
- If no build tool is available, state the limitation explicitly and rely on static checks.

## Gradle commands

| Purpose | Command |
|---|---|
| Compile prod + test | `./gradlew --no-daemon -q testClasses` |
| All tests | `./gradlew --no-daemon -q test` |
| One test class | `./gradlew test --tests "com.example.FooTest"` |
| One test method | `./gradlew test --tests "com.example.FooTest.shouldReject*"` |
| ktlint / detekt | `./gradlew ktlintCheck` / `./gradlew detekt` |
| Spotless | `./gradlew spotlessCheck` (fix: `spotlessApply`) |

## Maven commands

| Purpose | Command |
|---|---|
| Compile prod + test | `mvn -q -B test-compile` |
| All tests | `mvn -q -B test` |
| One test class | `mvn -q -B -Dtest=FooTest test` |
| One test method | `mvn -q -B -Dtest='FooTest#shouldReject*' test` |
| Checkstyle | `mvn -q -B checkstyle:check` |
| Spotless | `mvn -q -B spotless:check` |

## Reading failures

- Gradle test reports: `build/reports/tests/test/index.html`; per-test XML under `build/test-results/test/`.
- Maven surefire reports: `target/surefire-reports/`.
- On compile errors, fix the first error before re-running - later errors are usually cascade noise.
