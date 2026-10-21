"""Offline span checks, failed-trial replay and explicit semantic limitations."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import semantic_quality as quality
import semantic_relation_spans as spans
import semantic_relations as legacy


class SpanContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.controls = json.loads((ROOT / "tests/fixtures/semantic-relation-spans-v3.json").read_text(encoding="utf-8"))
        cls.observed_path = ROOT / "tests/fixtures/semantic-relations-v2-armA.json"
        cls.observed_bytes = cls.observed_path.read_bytes()
        cls.observed = json.loads(cls.observed_bytes)

    def test_authored_positive_representations_include_bilingual_gaps_and_repeated_literals(self):
        self.assertEqual(len(self.controls["positive_cases"]), 4)
        for case in self.controls["positive_cases"]:
            with self.subTest(case=case["id"]):
                self.assertEqual(spans.checked(case["response"], case["pairs"]), case["response"])
                result = spans.coverage(case["response"], case["pairs"])
                self.assertTrue(result["literal_context_coverage_complete"])
                self.assertFalse(result["quality_passed"])
                self.assertFalse(result["protocol_validated"])

    def test_new_structural_negatives_are_rejected_with_predeclared_errors(self):
        self.assertEqual(len(self.controls["structural_negatives"]), 25)
        for case in self.controls["structural_negatives"]:
            with self.subTest(case=case["id"]):
                with self.assertRaisesRegex(ValueError, "^" + case["expected_error"] + "$"):
                    spans.checked(case["response"], case["pairs"])

    def test_literal_validity_alone_does_not_detect_semantic_counterexamples(self):
        self.assertEqual(len(self.controls["semantic_boundaries"]), 3)
        for case in self.controls["semantic_boundaries"]:
            with self.subTest(case=case["id"]):
                self.assertEqual(case["oracle_expected"], "different")
                self.assertEqual(case["response"]["pairs"]["pair_0"]["status"], "equivalent")
                evidence = spans.coverage(case["response"], case["pairs"])
                result = quality.decide(execution_completed=True, model_status="model_screened", requested_pages=[1],
                    image_pages=[1], uncertain_count=0, relation_witness_coverage_complete=evidence["literal_context_coverage_complete"],
                    known_regressions=[])
                self.assertEqual(result["quality_status"], "blocked_unvalidated_protocol")
                self.assertFalse(result["quality_passed"])
                self.assertFalse(result["promotion_allowed"])

    def test_exact_lift_preserves_ten_valid_and_two_invalid_old_replies_without_regrading(self):
        old_valid, lifted_valid, old_errors, lift_errors = [], [], {}, {}
        for key, pair in self.observed["pairs"].items():
            pairs, raw = {key: pair}, {"pairs": {key: self.observed["response"]["pairs"][key]}}
            try:
                legacy.checked(raw, pairs)
                old_valid.append(key)
            except ValueError as error:
                old_errors[key] = str(error)
            try:
                spans.lift_v2_exact(raw, pairs)
                lifted_valid.append(key)
            except ValueError as error:
                lift_errors[key] = str(error)
        self.assertEqual(len(old_valid), 10)
        self.assertEqual(old_valid, lifted_valid)
        self.assertEqual(old_errors, {"pair_817049": "RELATION_ROLE_ANCHOR_NOT_FOUND", "pair_145184": "RELATION_ROLE_ANCHOR_NOT_FOUND"})
        self.assertEqual(lift_errors, {"pair_817049": "LEGACY_ROLE_NOT_VERBATIM", "pair_145184": "LEGACY_ROLE_NOT_VERBATIM"})
        self.assertEqual(self.observed_path.read_bytes(), self.observed_bytes)
    def test_archived_native_reply_hash_matches_the_retained_fixture_provenance(self):
        from evidence_support import evidence_file
        public = evidence_file("benchmarks/l1quad-2026-10-15/rc5/relation-pilot/arm-A-response.json")
        self.assertEqual(hashlib.sha256(public.read_bytes()).hexdigest(), self.observed["provenance"]["response_file_sha256"])

    def test_d04_new_authored_span_example_does_not_repair_the_original_response(self):
        key = "pair_145184"
        original = self.observed["response"]["pairs"][key]
        self.assertEqual(original["alignments"][1]["target_predicate"], "可以使用")
        case = next(c for c in self.controls["positive_cases"] if c["id"] == "D04-human-multispan-demonstration")
        self.assertEqual(case["pairs"], {key: self.observed["pairs"][key]})
        evidence = case["response"]["pairs"][key]["alignments"][1]["target"]
        self.assertEqual([x["text"] for x in evidence["roles"]["predicate"]], ["可以", "使用"])
        self.assertEqual(evidence["attachments"], [{"kind": "reference_scope", "head": "predicate", "span": evidence["attachments"][0]["span"]}])
        self.assertEqual(evidence["attachments"][0]["span"]["text"], "在{v3}中")
        spans.checked(case["response"], case["pairs"])
        with self.assertRaisesRegex(ValueError, "LEGACY_ROLE_NOT_VERBATIM"):
            spans.lift_v2_exact({"pairs": {key: original}}, case["pairs"])

    def test_d02_missing_quote_evidence_survives_even_a_vacuous_literal_role_probe(self):
        key = "pair_817049"
        pair = self.observed["pairs"][key]
        old = self.observed["response"]["pairs"][key]
        for side, expected in [("source", (371, 319)), ("target", (112, 97))]:
            result = legacy._coverage(pair[side], [claim[side + "_quote"] for claim in old["alignments"]])
            self.assertEqual((result["lexical_characters"], result["covered_characters"]), expected)
            self.assertFalse(result["complete"])
        # Deliberately vacuous authored representation, only to isolate the
        # coverage invariant. It is not a replacement or a repaired model reply.
        row = {"status": old["status"], "summary": "Coverage-only offline probe.", "alignments": []}
        for claim in old["alignments"]:
            item = {"kind": claim["kind"], "status": claim["status"], "explanation": "Not semantic evidence: coverage-only probe."}
            for side in ("source", "target"):
                quote = claim[side + "_quote"]
                start, end = legacy._span(pair[side], quote, side.upper())
                literal = {"start": start, "end": end, "text": quote}
                item[side] = {"context": literal, "roles": {"subject": [], "predicate": [copy.deepcopy(literal)], "object": []}, "attachments": []}
            row["alignments"].append(item)
        probe = {"protocol": spans.PROTOCOL, "contract_version": spans.CONTRACT_VERSION, "pairs": {key: row}}
        with self.assertRaisesRegex(ValueError, "INCOMPLETE_SPAN_SOURCE_COVERAGE"):
            spans.checked(probe, {key: pair})

    def test_known_d02_regression_remains_a_veto_regardless_of_model_or_contract_claims(self):
        fixture = ROOT / "tests/fixtures/semantic-known-failures.json"
        document = json.loads(fixture.read_text(encoding="utf-8"))["source_document_sha256"]
        failures = quality.known_failures({"pair_817049": self.observed["pairs"]["pair_817049"]}, quality.load_corpora([fixture]), document)
        self.assertEqual([x["case_id"] for x in failures], ["D02"])
        for claimed_validated in (False, True):
            result = quality.decide(execution_completed=True, model_status="model_screened", requested_pages=[5], image_pages=[5],
                uncertain_count=0, relation_witness_coverage_complete=True, known_regressions=failures,
                protocol_validated=claimed_validated)
            self.assertEqual(result["quality_status"], "blocked_known_regression")
            self.assertFalse(result["quality_passed"])

    def test_unicode_offsets_disambiguate_repeated_words_without_normalization(self):
        case = next(c for c in self.controls["positive_cases"] if c["id"] == "new-repeated-literal-and-unicode")
        text = case["pairs"]["pair_0"]["target"]
        subject = case["response"]["pairs"]["pair_0"]["alignments"][0]["target"]["roles"]["subject"][0]
        self.assertEqual(text.count(subject["text"]), 2)
        self.assertEqual(text[subject["start"]:subject["end"]], subject["text"])
        self.assertEqual(subject["start"], text.rindex("继电器"))

    def test_opaque_tokens_require_whole_literal_coverage(self):
        result = spans._coverage("left {v1} right", [(0, 5), (10, 15)])
        self.assertFalse(result["complete"])
        self.assertEqual(result["uncovered_excerpt"], "{v1}")

    def test_versioned_schema_has_explicit_offsets_and_explanations_are_not_span_fields(self):
        pair = self.controls["positive_cases"][0]["pairs"]
        schema = spans.schema(pair)
        self.assertEqual(schema["properties"]["contract_version"]["enum"], ["3.0.0-draft.1"])
        self.assertEqual(schema["properties"]["protocol"]["enum"], ["relations-spans-v3"])
        claim = schema["properties"]["pairs"]["properties"]["pair_0"]["properties"]["alignments"]["items"]
        subject = claim["properties"]["source"]["properties"]["roles"]["properties"]["subject"]["items"]
        self.assertEqual(set(subject["required"]), {"start", "end", "text"})
        self.assertNotIn("explanation", subject["properties"])


if __name__ == "__main__":
    unittest.main()
