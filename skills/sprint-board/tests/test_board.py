"""Tests for the sprint-board scripts.

    python3 -m unittest discover -s tests
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import board_lint  # noqa: E402
import board_scaffold  # noqa: E402

# A fabricated six-digit ID, belonging to no board anywhere. The regime rules key
# off the six-digit shape, so the tests that exercise them need one; it is joined
# to its prefix at runtime rather than written inline, because a prefixed literal
# is the shape a real board identifier takes.
REAL_ID = "510001"
# The zero-sequence form the linter rejects beside a real ID. Joined at runtime for
# the same reason.
ZERO_ID = "000001"


CLEAN_BOARD = """# EPIC-NNNN01
- [ ] Reporting Platform Stability

**DESCRIPTION**
````
**OUTCOME**:
Make scheduled reporting dependable enough to run unattended.

**OUT OF SCOPE**:
- Report content changes

**END STATE**:
- Scheduled reports complete within their window

**COMPLETION EVIDENCE**:
- Run history for one observation period
````

---

## FEATURE-NNNN02
- [ ] Report Delivery Reliability
- Parent: EPIC-NNNN01

**DESCRIPTION**
````
**PURPOSE**:
Confirm scheduled reports are produced and delivered on time.

**KEY ACTIVITIES**:
- [ ] Inventory scheduled reports
- [ ] Review delivery failures
- [ ] Define retry behaviour

**ACCEPTANCE CRITERIA**:
- [ ] Every scheduled report is inventoried (STORY-NNNN03)
- [ ] Delivery failures are categorised (STORY-NNNN03, STORY-NNNN04)
- [ ] Retry behaviour is documented (STORY-NNNN04)
- [ ] Owner is recorded (STORY-NNNN03)

**PRIMARY OWNER**: Platform Engineer
````

---

### STORY-NNNN03
- [ ] Record scheduler job outcomes
- Parent: FEATURE-NNNN02

**DESCRIPTION**
````
**USER STORY**:
As the platform team, we need each scheduler run to record its outcome.

**DEVELOPMENT APPROACH**:
- [ ] Add an outcome column
- [ ] Write the outcome on completion
- [ ] Expose the last outcome
````

**ACCEPTANCE CRITERIA**
````
**DEFINITION OF DONE**:
- [ ] Every run writes an outcome
- [ ] Outcomes survive a restart
- [ ] The last outcome is queryable

**TESTING APPROACH**:
- [ ] Run a job and confirm the outcome is written
- [ ] Kill a worker mid-run and confirm a failure outcome
````

---

### STORY-NNNN04
- [ ] Alert on repeated failures
- Parent: FEATURE-NNNN02
- Depends on: STORY-NNNN03

**DESCRIPTION**
````
**USER STORY**:
As the platform team, we need an alert when a job fails repeatedly.

**DEVELOPMENT APPROACH**:
- [ ] Define the failure threshold
- [ ] Emit an alert at the threshold
- [ ] Document the response
````

**ACCEPTANCE CRITERIA**
````
**DEFINITION OF DONE**:
- [ ] An alert fires at the threshold
- [ ] The alert names the job
- [ ] The response is documented

