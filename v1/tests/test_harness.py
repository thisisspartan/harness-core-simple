import json, os, subprocess, sys, tempfile, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(ROOT, "scripts", "gate.py")
START = os.path.join(ROOT, "scripts", "start.py")


def sh(cwd, *cmd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        sh(self.root, "git", "init", "-q")
        sh(self.root, "git", "config", "user.email", "t@t")
        sh(self.root, "git", "config", "user.name", "t")
        self.write("a.txt", "1")
        sh(self.root, "git", "add", "-A")
        sh(self.root, "git", "commit", "-qm", "init")
        os.makedirs(os.path.join(self.root, ".harness"))
        self.counter = os.path.join(self.root, "runs.txt")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def verify(self, body):
        p = self.write(".harness/verify", "#!/usr/bin/env bash\necho x >> '%s'\n%s\n" % (self.counter, body))
        os.chmod(p, 0o755)

    def runs(self):
        if not os.path.exists(self.counter):
            return 0
        with open(self.counter) as f:
            return len(f.read().split())

    def call(self, script, payload=None, env=None, raw=None):
        e = dict(os.environ, CLAUDE_PROJECT_DIR=self.root, **(env or {}))
        r = subprocess.run([sys.executable, script], input=raw if raw is not None else json.dumps(payload or {}),
                           capture_output=True, text=True, env=e)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def gate(self, sess="s1", **kw):
        out = self.call(GATE, {"session_id": sess}, **kw)
        return json.loads(out) if out.strip() else None

    def base(self):
        with open(os.path.join(self.root, ".harness/state/gate.json")) as f:
            return json.load(f)["base"]["s1"]

    def start(self, sess="s1", source="startup"):
        return self.call(START, {"session_id": sess, "source": source})


class GateTests(Base):
    def test_no_verify_is_noop(self):
        self.write("a.txt", "2")
        self.assertIsNone(self.gate())

    def test_not_executable_warns_and_is_off(self):
        self.write(".harness/verify", "#!/bin/sh\nexit 1\n")
        self.write("a.txt", "2")
        self.assertIn("not executable", self.gate()["systemMessage"])

    def test_pass_allows_and_is_not_rerun_on_same_tree(self):
        self.verify("exit 0")
        self.start()
        self.write("a.txt", "2")
        self.assertIsNone(self.gate())
        self.assertIsNone(self.gate())
        self.assertEqual(self.runs(), 1)

    def test_fail_blocks_with_tail(self):
        self.verify("echo BOOM; exit 3")
        self.start()
        self.write("a.txt", "2")
        r = self.gate()
        self.assertEqual(r["decision"], "block")
        self.assertIn("exited 3", r["reason"])
        self.assertIn("BOOM", r["reason"])
        self.assertIn("attempt 1/3", r["reason"])

    def test_gives_up_after_three_blocks(self):
        self.verify("exit 1")
        self.start()
        self.write("a.txt", "2")
        for i in (1, 2, 3):
            self.assertEqual(self.gate()["decision"], "block")
        self.assertIn("gave up", self.gate()["systemMessage"])

    def test_session_without_changes_does_not_run(self):
        self.verify("exit 1")
        self.write("a.txt", "dirty-before-session")
        self.start()
        self.assertIsNone(self.gate())
        self.assertEqual(self.runs(), 0)

    def test_change_after_pass_reruns(self):
        self.verify("exit 0")
        self.start()
        self.write("a.txt", "2"); self.gate()
        self.write("a.txt", "3"); self.gate()
        self.assertEqual(self.runs(), 2)

    def test_untracked_file_counts_as_change(self):
        self.verify("exit 0")
        self.start()
        self.write("new.txt", "x")
        self.gate()
        self.assertEqual(self.runs(), 1)

    def test_harness_dir_changes_are_ignored(self):
        self.verify("exit 0")
        self.start()
        self.write(".harness/task.md", "progress")
        self.gate()
        self.assertEqual(self.runs(), 0)

    def test_timeout_counts_as_failure_and_kills_group(self):
        self.verify("sleep 30")
        self.start()
        self.write("a.txt", "2")
        r = self.gate(env={"HARNESS_VERIFY_TIMEOUT": "1"})
        self.assertIn("timed out", r["reason"])

    def test_kill_switch(self):
        self.verify("exit 1")
        self.start()
        self.write("a.txt", "2")
        self.assertIsNone(self.gate(env={"HARNESS_GATE": "0"}))

    def test_bad_timeout_env_falls_back_and_still_exits_zero(self):
        self.verify("exit 1")
        self.start()
        self.write("a.txt", "2")
        self.assertEqual(self.gate(env={"HARNESS_VERIFY_TIMEOUT": "abc"})["decision"], "block")

    def test_cyrillic_survives_non_utf8_locale(self):
        env = {"LC_ALL": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0"}
        self.write(".harness/task.md", "# Task\nЦель: перенос Strata")
        self.verify('echo "ОШИБКА теста: ожидалось 1"; exit 1')
        out = self.call(START, {"session_id": "s1", "source": "startup"}, env=env)
        self.assertIn("Цель: перенос Strata", out)
        self.write("a.txt", "2")
        r = json.loads(self.call(GATE, {"session_id": "s1"}, env=env))
        self.assertIn("ОШИБКА теста", r["reason"])

    def test_after_give_up_a_turn_without_edits_does_not_block_again(self):
        self.verify("exit 1")
        self.start()
        self.write("a.txt", "2")
        for _ in range(3):
            self.assertEqual(self.gate()["decision"], "block")
        self.assertIn("gave up", self.gate()["systemMessage"])
        runs = self.runs()
        self.assertIsNone(self.gate())
        self.assertEqual(self.runs(), runs)
        self.write("a.txt", "3")
        self.assertEqual(self.gate()["decision"], "block")

    def test_background_process_does_not_delay_the_gate(self):
        self.verify("(sleep 20 &)\nexit 0")
        self.start()
        self.write("a.txt", "2")
        t0 = time.time()
        self.assertIsNone(self.gate())
        self.assertLess(time.time() - t0, 8)

    def test_edits_inside_a_dirty_submodule_are_seen(self):
        sub = tempfile.TemporaryDirectory()
        self.addCleanup(sub.cleanup)
        sh(sub.name, "git", "init", "-q")
        sh(sub.name, "git", "config", "user.email", "t@t")
        sh(sub.name, "git", "config", "user.name", "t")
        with open(os.path.join(sub.name, "s.txt"), "w") as f:
            f.write("s")
        sh(sub.name, "git", "add", "-A")
        sh(sub.name, "git", "commit", "-qm", "i")
        sh(self.root, "git", "-c", "protocol.file.allow=always", "submodule", "add", "-q", sub.name, "sub")
        sh(self.root, "git", "commit", "-qm", "sm")
        self.verify("exit 0")
        self.start()
        for i in (1, 2, 3):
            self.write("sub/s.txt", "edit %d" % i)
            self.gate()
        self.assertEqual(self.runs(), 3)

    def test_large_tracked_file_does_not_disable_the_gate(self):
        self.write("a.txt", "1")
        with open(os.path.join(self.root, "big.bin"), "wb") as f:
            f.write(os.urandom(64 * 1024 * 1024))
        sh(self.root, "git", "add", "-A")
        sh(self.root, "git", "commit", "-qm", "big")
        self.verify("exit 1")
        self.start()
        with open(os.path.join(self.root, "big.bin"), "ab") as f:
            f.write(b"x")
        t0 = time.time()
        self.assertEqual(self.gate()["decision"], "block")
        self.assertLess(time.time() - t0, 5)

    def test_garbage_stdin_is_silent(self):
        self.assertEqual(self.call(GATE, raw="not json").strip(), "")

    def test_not_a_git_repo_is_off(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, ".harness"); os.makedirs(p)
            v = os.path.join(p, "verify")
            with open(v, "w") as f:
                f.write("#!/bin/sh\nexit 1\n")
            os.chmod(v, 0o755)
            r = subprocess.run([sys.executable, GATE], input="{}", capture_output=True, text=True,
                               env=dict(os.environ, CLAUDE_PROJECT_DIR=d))
            self.assertEqual((r.returncode, r.stdout.strip()), (0, ""))

    def test_repo_without_commits_works(self):
        with tempfile.TemporaryDirectory() as d:
            sh(d, "git", "init", "-q")
            os.makedirs(os.path.join(d, ".harness"))
            v = os.path.join(d, ".harness", "verify")
            with open(v, "w") as f:
                f.write("#!/bin/sh\nexit 1\n")
            os.chmod(v, 0o755)
            env = dict(os.environ, CLAUDE_PROJECT_DIR=d)
            subprocess.run([sys.executable, START], input='{"session_id":"z"}', capture_output=True, text=True, env=env)
            with open(os.path.join(d, "f.py"), "w") as f:
                f.write("x=1")
            r = subprocess.run([sys.executable, GATE], input='{"session_id":"z"}', capture_output=True, text=True, env=env)
            self.assertEqual(json.loads(r.stdout)["decision"], "block")


    def test_commit_made_by_the_agent_before_stop_is_still_verified(self):
        # the agent edits AND commits before the first gate(): the tree is clean again,
        # only HEAD moved — a tree_id that ignores HEAD would skip the check entirely
        self.verify("exit 1")
        self.start()
        self.write("a.txt", "2")
        sh(self.root, "git", "commit", "-qam", "agent-commit")
        self.assertEqual(self.gate()["decision"], "block")

    def test_single_huge_line_output_is_char_capped(self):
        self.verify("python3 -c 'print(\"E\" * 20000)'; exit 1")
        self.start()
        self.write("a.txt", "2")
        r = self.gate()
        self.assertLess(len(r["reason"]), 4500)
        self.assertIn("[truncated]", r["reason"])

    def test_subdir_project_sees_every_edit_not_only_the_first(self):
        # without `diff --relative`, paths come out repo-rooted and lstat sees "gone" for
        # EVERY edit — both fingerprints match and the second edit is silently skipped
        self.write("sub/x.txt", "1")
        sh(self.root, "git", "add", "sub/x.txt")
        sh(self.root, "git", "commit", "-qm", "sub")
        sub = os.path.join(self.root, "sub")
        os.makedirs(os.path.join(sub, ".harness"), exist_ok=True)
        v = os.path.join(sub, ".harness", "verify")
        with open(v, "w") as f:
            f.write("#!/usr/bin/env bash\necho x >> '%s'\nexit 0\n" % self.counter)
        os.chmod(v, 0o755)
        env = dict(os.environ, CLAUDE_PROJECT_DIR=sub)
        run = lambda s: subprocess.run([sys.executable, s], input='{"session_id":"sd"}',
                                       capture_output=True, text=True, env=env, check=True)
        run(START)
        self.write("sub/x.txt", "2")
        run(GATE)
        self.write("sub/x.txt", "3333")
        run(GATE)
        self.assertEqual(self.runs(), 2)

    def test_bad_timeout_bounds_are_clamped(self):
        self.verify("sleep 0.1; exit 0")
        self.start()
        self.write("a.txt", "2")
        self.assertIsNone(self.gate(env={"HARNESS_VERIFY_TIMEOUT": "0"}))

    def test_broken_symlink_retarget_is_seen(self):
        # os.stat on a dangling symlink raises -> fingerprint "gone" for BOTH targets;
        # os.lstat fingerprints the link itself (size = target-name length differs here)
        self.verify("exit 0")
        self.start()
        os.symlink("t.txt", os.path.join(self.root, "link"))  # target never created
        self.gate()
        self.assertEqual(self.runs(), 1)
        os.remove(os.path.join(self.root, "link"))
        os.symlink("target2.txt", os.path.join(self.root, "link"))
        self.gate()
        self.assertEqual(self.runs(), 2)

    def test_fails_map_is_pruned_to_50(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import lib
        st = {"base": {}, "fails": {"s%d" % i: 1 for i in range(60)}}
        lib.save_state(self.root, st)
        with open(os.path.join(self.root, ".harness/state/gate.json")) as f:
            saved = json.load(f)
        self.assertEqual(len(saved["fails"]), 50)
        self.assertIn("s59", saved["fails"])
        self.assertNotIn("s0", saved["fails"])


class StartTests(Base):
    def test_prints_kernel_task_and_state(self):
        self.write(".harness/task.md", "# Task\nGoal: ship")
        self.verify("exit 0")
        out = self.start(source="compact")
        for needle in ("Harness kernel", "Goal: ship", "branch=", "source=compact", "verify gate: .harness/verify"):
            self.assertIn(needle, out)

    def test_missing_task_and_verify_are_reported_not_fatal(self):
        out = self.start()
        self.assertIn("OFF", out)
        self.assertNotIn("task.md ---", out)

    def test_huge_task_is_truncated_under_hook_cap(self):
        self.write(".harness/task.md", "x" * 50000)
        out = self.start()
        self.assertLess(len(out), 8000)
        self.assertIn("truncated", out)

    def test_last_gate_result_shown(self):
        self.verify("exit 0")
        self.start()
        self.write("a.txt", "2"); self.gate()
        self.assertIn("PASS", self.start(sess="s2"))

    def test_base_tree_recorded_once_per_session(self):
        self.start()
        base1 = self.base()
        self.write("a.txt", "changed")
        self.start(source="compact")
        base2 = self.base()
        self.assertEqual(base1, base2)

    def test_garbage_stdin_still_prints(self):
        self.assertIn("Harness kernel", self.call(START, raw="nope"))

    def test_repo_without_commits_prints_real_branch_not_no_git(self):
        with tempfile.TemporaryDirectory() as d:
            sh(d, "git", "init", "-q")
            out = subprocess.run([sys.executable, START], input='{"session_id":"z"}',
                                 capture_output=True, text=True,
                                 env=dict(os.environ, CLAUDE_PROJECT_DIR=d), check=True).stdout
            self.assertIn("branch=", out)
            self.assertNotIn("branch=no-git", out)


GUARD = os.path.join(ROOT, "scripts", "loop_guard.py")


class LoopGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, payload, sess="s1", agent="main", raw=None):
        payload = dict(payload, session_id=sess, agent_id=agent)
        stdin = raw if raw is not None else json.dumps(payload)
        env = dict(os.environ, TMPDIR=self.tmp.name)
        r = subprocess.run([sys.executable, GUARD], input=stdin,
                           capture_output=True, text=True, env=env)
        return r.returncode, r.stderr

    def bash(self, cmd, **kw):
        return self.call({"tool_name": "Bash", "tool_input": {"command": cmd}}, **kw)

    def edit(self, path, **kw):
        return self.call({"tool_name": "Edit", "tool_input": {"file_path": path}}, **kw)

    def test_same_call_blocked_at_8_and_history_kept(self):
        for _ in range(7):
            self.assertEqual(0, self.bash("ls")[0])
        code, err = self.bash("ls")
        self.assertEqual(2, code)
        self.assertIn("Loop guard blocked", err)
        # history not clobbered by the blocked call: repeats stay blocked
        self.assertEqual(2, self.bash("ls")[0])

    def test_different_command_resets(self):
        for _ in range(7):
            self.assertEqual(0, self.bash("ls")[0])
        self.assertEqual(0, self.bash("pwd")[0])
        self.assertEqual(0, self.bash("ls")[0])

    def test_ab_cycle_blocked_at_6(self):
        for seq in "ABABA":
            self.assertEqual(0, self.bash("cmd" + seq)[0])
        code, err = self.bash("cmdB")
        self.assertEqual(2, code)
        self.assertIn("alternating", err)
        self.assertEqual(2, self.bash("cmdB")[0])

    def test_tdd_pattern_allowed(self):
        for i in range(1, 4):
            self.assertEqual(0, self.bash("python3 -m unittest")[0])
            self.assertEqual(0, self.edit(f"fix{i}.py")[0])

    def test_agents_isolated_per_session(self):
        for _ in range(7):
            self.assertEqual(0, self.bash("ls", agent="main")[0])
        # sub1's different history does not reset main's
        self.assertEqual(0, self.bash("ls", agent="sub1")[0])
        self.assertEqual(2, self.bash("ls", agent="main")[0])

    def test_garbage_stdin_fail_open(self):
        env = dict(os.environ, TMPDIR=self.tmp.name, LC_ALL="C")
        r = subprocess.run([sys.executable, GUARD], input="nope",
                           capture_output=True, text=True, env=env)
        self.assertEqual(0, r.returncode)


if __name__ == "__main__":
    unittest.main()
