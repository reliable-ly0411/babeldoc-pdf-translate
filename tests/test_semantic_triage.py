"""Offline minimal triage/location checks; historical labels are not reruns."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import semantic_quality as quality
import chat_bridge as bridge
spec = importlib.util.spec_from_file_location("semantic_triage", ROOT / "experiments/semantic_triage.py")
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)


class MinimalTriageTests(unittest.TestCase):
    def setUp(self):
        self.unit = {"source": "The valve near the pump opens.", "target": "泵旁的阀门打开。"}
        self.packet = t.build([self.unit])

    def response(self, verdict):
        return {"units": {"u0": {"verdict": verdict}}}

    def test_model_task_has_only_verdict_no_location_explanation_or_reference_answer(self):
        schema = self.packet["request"]["schema"]["properties"]["units"]["properties"]["u0"]
        self.assertEqual(set(schema["properties"]), {"verdict"})
        self.assertEqual(schema["properties"]["verdict"]["enum"], ["equivalent", "different", "uncertain"])
        self.assertNotIn("bindings", self.packet["request"]["prompt"])
        with self.assertRaisesRegex(ValueError, "SOURCE_TARGET_ONLY"):
            t.build([{**self.unit, "expected": "equivalent"}])

    def test_independent_unit_default_and_same_source_answer_alternatives_forbidden(self):
        alternative = {**self.unit, "target": "阀门旁的泵打开。"}
        with self.assertRaisesRegex(ValueError, "INDEPENDENT_UNIT_REQUIRED"):
            t.build([self.unit, alternative])
        with self.assertRaisesRegex(ValueError, "SAME_SOURCE_ALTERNATIVES_FORBIDDEN"):
            t.build([self.unit, alternative], diagnostic_batch=True)

    def test_all_three_verdicts_retained_but_extra_explanation_or_units_rejected(self):
        for verdict in t.VERDICTS:
            self.assertEqual(t.checked(self.response(verdict), self.packet), self.response(verdict))
        for response in ({"units": {"u0": {"verdict": "equivalent", "reason": "extra"}}}, {"units": {}}, {"units": {"u0": {"verdict": "yes"}}}):
            with self.assertRaises(ValueError):
                t.checked(response, self.packet)

    def test_receipt_binding_cannot_be_reused_for_changed_target(self):
        actual = t.receipts(self.response("equivalent"), self.packet)
        other = t.build([{**self.unit, "target": "泵已经打开。"}])
        self.assertEqual(t.gate(actual, other["bindings"])["quality_status"], "blocked_missing_or_changed_unit")

    def test_uncertain_and_different_never_trigger_automatic_repair_or_acceptance(self):
        for verdict, expected in [("uncertain", "blocked_uncertainty"), ("different", "needs_evidence_review"), ("equivalent", "blocked_unvalidated_protocol")]:
            result = t.gate(t.receipts(self.response(verdict), self.packet), self.packet["bindings"])
            self.assertEqual(result["quality_status"], expected)
            self.assertFalse(result["quality_passed"])
            self.assertFalse(result["automatic_repair_allowed"])

    def test_even_validated_clear_model_receipts_need_independent_acceptance(self):
        result = t.gate(t.receipts(self.response("equivalent"), self.packet), self.packet["bindings"], protocol_validated=True)
        self.assertEqual(result["quality_status"], "screened_pending_independent_acceptance")
        self.assertFalse(result["quality_passed"])
        self.assertFalse(result["promotion_allowed"])

    def test_program_locates_literal_fragments_and_keeps_reference_gap(self):
        result = t.locate_fragments("我们可以在{v3}中使用{v2}", ["可以", "使用"])
        self.assertEqual(result["status"], "located")
        self.assertEqual([span["text"] for span in result["spans"]], ["可以", "使用"])
        self.assertEqual([gap["text"] for gap in result["gaps"]], ["在{v3}中"])
        self.assertTrue(result["needs_semantic_review"])
        self.assertFalse(result["quality_passed"])

    def test_generated_concatenation_is_not_reconstructed_as_evidence(self):
        self.assertEqual(t.locate_fragments("我们可以在{v3}中使用", ["可以使用"])["status"], "not_found")

    def test_ambiguous_repeated_words_are_not_assigned_first_occurrence(self):
        self.assertEqual(t.locate_fragments("The pump is beside another pump.", ["pump"])["status"], "ambiguous")

    def test_negation_gaps_order_unicode_and_whole_markers_are_preserved(self):
        result = t.locate_fragments("🙂 It can not open {v1}.", ["can", "open"])
        self.assertEqual(result["gaps"][0]["text"], " not ")
        self.assertEqual(result["spans"][0]["start"], 5)
        self.assertEqual(t.locate_fragments("can open", ["open", "can"])["status"], "overlapping_or_out_of_order")
        self.assertEqual(t.locate_fragments("open {v1}", ["v1"])["status"], "partial_opaque_token")
        self.assertEqual(t.OPAQUE.pattern, bridge.MARKER.pattern)

    def test_long_units_require_explicit_segmentation_without_automatic_text_cutting(self):
        with self.assertRaisesRegex(ValueError, "UNIT_REQUIRES_SEGMENTATION"):
            t.build([{**self.unit, "source": "x" * 1201}])

    def test_generic_known_failure_veto_still_blocks_an_equivalent_declaration(self):
        path = ROOT / "tests/fixtures/semantic-known-failures.json"
        corpus = json.loads(path.read_text(encoding="utf-8"))
        failed = corpus["failures"][0]
        packet = t.build([{"source": failed["source"], "target": failed["target"]}])
        hits = quality.known_failures({"pair_0": {"source": failed["source"], "target": failed["target"]}}, quality.load_corpora([path]), corpus["source_document_sha256"])
        result = t.gate(t.receipts(self.response("equivalent"), packet), packet["bindings"], known_regressions=hits)
        self.assertEqual(result["quality_status"], "blocked_known_regression")

    def test_no_units_or_missing_units_cannot_be_a_complete_screen(self):
        for actual, expected in [({}, {}), ({}, self.packet["bindings"])]:
            result = t.gate(actual, expected)
            self.assertEqual(result["quality_status"], "blocked_missing_or_changed_unit")
            self.assertFalse(result["complete_bound_receipts"])

    def test_three_semantic_boundaries_remain_unknown_to_this_syntax_checker(self):
        controls = json.loads((ROOT / "tests/fixtures/semantic-relation-spans-v3.json").read_text(encoding="utf-8"))
        for case in controls["semantic_boundaries"]:
            packet = t.build([case["pairs"]["pair_0"]])
            self.assertEqual(case["oracle_expected"], "different")
            self.assertEqual(t.checked(self.response("equivalent"), packet), self.response("equivalent"))
            self.assertFalse(t.gate(t.receipts(self.response("equivalent"), packet), packet["bindings"])["quality_passed"])


if __name__ == "__main__":
    unittest.main()