**TESTING APPROACH**:
- [ ] Force repeated failures and confirm one alert
- [ ] Confirm a single failure does not alert
````
"""

# The same board in the real-ID regime, for the rules that only fire when a real
# six-digit ID is present.
REAL_ID_BOARD = CLEAN_BOARD.replace("EPIC-NNNN01", "EPIC-" + REAL_ID)


def lint_text(text):
    """Lint a board given as a string; return the list of finding codes."""
    items, parse_findings = board_lint.parse(text)
    return [f[2] for f in board_lint.check(items, parse_findings)]


def lint_errors(text):
    items, parse_findings = board_lint.parse(text)
    return [f[2] for f in board_lint.check(items, parse_findings) if f[0] == "error"]


class TestParse(unittest.TestCase):
    def test_extracts_items_and_fields(self):
        items, findings = board_lint.parse(CLEAN_BOARD)
        self.assertEqual([i.ref for i in items], [
            "EPIC-NNNN01", "FEATURE-NNNN02", "STORY-NNNN03", "STORY-NNNN04"])
        self.assertEqual(items[1].parent, "EPIC-NNNN01")
        self.assertEqual(items[3].depends, "STORY-NNNN03")
        self.assertEqual(items[0].title, "Reporting Platform Stability")
        self.assertEqual(findings, [])

    def test_captures_blocks_and_fence_width(self):
        items, _ = board_lint.parse(CLEAN_BOARD)
        story = items[2]
        self.assertIn("DESCRIPTION", story.blocks)
        self.assertIn("ACCEPTANCE CRITERIA", story.blocks)
        self.assertEqual(story.blocks["DESCRIPTION"]["fence"], "````")

    def test_unclosed_fence_is_reported(self):
        text = "# EPIC-000000\n- [ ] X\n\n**DESCRIPTION**\n````\nbody\n"
        _, findings = board_lint.parse(text)
        self.assertIn("unclosed-fence", [f[2] for f in findings])


class TestCleanBoard(unittest.TestCase):
    def test_clean_board_has_no_findings(self):
        self.assertEqual(lint_text(CLEAN_BOARD), [])


class TestStructuralChecks(unittest.TestCase):
    def test_duplicate_id(self):
        text = CLEAN_BOARD.replace("STORY-NNNN04", "STORY-NNNN03")
        self.assertIn("duplicate-id", lint_errors(text))

    def test_wrong_heading_level(self):
        text = CLEAN_BOARD.replace("## FEATURE-NNNN02", "# FEATURE-NNNN02")
        self.assertIn("heading-level", lint_errors(text))

    def test_missing_parent_line(self):
        text = CLEAN_BOARD.replace("- Parent: FEATURE-NNNN02\n", "", 1)
        self.assertIn("missing-parent", lint_errors(text))

    def test_absent_predecessor_line_is_not_an_error(self):
        """Parent is the only link an item must declare."""
        text = CLEAN_BOARD.replace("- Depends on: STORY-NNNN03\n", "")
        self.assertNotIn("missing-depends", lint_errors(text))

    def test_empty_predecessor_is_flagged(self):
        text = CLEAN_BOARD.replace("- Parent: FEATURE-NNNN02\n",
                                   "- Parent: FEATURE-NNNN02\n- Predecessor: none\n", 1)
        self.assertIn("empty-predecessor", lint_text(text))

    def test_predecessor_spelling_is_accepted(self):
        text = CLEAN_BOARD.replace("- Depends on: STORY-NNNN03", "- Predecessor: STORY-NNNN03")
        self.assertNotIn("unresolved-dependency", lint_errors(text))

    def test_unprefixed_parent_is_flagged(self):
        text = CLEAN_BOARD.replace("- Parent: FEATURE-NNNN02", "- Parent: NNNN02", 1)
        self.assertIn("unprefixed-parent", lint_text(text))

    def test_prefixed_parent_still_resolves(self):
        self.assertNotIn("unresolved-parent", lint_errors(CLEAN_BOARD))

    def test_unresolved_parent(self):
        text = CLEAN_BOARD.replace("- Parent: EPIC-NNNN01", "- Parent: EPIC-999999")
        self.assertIn("unresolved-parent", lint_errors(text))

    def test_parent_mismatch_against_position(self):
        text = CLEAN_BOARD.replace(
            "- Parent: FEATURE-NNNN02\n- Depends on: STORY-NNNN03",
            "- Parent: FEATURE-NNNN01\n- Depends on: STORY-NNNN03")
        self.assertIn("parent-mismatch", lint_errors(text))

    def test_unresolved_dependency(self):
        text = CLEAN_BOARD.replace("- Depends on: STORY-NNNN03", "- Depends on: STORY-777777")
        self.assertIn("unresolved-dependency", lint_errors(text))

    def test_order_violation(self):
        text = CLEAN_BOARD.replace(
            "### STORY-NNNN03\n- [ ] Record scheduler job outcomes\n"
            "- Parent: FEATURE-NNNN02",
            "### STORY-NNNN03\n- [ ] Record scheduler job outcomes\n"
            "- Parent: FEATURE-NNNN02\n- Predecessor: STORY-NNNN04")
        self.assertIn("order-violation", lint_errors(text))

    def test_self_dependency(self):
        text = CLEAN_BOARD.replace("- Depends on: STORY-NNNN03", "- Depends on: STORY-NNNN04")
        self.assertIn("self-dependency", lint_errors(text))

    def test_missing_block(self):
        text = CLEAN_BOARD.replace("**ACCEPTANCE CRITERIA**\n````\n**DEFINITION OF DONE**:\n"
                                   "- [ ] Every run writes an outcome\n"
                                   "- [ ] Outcomes survive a restart\n"
                                   "- [ ] The last outcome is queryable\n\n"
                                   "**TESTING APPROACH**:\n"
                                   "- [ ] Run a job and confirm the outcome is written\n"
                                   "- [ ] Kill a worker mid-run and confirm a failure outcome\n"
                                   "````\n", "", 1)
        self.assertIn("missing-block", lint_errors(text))

    def test_fence_width(self):
        text = CLEAN_BOARD.replace(
            "**DESCRIPTION**\n````\n**OUTCOME**:",
            "**DESCRIPTION**\n```\n**OUTCOME**:").replace(
            "- Run history for one observation period\n````",
            "- Run history for one observation period\n```")
        self.assertIn("fence-width", lint_errors(text))

    def test_template_residue(self):
        text = CLEAN_BOARD.replace("- [ ] Every run writes an outcome", "- [ ] Criterion 1")
        self.assertIn("template-residue", lint_errors(text))

    def test_no_items(self):
        self.assertIn("no-items", lint_errors("# Just a title\n\nSome prose.\n"))


class TestIdRegimes(unittest.TestCase):
    def test_zero_placeholder_beside_real_id_is_an_error(self):
        text = REAL_ID_BOARD.replace("### STORY-NNNN04", "### STORY-" + ZERO_ID)
        self.assertIn("wrong-placeholder-regime", lint_errors(text))

    def test_nnnn_placeholder_beside_real_id_is_accepted(self):
        text = REAL_ID_BOARD.replace("### STORY-NNNN04", "### STORY-NNNN01")
        codes = lint_errors(text)
        self.assertNotIn("wrong-placeholder-regime", codes)
        self.assertNotIn("bad-id-form", codes)

    def test_bad_id_form(self):
        text = CLEAN_BOARD.replace("### STORY-NNNN04", "### STORY-ABC")
        self.assertIn("bad-id-form", lint_errors(text))


class TestBudgets(unittest.TestCase):
    def test_over_budget_development_approach(self):
        extra = "\n".join(f"- [ ] Extra step {n}" for n in range(1, 6))
        text = CLEAN_BOARD.replace("- [ ] Expose the last outcome",
                                   "- [ ] Expose the last outcome\n" + extra)
        self.assertIn("over-budget", lint_text(text))

    def test_development_approach_over_budget_is_only_a_warning(self):
        extra = "\n".join(f"- [ ] Extra step {n}" for n in range(1, 6))
        text = CLEAN_BOARD.replace("- [ ] Expose the last outcome",
                                   "- [ ] Expose the last outcome\n" + extra)
        self.assertNotIn("over-budget", lint_errors(text))

    def test_acceptance_criteria_cap_is_a_hard_error(self):
        extra = "\n".join(f"- [ ] Extra criterion {n}" for n in range(1, 8))
        text = CLEAN_BOARD.replace("- [ ] The last outcome is queryable",
                                   "- [ ] The last outcome is queryable\n" + extra)
        self.assertIn("over-budget", lint_errors(text))

    def test_testing_approach_cap_is_a_hard_error(self):
        extra = "\n".join(f"- [ ] Extra test {n}" for n in range(1, 6))
        text = CLEAN_BOARD.replace(
            "- [ ] Kill a worker mid-run and confirm a failure outcome",
            "- [ ] Kill a worker mid-run and confirm a failure outcome\n" + extra)
        self.assertIn("over-budget", lint_errors(text))

    def test_under_budget_testing_approach(self):
        text = CLEAN_BOARD.replace(
            "- [ ] Run a job and confirm the outcome is written\n"
            "- [ ] Kill a worker mid-run and confirm a failure outcome",
            "- [ ] Run a job and confirm the outcome is written")
        self.assertIn("under-budget", lint_text(text))

    def test_plain_bullets_where_checkboxes_belong(self):
        text = CLEAN_BOARD.replace(
            "**DEVELOPMENT APPROACH**:\n"
            "- [ ] Add an outcome column\n"
            "- [ ] Write the outcome on completion\n"
            "- [ ] Expose the last outcome",
            "**DEVELOPMENT APPROACH**:\n"
            "- Add an outcome column\n"
            "- Write the outcome on completion\n"
            "- Expose the last outcome")
        self.assertIn("missing-checkboxes", lint_text(text))

    def test_long_checkbox(self):
        text = CLEAN_BOARD.replace("- [ ] Add an outcome column",
                                   "- [ ] " + "x" * 130)
        self.assertIn("long-checkbox", lint_text(text))


class TestSpineShape(unittest.TestCase):
    def test_compound_story_title_is_flagged(self):
        text = CLEAN_BOARD.replace(
            "- [ ] Record scheduler job outcomes",
            "- [ ] Fix the scheduler and rebuild the delivery queue")
        self.assertIn("compound-title", lint_text(text))

    def test_plain_story_title_is_not_flagged(self):
        self.assertNotIn("compound-title", lint_text(CLEAN_BOARD))

    def test_feature_with_no_stories(self):
        text = CLEAN_BOARD + """
