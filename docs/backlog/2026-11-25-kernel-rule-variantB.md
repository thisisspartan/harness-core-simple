# ТЗ: правило «сначала инструмент под задачу» (Вариант Б)

**СТАТУС: ВЫПОЛНЕНО** — реализовано в коммите `ede0ace` (2026-11-25).
kernel.md содержит правило, дубль из `~/.claude/CLAUDE.md` удалён, 33 теста + E2E + validate зелёные.
Файл оставлен как архив ТЗ и обоснования выбора — чтобы вернуться к решению, а не к работе.

---

Перенеси правило «сначала инструмент под задачу» внутрь плагина (в `v1/templates/kernel.md`), убери дубль из `~/.claude/CLAUDE.md` и проверь, что все тесты и валидация зелёные. Работаем в `/home/hermes/projects/harness-core-simple`.

1. Перезапиши `v1/templates/kernel.md` ровно этим текстом:

```
# Harness kernel
You own the outcome: work until the project's check passes. Ask the operator only for goals, product decisions and true blockers.
- Non-trivial task: first write the goal and verifiable acceptance criteria in .harness/task.md. Small clear task: just do it.
- If `.harness/verify` exists, it is the project check: the harness runs it when you stop and blocks up to 3 times if it fails. Run it yourself before stopping. Without it, still end with verified evidence (command output, script calculation), not opinion.
- For multi-step math, log/benchmark parsing, or bug repros, write a small script (`python3 -c` or `/tmp`), sanity-check it on a known case, and run it instead of reasoning by hand; promote recurring checks to `tests/` or `.harness/verify`. Skip tooling on 1-2 step edits.
- Keep .harness/task.md current at real checkpoints (stage done, decision made, before a long command, before stopping): goal, status, evidence, next step, open questions. Rewrite it, do not append a log; keep it under 40 lines.
- Delegate to a subagent for: (a) broad multi-file search (built-in Explore); (b) noisy output over ~100 lines (`harness-core:digest`, or redirect to a file and Read ranges); (c) independent parallel work or fresh review. Planning and code edits stay in your main context.
- Ask subagents for a brief verdict (<=20 lines) plus file path if output was saved; record verdicts in .harness/task.md under Evidence.
- Durable project facts belong in CLAUDE.md or docs, not only in the conversation.
```

2. Обнови `~/.claude/CLAUDE.md`: удали блок про leverage/скрипты (чтобы не дублировал `kernel.md`), оставь там только личное правило оператора:

```
- End engineering reviews with an explicit verdict: ACCEPT, REJECT, or INSUFFICIENT DATA, scoped strictly to what was asked.
```

3. Из `/home/hermes/projects/harness-core-simple/v1` прогони:
   - `python3 -m unittest discover -s tests`
   - `tests/e2e/run.sh`
   - `claude plugin validate .`

4. Закоммить изменение `v1/templates/kernel.md` локально (без push) и в отчёте покажи:
   - `git diff HEAD~1` по репо;
   - `cat ~/.claude/CLAUDE.md` целиком;
   - `wc -c v1/templates/kernel.md` и результаты всех трёх проверок.

---

## Обоснование выбора (из разбора)

1. Через /harness-init в проектный CLAUDE.md — точно не нужно. Проектный CLAUDE.md — для фактов конкретного проекта и команды, а harness-init специально в него не лезет, чтобы не конкурировать с нативным /init. Плюс в репо без harness-init этого правила всё равно не было бы.

2. В templates/kernel.md vs ~/.claude/CLAUDE.md — оба варианта рабочие, но выбран строго ОДИН (чтобы не дублировать в контексте):

   - **Вариант А** — оставить в ~/.claude/CLAUDE.md (ничего не менять): уже грузится в любой проект на этом компе (даже без /harness-init). Плюс — плагин остаётся стерильно нейтральным; минус — при переносе на другой сервер или запуске с другим HOME правило не едет вместе с плагином.

   - **Вариант Б (ВЫБРАН)** — перенести строкой в templates/kernel.md, из ~/.claude/CLAUDE.md убрать. Принцип «сначала инструмент + sanity-check» становится частью харнесса и работает везде, куда подключаешь --plugin-dir (новый HOME, чистый -p, после /compact), даже без /harness-init. Цена — +285 символов к ядру (вывод start.py ~5.4K при лимите теста 8K и лимите хука 10K — все 33 теста проходят).