---

## FEATURE-NNNN05
- [ ] Schedule Integrity
- Parent: EPIC-NNNN01

**DESCRIPTION**
````
**PURPOSE**:
Confirm schedules are correct.
````
"""
        self.assertIn("empty-feature", lint_text(text))

    def test_epic_missing_contract_sections(self):
        text = CLEAN_BOARD.replace("**OUT OF SCOPE**:\n- Report content changes\n\n", "")
        self.assertIn("epic-missing-section", lint_text(text))

    def test_epic_with_all_sections_is_clean(self):
        self.assertNotIn("epic-missing-section", lint_text(CLEAN_BOARD))

    def test_epic_sections_match_case_insensitively(self):
        text = (CLEAN_BOARD
                .replace("**OUT OF SCOPE**:", "Out of Scope")
                .replace("**END STATE**:", "End State")
                .replace("**COMPLETION EVIDENCE**:", "Completion Evidence"))
        self.assertNotIn("epic-missing-section", lint_text(text))


class TestFiller(unittest.TestCase):
    def test_clean_board_has_no_filler_findings(self):
        codes = lint_text(CLEAN_BOARD)
        self.assertNotIn("boilerplate-line", codes)
        self.assertNotIn("criterion-restates-step", codes)

    def test_line_repeated_across_three_items_is_flagged(self):
        text = CLEAN_BOARD
        for old in ("- [ ] Every run writes an outcome",
                    "- [ ] An alert fires at the threshold",
                    "- [ ] Every scheduled report is inventoried (STORY-NNNN03)"):
            text = text.replace(old, "- [ ] The item is reviewed and approved")
        self.assertIn("boilerplate-line", lint_text(text))

    def test_line_repeated_across_two_items_is_not_flagged(self):
        text = CLEAN_BOARD.replace("- [ ] Every run writes an outcome",
                                   "- [ ] An alert fires at the threshold")
        self.assertNotIn("boilerplate-line", lint_text(text))

    def test_criterion_restating_a_dev_step_is_flagged(self):
        text = CLEAN_BOARD.replace("- [ ] Every run writes an outcome",
                                   "- [ ] Add an outcome column")
        self.assertIn("criterion-restates-step", lint_text(text))


class TestLevelDiscipline(unittest.TestCase):
    def test_clean_board_has_no_level_violation(self):
        self.assertNotIn("level-violation", lint_text(CLEAN_BOARD))

    def test_feature_criterion_repeating_child_dod_is_flagged(self):
        text = CLEAN_BOARD.replace(
            "- [ ] Every scheduled report is inventoried",
            "- [ ] Every run writes an outcome")
        self.assertIn("level-violation", lint_text(text))

    def test_trace_does_not_hide_a_repeated_criterion(self):
        """The story reference must not stop the level check from matching."""
        text = CLEAN_BOARD.replace(
            "- [ ] Every scheduled report is inventoried (STORY-NNNN03)",
            "- [ ] Every run writes an outcome (STORY-NNNN03)")
        self.assertIn("level-violation", lint_text(text))


class TestTraceability(unittest.TestCase):
    def test_clean_board_is_fully_traced(self):
        codes = lint_text(CLEAN_BOARD)
        self.assertNotIn("criterion-untraced", codes)
        self.assertNotIn("criterion-misrouted", codes)
        self.assertNotIn("story-uncovered", codes)

    def test_criterion_without_a_story_reference_is_an_error(self):
        text = CLEAN_BOARD.replace(
            "- [ ] Retry behaviour is documented (STORY-NNNN04)",
            "- [ ] Retry behaviour is documented")
        self.assertIn("criterion-untraced", lint_errors(text))

    def test_criterion_pointing_outside_the_feature_is_an_error(self):
        text = CLEAN_BOARD.replace(
            "- [ ] Retry behaviour is documented (STORY-NNNN04)",
            "- [ ] Retry behaviour is documented (STORY-999999)")
        self.assertIn("criterion-misrouted", lint_errors(text))

    def test_story_no_criterion_names_is_flagged(self):
        text = CLEAN_BOARD.replace(
            "- [ ] Retry behaviour is documented (STORY-NNNN04)",
            "- [ ] Retry behaviour is documented (STORY-NNNN03)")
        text = text.replace(
            "- [ ] Delivery failures are categorised (STORY-NNNN03, STORY-NNNN04)",
            "- [ ] Delivery failures are categorised (STORY-NNNN03)")
        self.assertIn("story-uncovered", lint_text(text))

    def test_multiple_references_on_one_criterion_resolve(self):
        codes = lint_text(CLEAN_BOARD)
        self.assertNotIn("criterion-misrouted", codes)

    def test_reference_does_not_count_against_the_line_budget(self):
        long_condition = "x" * 118
        text = CLEAN_BOARD.replace(
            "- [ ] Retry behaviour is documented (STORY-NNNN04)",
            f"- [ ] {long_condition} (STORY-NNNN04)")
        self.assertNotIn("long-checkbox", lint_text(text))


class TestSpecificity(unittest.TestCase):
    def test_clean_board_is_not_flagged_vague(self):
        self.assertNotIn("vague-reference", lint_text(CLEAN_BOARD))

    def test_placeholder_phrasing_is_flagged(self):
        text = CLEAN_BOARD.replace(
            "- [ ] Add an outcome column",
            "- [ ] Update the table for each source as appropriate")
        text = text.replace("- [ ] Write the outcome on completion",
                            "- [ ] Refresh the inventory where practical")
        self.assertIn("vague-reference", lint_text(text))

    def test_glossary_requires_every_story_to_name_something(self):
        items, pf = board_lint.parse(CLEAN_BOARD)
        codes = [f[2] for f in board_lint.check(items, pf, glossary=["nonexistent_table"])]
        self.assertIn("no-named-object", codes)

    def test_glossary_satisfied_by_a_named_object(self):
        text = CLEAN_BOARD.replace("- [ ] Add an outcome column",
                                   "- [ ] Add an outcome column to meta.feed_registry")
        items, pf = board_lint.parse(text)
        errs = [f for f in board_lint.check(items, pf, glossary=["meta.feed_registry"])
                if f[2] == "no-named-object"]
        story_ids = {f[3].split()[0] for f in errs}
        self.assertNotIn("STORY-NNNN03", story_ids)

    def test_no_glossary_means_no_named_object_check(self):
        self.assertNotIn("no-named-object", lint_text(CLEAN_BOARD))


class TestCrypticWriting(unittest.TestCase):
    """The five habits that leave every fact present and none of it stated.

    Each case is drawn from a real board the user corrected by hand, so a green
    test here means the check reproduces an edit somebody actually made.
    """

    def test_clean_board_is_not_flagged(self):
        codes = lint_text(CLEAN_BOARD)
        for code in ("trailing-rationale", "role-noun", "insider-deixis",
                     "sql-comment-argues"):
            self.assertNotIn(code, codes)

    def test_trailing_rationale_is_flagged(self):
        text = CLEAN_BOARD.replace(
            "- [ ] Add an outcome column",
            "- [ ] Compare the two exports, so a difference is a finding rather "
            "than an assumption")
        self.assertIn("trailing-rationale", lint_text(text))

    def test_a_causal_clause_carrying_the_content_is_not_flagged(self):
        # "because" naming the cause IS the criterion here, not an argument for it.
        # The comma-anchored form of the same word must still fire, or this check
        # is passing because it never fires on "because" at all.
        content = CLEAN_BOARD.replace(
            "- [ ] Add an outcome column",
            "- [ ] Every run that failed because the source was unreachable is listed")
        self.assertNotIn("trailing-rationale", lint_text(content))
        argued = CLEAN_BOARD.replace(
            "- [ ] Add an outcome column",
            "- [ ] Every failed run is listed, because an absent row reads as a pass")
        self.assertIn("trailing-rationale", lint_text(argued))

    def test_purpose_may_carry_its_reasoning(self):
        # The rule is that reasoning lives in the purpose once instead of trailing
        # every criterion, so flagging it there would fight the rule it enforces.
        sentence = ("The seeds merge rather than replace, so a dropped row keeps "
                    "running")
        bare = CLEAN_BOARD.replace(
            "**DESCRIPTION**\n````\n", f"**DESCRIPTION**\n````\n{sentence}\n\n", 1)
        self.assertIn("trailing-rationale", lint_text(bare))
        purposed = CLEAN_BOARD.replace(
            "**DESCRIPTION**\n````\n",
            f"**DESCRIPTION**\n````\n**PURPOSE**: \n{sentence}\n\n", 1)
        self.assertNotIn("trailing-rationale", lint_text(purposed))

    def test_role_noun_flagged_only_when_the_real_name_is_present(self):
        bare = CLEAN_BOARD.replace("- [ ] Add an outcome column",
                                   "- [ ] Correct the register on a branch")
        self.assertNotIn("role-noun", lint_text(bare))
        named = bare.replace("- [ ] Write the outcome on completion",
                             "- [ ] Publish source-to-bronze-inventory.md")
        self.assertIn("role-noun", lint_text(named))

    def test_insider_deixis_is_flagged(self):
        text = CLEAN_BOARD.replace(
            "- [ ] Add an outcome column",
            "- [ ] Read the newest commit to find out whether the write was ours")
        self.assertIn("insider-deixis", lint_text(text))

    def test_sql_comment_that_argues_is_flagged(self):
        text = CLEAN_BOARD.replace(
            "- [ ] Add an outcome column",
            "- [ ] Export the rows\n```sql\n-- distinct source systems configured in "
            "the framework, which the register's own count is checked against\n"
            "SELECT 1;\n```")
        self.assertIn("sql-comment-argues", lint_text(text))

    def test_short_sql_label_passes(self):
        text = CLEAN_BOARD.replace(
            "- [ ] Add an outcome column",
            "- [ ] Export the rows\n```sql\n-- all schemas\nSELECT 1;\n```")
        self.assertNotIn("sql-comment-argues", lint_text(text))

    def test_original_request_is_left_alone(self):
        # The requester's own words are preserved verbatim, so they are not the
        # board's prose to correct. Asserted against the same sentence unlabelled,
        # which must fire - otherwise this passes because nothing was inserted.
        sentence = ("Give us the numbers, so a difference is a finding rather "
                    "than an assumption")
        unlabelled = CLEAN_BOARD.replace(
            "**DESCRIPTION**\n````\n", f"**DESCRIPTION**\n````\n{sentence}\n\n", 1)
        self.assertIn("trailing-rationale", lint_text(unlabelled))
        labelled = CLEAN_BOARD.replace(
            "**DESCRIPTION**\n````\n",
            f"**DESCRIPTION**\n````\n**ORIGINAL REQUEST**: \n{sentence}\n\n", 1)
        self.assertNotIn("trailing-rationale", lint_text(labelled))


class TestNamedPeople(unittest.TestCase):
    def test_clean_board_names_nobody(self):
        self.assertNotIn("named-person", lint_text(CLEAN_BOARD))
        self.assertNotIn("person-not-role", lint_text(CLEAN_BOARD))

    def test_mention_is_flagged(self):
        text = CLEAN_BOARD.replace("- [ ] Add an outcome column",
                                   "- [ ] Add an outcome column, agreed with @AB")
        self.assertIn("named-person", lint_text(text))

    def test_initials_in_a_person_context_are_flagged(self):
        text = CLEAN_BOARD.replace("- [ ] Write the outcome on completion",
                                   "- [ ] Write the outcome once confirmed with CD")
        self.assertIn("named-person", lint_text(text))

    def test_role_label_naming_a_person_is_flagged(self):
        text = CLEAN_BOARD.replace("- [ ] Add an outcome column",
                                   "**REVIEWERS**: AB\n- [ ] Add an outcome column")
        self.assertIn("person-not-role", lint_text(text))

    def test_role_label_naming_a_role_is_clean(self):
        text = CLEAN_BOARD.replace("- [ ] Add an outcome column",
                                   "**REVIEWERS**: Data Engineer\n- [ ] Add an outcome column")
        self.assertNotIn("person-not-role", lint_text(text))

    def test_domain_acronyms_are_not_mistaken_for_initials(self):
        text = CLEAN_BOARD.replace(
            "- [ ] Add an outcome column",
            "- [ ] Add an outcome column for CRM, ERP and BI loads at 05:00 CT")
        self.assertNotIn("named-person", lint_text(text))

    def test_sql_keywords_inside_a_fence_are_ignored(self):
        text = CLEAN_BOARD.replace(
            "- [ ] Add an outcome column",
            "- [ ] Add an outcome column\n```sql\nSELECT a AS b FROM t "
            "WHERE x = 1 AND y = 2 ORDER BY z\n```")
        self.assertNotIn("named-person", lint_text(text))


class TestOutOfScopeGate(unittest.TestCase):
    EPIC_WITH_EXCLUSIONS = CLEAN_BOARD.replace(
        "**OUT OF SCOPE**:\n- Report content changes",
        "**OUT OF SCOPE**:\n- Report content changes\n"
        "- Capacity planning and cost forecasting")

    def test_clean_board_has_no_overlap(self):
        self.assertNotIn("out-of-scope-overlap", lint_text(self.EPIC_WITH_EXCLUSIONS))

    def test_item_doing_excluded_work_is_flagged(self):
        text = self.EPIC_WITH_EXCLUSIONS.replace(
            "- [ ] Add an outcome column",
            "- [ ] Produce the capacity planning and cost forecasting model")
        self.assertIn("out-of-scope-overlap", lint_text(text))

    def test_scope_boundary_may_name_an_exclusion(self):
        text = self.EPIC_WITH_EXCLUSIONS.replace(
            "**PRIMARY OWNER**: Platform Engineer",
            "**SCOPE BOUNDARY**:\nCapacity planning and cost forecasting are excluded.\n\n"
            "**PRIMARY OWNER**: Platform Engineer")
        self.assertNotIn("out-of-scope-overlap", lint_text(text))

    def test_shared_vocabulary_does_not_flag(self):
        # "report" appears in both the epic's in-scope wording and an exclusion.
        self.assertNotIn("out-of-scope-overlap", lint_text(CLEAN_BOARD))


class TestCycles(unittest.TestCase):
    def test_dag_has_no_cycles(self):
        self.assertEqual(board_lint.find_cycles({"a": ["b"], "b": ["c"], "c": []}), [])

    def test_cycle_is_found(self):
        cycles = board_lint.find_cycles({"a": ["b"], "b": ["a"]})
        self.assertTrue(cycles)
        self.assertIn("a", cycles[0])


class TestScaffoldUnits(unittest.TestCase):
    def test_scratch_regime_counts_from_zero(self):
        spine = {"epics": [{"title": "E", "features": [
            {"title": "F", "stories": [{"title": "S1"}, {"title": "S2"}]}]}]}
        nodes = board_scaffold.walk(spine)
        gapfill = board_scaffold.assign_ids(nodes)
        self.assertFalse(gapfill)
        self.assertEqual([n["_id"] for _, n, _ in nodes],
                         ["000000", "000001", "000002", "000003"])

    def test_gapfill_regime_uses_nnnn(self):
        spine = {"epics": [{"id": REAL_ID, "title": "E", "features": [
            {"title": "F", "stories": [{"title": "S"}]}]}]}
        nodes = board_scaffold.walk(spine)
        gapfill = board_scaffold.assign_ids(nodes)
        self.assertTrue(gapfill)
        self.assertEqual([n["_id"] for _, n, _ in nodes],
                         [REAL_ID, "NNNN01", "NNNN02"])

    def test_given_ids_are_preserved(self):
        spine = {"epics": [{"id": "NNNN01", "title": "E", "features": [
            {"id": "NNNN02", "title": "F", "stories": []}]}]}
        nodes = board_scaffold.walk(spine)
        board_scaffold.assign_ids(nodes)
        self.assertEqual([n["_id"] for _, n, _ in nodes], ["NNNN01", "NNNN02"])

    def test_duplicate_ids_rejected(self):
        spine = {"epics": [{"id": "NNNN01", "title": "E", "features": [
            {"id": "NNNN01", "title": "F", "stories": []}]}]}
        with self.assertRaises(board_scaffold.SpineError):
            board_scaffold.assign_ids(board_scaffold.walk(spine))

    def test_bad_id_form_rejected(self):
        spine = {"epics": [{"id": "nope", "title": "E"}]}
        with self.assertRaises(board_scaffold.SpineError):
            board_scaffold.assign_ids(board_scaffold.walk(spine))

    def test_missing_title_rejected(self):
        with self.assertRaises(board_scaffold.SpineError):
            board_scaffold.walk({"epics": [{"features": []}]})

    def test_missing_epics_rejected(self):
        with self.assertRaises(board_scaffold.SpineError):
            board_scaffold.walk({"stories": []})

    def test_depends_rendering(self):
        """No predecessor means no line at all, rather than a line reading 'none'."""
        self.assertEqual(board_scaffold.depends_line({}), "")
        self.assertEqual(
            board_scaffold.depends_line({"depends": "STORY-1"}), "- Predecessor: STORY-1\n")
        self.assertEqual(
            board_scaffold.depends_line({"depends": ["A", "B"]}), "- Predecessor: A, B\n")


class TestScaffoldLintContract(unittest.TestCase):
    """The load-bearing invariant: generated structure is structurally valid."""

    SPINE = {"epics": [{"id": "NNNN01", "title": "Reporting Stability", "features": [
        {"id": "NNNN02", "title": "Delivery Reliability", "stories": [
            {"id": "NNNN03", "title": "Record job outcomes"},
            {"title": "Alert on repeated failures", "depends": ["STORY-NNNN03"]},
        ]},
        {"title": "Schedule Integrity", "stories": [{"title": "Inventory schedules"}]},
    ]}]}

    def test_scaffold_output_has_no_structural_errors(self):
        text = board_scaffold.render(json.loads(json.dumps(self.SPINE)))
        errors = lint_errors(text)
        structural = [c for c in errors if c != "template-residue"]
        self.assertEqual(structural, [], f"unexpected structural errors: {structural}")

    def test_scaffold_output_still_flags_its_own_residue(self):
        text = board_scaffold.render(json.loads(json.dumps(self.SPINE)))
        self.assertIn("template-residue", lint_errors(text))

    def test_render_is_deterministic(self):
        a = board_scaffold.render(json.loads(json.dumps(self.SPINE)))
        b = board_scaffold.render(json.loads(json.dumps(self.SPINE)))
        self.assertEqual(a, b)

    def test_placeholders_do_not_collide_with_given_ids(self):
        text = board_scaffold.render(json.loads(json.dumps(self.SPINE)))
        self.assertNotIn("duplicate-id", lint_errors(text))


class TestCli(unittest.TestCase):
    def run_script(self, name, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / name), *args],
            capture_output=True, text=True)

    def test_scaffold_refuses_to_overwrite_an_existing_board(self):
        """A board carries tracker IDs and hand edits. Truncating one silently
        is the loss this guard exists to prevent."""
        with tempfile.TemporaryDirectory() as tmp:
            spine = Path(tmp) / "spine.json"
            spine.write_text(json.dumps(
                {"epics": [{"id": "NNNN01", "title": "E", "features": []}]}),
                encoding="utf-8")
            out = Path(tmp) / "board.md"
            out.write_text("PRECIOUS", encoding="utf-8")
            proc = self.run_script(
                "board_scaffold.py", str(spine), "-o", str(out))
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("exists", proc.stderr)
            self.assertEqual(out.read_text(encoding="utf-8"), "PRECIOUS")

    def test_scaffold_overwrites_with_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            spine = Path(tmp) / "spine.json"
            spine.write_text(json.dumps(
                {"epics": [{"id": "NNNN01", "title": "E", "features": []}]}),
                encoding="utf-8")
            out = Path(tmp) / "board.md"
            out.write_text("PRECIOUS", encoding="utf-8")
            proc = self.run_script(
                "board_scaffold.py", str(spine), "-o", str(out), "--force")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("EPIC-NNNN01", out.read_text(encoding="utf-8"))

    def test_lint_exit_zero_on_clean_board(self):
        with tempfile.TemporaryDirectory() as tmp:
            board = Path(tmp) / "board.md"
            board.write_text(CLEAN_BOARD, encoding="utf-8")
            proc = self.run_script("board_lint.py", str(board))
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_lint_exit_one_on_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            board = Path(tmp) / "board.md"
            board.write_text(CLEAN_BOARD.replace("STORY-NNNN04", "STORY-NNNN03"),
                             encoding="utf-8")
            proc = self.run_script("board_lint.py", str(board))
            self.assertEqual(proc.returncode, 1)
            self.assertIn("duplicate-id", proc.stdout)

    def test_lint_exit_two_on_missing_file(self):
        proc = self.run_script("board_lint.py", "/nonexistent/board.md")
        self.assertEqual(proc.returncode, 2)

    def test_lint_json_output_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            board = Path(tmp) / "board.md"
            board.write_text(CLEAN_BOARD, encoding="utf-8")
            proc = self.run_script("board_lint.py", str(board), "--json")
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["errors"], 0)
            self.assertEqual(payload["items"], 4)
            self.assertIn("findings", payload)

    def test_scaffold_writes_file_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            spine = Path(tmp) / "spine.json"
            spine.write_text(json.dumps(TestScaffoldLintContract.SPINE), encoding="utf-8")
            out = Path(tmp) / "board.md"
            first = self.run_script("board_scaffold.py", str(spine), "-o", str(out))
            self.assertEqual(first.returncode, 0, first.stderr)
            once = out.read_bytes()
            self.run_script("board_scaffold.py", str(spine), "-o", str(out))
            self.assertEqual(once, out.read_bytes())

    def test_scaffold_rejects_bad_spine(self):
        with tempfile.TemporaryDirectory() as tmp:
            spine = Path(tmp) / "spine.json"
            spine.write_text('{"epics": [{"features": []}]}', encoding="utf-8")
            proc = self.run_script("board_scaffold.py", str(spine))
            self.assertEqual(proc.returncode, 2)
            self.assertIn("title", proc.stderr)

    def test_scaffold_then_lint_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            spine = Path(tmp) / "spine.json"
            spine.write_text(json.dumps(TestScaffoldLintContract.SPINE), encoding="utf-8")
            out = Path(tmp) / "board.md"
            self.run_script("board_scaffold.py", str(spine), "-o", str(out))
            proc = self.run_script("board_lint.py", str(out), "--json")
            payload = json.loads(proc.stdout)
            codes = {f["code"] for f in payload["findings"] if f["severity"] == "error"}
            self.assertEqual(codes, {"template-residue"})


if __name__ == "__main__":
    unittest.main()
