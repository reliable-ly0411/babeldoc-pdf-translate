"""Independent review counterexamples through actual patch/adapter/checker code."""
import copy
import html
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import pymupdf as fitz
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import chat_bridge
import final_audit as audit
import pdf_pipeline as pipeline
import repair_objects
import translation_contract as contracts
import visual_review as visual
import semantic_offline_support as semantic_fake

CLEAR = {"verdict": "clear", "issues": []}
PROVIDER = {"type": "codex", "model": "offline-vision", "vision": True, "retries": 0, "timeout_seconds": 30}


def pdf(path, texts, *, unknown_font=False):
    with fitz.open() as doc:
        for text in texts:
            page = doc.new_page(width=420, height=240)
            if unknown_font:
                page.insert_font(fontname="UnknownFixture", fontbuffer=fitz.Font("cour").buffer)
                page.insert_text((30, 65), text, fontsize=13, fontname="UnknownFixture")
            else:
                page.insert_htmlbox((30, 48, 390, 100), "<p>" + html.escape(text) + "</p>",
                    css="body {font-family:sans-serif;font-size:13pt;margin:0;} p {margin:0;}")
        doc.save(path)


class Vision:
    def __init__(self, issue):
        self.issue = issue
        self.prompts = []

    def doctor(self):
        return {"ready": True, "native_version": "offline-no-model"}

    def inspect(self, prompt, images, timeout, schema=None):
        self.prompts.append(prompt)
        schema = schema or visual.SCHEMA
        if "before" in schema["properties"]:
            identifiers = schema["properties"]["before"]["properties"]["issues"]["items"]["properties"]["region_id"]["enum"]
            identifier = next(item for item in identifiers if item != "page_context")
            value = {"before": {"issues": [{**self.issue, "region_id": identifier, "replacement": ""}]}, "after": {"issues": []}}
        else:
            value = {"issues": [self.issue]}
        return value, {"input_tokens": 1, "output_tokens": 1}


class ReviewBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="terminal-boundary-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(chat_bridge.NativeClient, "invoke", side_effect=AssertionError("REAL MODEL FORBIDDEN")).start()

    def bundle(self, folder, text, *, unknown_font=False):
        folder.mkdir()
        source, mono, dual = (folder / name for name in ("source.pdf", "before.mono.pdf", "before.dual.pdf"))
        pdf(source, [text], unknown_font=unknown_font)
        shutil.copyfile(source, mono)
        visual.bilingual(source, mono, dual)
        with fitz.open(mono) as doc:
            region = visual.regions(doc[0])[0]
            self.assertIn(text, doc[0].get_text().replace("\n", " "))
        return source, {"mono": mono, "dual": dual}, region

    def issue(self, region, replacement):
        return {"region_id": region["id"], "category": "translation", "severity": "major",
            "reason": "Offline untranslated prose counterexample.", "replacement": replacement}

    def test_unicode_and_ambiguous_math_cannot_enter_real_plain_patch_or_terminal_adapter(self):
        variants = [("Use x² as a bound.", "使用 x³ 作为界。"),
            ("Use x₂ as a bound.", "使用 x₃ 作为界。"),
            ("Use xⁿ as a bound.", "使用 xᵐ 作为界。"),
            ("Use xᵢ as a bound.", "使用 xⱼ 作为界。"),
            ("Use α as a bound.", "使用 β 作为界。"),
            ("Use x as a bound.", "使用 y 作为界。")]
        for number, (text, replacement) in enumerate(variants):
            with self.subTest(text=text):
                folder = self.root / ("math-%d" % number)
                source, before, region = self.bundle(folder, text)
                issue = self.issue(region, replacement)
                with fitz.open(before["mono"]) as doc:
                    self.assertFalse(visual.repairable(doc[0], region, issue))
                self.assertEqual(visual.patch_pdf(before["mono"], folder / "illegal.pdf", 1, [region], [issue], 1), [])
                client = Vision(issue)
                output = folder / "adapter"; output.mkdir()
                budget = audit.Budget(6, 60)
                finding = {"id": "f", "page": 1, **{key: value for key, value in issue.items() if key != "replacement"}}
                hashes = {key: audit.sha(path) for key, path in before.items()}
                with mock.patch.object(visual, "NativeVision", return_value=client):
                    with self.assertRaisesRegex(ValueError, "FINAL_FINDINGS_NOT_REPAIRED"):
                        audit.visual_repairer(PROVIDER, mock.Mock(capability_verified=True))(source, before, [finding], budget, output)
                self.assertEqual(budget.calls, 1)
                report = json.loads((output / "visual-repair/review-report.json").read_text(encoding="utf-8"))
                self.assertFalse(report["pages"][0]["accepted_repairs"])
                self.assertEqual(hashes, {key: audit.sha(path) for key, path in before.items()})

    def test_unknown_font_is_not_certified_as_plain_prose(self):
        source, before, region = self.bundle(self.root / "unknown", "Temperature is controlled.", unknown_font=True)
        issue = self.issue(region, "温度受到控制。")
        with fitz.open(source) as doc:
            result = repair_objects.inspect(doc[0], region["bbox"])
            self.assertFalse(result["passed"])
            self.assertIn("unknown_or_math_font", result["reasons"])
            self.assertFalse(visual.repairable(doc[0], region, issue))
        output = self.root / "unknown-adapter"; output.mkdir()
        client = Vision(issue)
        finding = {"id": "f", "page": 1, **{key: value for key, value in issue.items() if key != "replacement"}}
        with mock.patch.object(visual, "NativeVision", return_value=client):
            with self.assertRaisesRegex(ValueError, "FINAL_FINDINGS_NOT_REPAIRED"):
                audit.visual_repairer(PROVIDER, mock.Mock(capability_verified=True))(source, before, [finding], audit.Budget(6, 60), output)

    def test_independent_postcheck_cannot_certify_changed_exponent_even_with_claimed_evidence(self):
        for number, (old, new) in enumerate((("x²", "x³"), ("x₂", "x₃"), ("xⁿ", "xᵐ"))):
            with self.subTest(old=old):
                folder = self.root / ("post-%d" % number)
                source, before, region = self.bundle(folder, "Use " + old + " as a bound.")
                mono, dual = folder / "changed.mono.pdf", folder / "changed.dual.pdf"
                pdf(mono, ["使用 " + new + " 作为界。"])
                visual.bilingual(source, mono, dual)
                after = {"mono": mono, "dual": dual}
                finding = {"id": "f", "page": 1, "region_id": region["id"]}
                edits = [{"page": 1, "region_id": region["id"], "bbox": region["bbox"], "method": "bounded_plain_prose"}]
                evidence = audit.repair_object_evidence(source, before, after, edits)
                result = audit.program_revalidate(source, before, after, [finding], {"repair_evidence": evidence})
                self.assertFalse(result["math_objects_passed"])
                self.assertFalse(result["passed"])
                self.assertTrue(result["narrow_operator_screen_passed"])
                forged = copy.deepcopy(evidence)
                forged["edits"][0]["object_proof"]["passed"] = True
                self.assertFalse(audit.program_revalidate(source, before, after, [finding], {"repair_evidence": forged})["math_objects_passed"])

    def test_plain_prose_actual_adapter_and_independent_object_revalidation_pass(self):
        source, before, region = self.bundle(self.root / "plain", "Temperature is controlled.")
        issue = self.issue(region, "温度受到控制。")
        client = Vision(issue); output = self.root / "plain-adapter"; output.mkdir()
        finding = {"id": "f", "page": 1, **{key: value for key, value in issue.items() if key != "replacement"}}
        with mock.patch.object(visual, "NativeVision", return_value=client):
            revised = audit.visual_repairer(PROVIDER, mock.Mock(capability_verified=True))(source, before, [finding], audit.Budget(6, 60), output)
        result = audit.program_revalidate(source, before, revised["artifacts"], [finding], revised)
        self.assertTrue(result["math_objects_passed"])
        self.assertTrue(result["passed"])
        self.assertFalse(audit.program_revalidate(source, before, revised["artifacts"], [finding], {})["math_objects_passed"])

    def pipeline_case(self, count, translation_pages, review_pages, *, preference=False, terminal_repair=False, mutate_preferences=False):
        source, mono = self.root / "source.pdf", self.root / "translated.pdf"
        pdf(source, ["Temperature is controlled."] * count)
        pdf(mono, ["Temperature is controlled."] * count)
        job = {"input": "source.pdf", "output": "translation", "source_language": "en", "target_language": "zh-CN",
            "pages": translation_pages, "outputs": "both", "provider": {"type": "codex", "model": "offline-text"}}
        if preference:
            (self.root / "prompt.txt").write_text("USER_PREFERENCE_9472 use approved terminology.", encoding="utf-8")
            (self.root / "terms.csv").write_text("source,target\ntemperature,温度USER_PREFERENCE_9472\n", encoding="utf-8")
            job.update(prompt_file="prompt.txt", glossaries=["terms.csv"])
        config = {"translation_job": "job.json", "output": "output", "review": {"provider": PROVIDER,
            "pages": review_pages, "limits": {"max_model_calls": 40}, "repair": True}}
        audit.save(self.root / "job.json", job); audit.save(self.root / "pipeline.json", config)
        def translate(path, engine, execute=False):
            if not execute:
                return {"provider": job["provider"], "arguments": ["--files", str(source)]}
            return {"status": "needs-review", "output_validation": {"files": [{"kind": "mono", "valid": True, "file": str(mono)}]}}
        def reviewed(cfg):
            cfg["output"].mkdir(); shutil.copyfile(mono, cfg["output"] / "best.mono.pdf")
            visual.bilingual(source, mono, cfg["output"] / "best.dual.pdf")
            return {"status": "sample_model_screened", "execution_status": "completed", "quality_status": "pending",
                "selected_pages": cfg["pages"], "model_calls": 0, "vision_capability_verified": True}
        seen = []
        with fitz.open(mono) as doc:
            region = visual.regions(doc[0])[0]
        issue = self.issue(region, "温度受到控制。")
        client = Vision(issue)
        def auditor(packet, budget):
            seen.append(copy.deepcopy(packet))
            if mutate_preferences:
                (self.root / "prompt.txt").write_text("Changed during terminal audit.", encoding="utf-8")
            value = {"verdict": "defects", "issues": [{key: value for key, value in issue.items() if key != "replacement"}]} if terminal_repair and len(seen) == 1 else CLEAR
            return budget.invoke("offline-only", lambda timeout: (value, {"input_tokens": 1}))
        auditor.capability_verified = True
        hook = audit.make_pipeline_hook(auditor, repairer=audit.visual_repairer(PROVIDER, auditor) if terminal_repair else None,
            revalidate=audit.program_revalidate if terminal_repair else None, max_repair_rounds=int(terminal_repair))
        real_run = visual.run
        def routed(cfg, *args, **kwargs):
            return real_run(cfg, *args, **kwargs) if cfg.get("strict_repair_objects") else reviewed(cfg)
        with mock.patch.object(pipeline.translate, "run_job", side_effect=translate), mock.patch.object(visual, "run", side_effect=routed), mock.patch.object(visual, "NativeVision", return_value=client):
            result = pipeline.run(self.root / "pipeline.json", "offline", True, final_audit_hook=hook)
        return result, seen, client

    def test_translation_all_pages_visual_sample_does_not_hide_untranslated_page(self):
        result, seen, _ = self.pipeline_case(2, "1,2", [1])
        self.assertEqual(result["translation_pages"], [1, 2]); self.assertEqual(result["review_pages"], [1])
        self.assertEqual([packet["page"] for packet in seen], [1, 2])
        metadata = json.loads(seen[1]["prompt"].split("\n")[-1])
        self.assertEqual(metadata["translated_pages"], [1, 2])
        self.assertEqual(result["final_audit"]["receipt"]["translated_pages"], [1, 2])
        self.assertFalse(result["delivery_allowed"])

    def test_translate_only_page5_but_inspect_whole_container(self):
        result, seen, _ = self.pipeline_case(6, "5", list(range(1, 7)))
        self.assertEqual(result["translation_pages"], [5]); self.assertEqual(result["review_pages"], list(range(1, 7)))
        self.assertEqual([packet["page"] for packet in seen], list(range(1, 7)))
        self.assertTrue(all(json.loads(packet["prompt"].split("\n")[-1])["translated_pages"] == [5] for packet in seen))
        self.assertEqual(result["final_audit"]["receipt"]["translated_pages"], [5])

    def test_original_preferences_reach_real_terminal_adapter_followup_and_fresh_audit(self):
        result, seen, client = self.pipeline_case(1, "1", [1], preference=True, terminal_repair=True)
        self.assertEqual(result["final_audit"]["repair_rounds"], 1, result["final_audit"])
        self.assertEqual(len(seen), 2)
        self.assertTrue(all("USER_PREFERENCE_9472" in packet["prompt"] for packet in seen))
        self.assertTrue(all("USER_PREFERENCE_9472" in prompt for prompt in client.prompts))
        self.assertEqual(len(client.prompts), 2)
        contract = result["translation_contract"]
        self.assertEqual(result["final_audit"]["receipt"]["translation_contract_sha256"], contract["sha256"])
        config = json.loads((self.root / "output/final-audit/repair-01/effective-repair.json").read_text(encoding="utf-8"))
        self.assertIn(contract["sha256"], config["translation_context"])
        self.assertIn("USER_PREFERENCE_9472", config["translation_context"])
        self.assertTrue(config["strict_repair_objects"])
        self.assertNotEqual(seen[0]["context_id"], seen[1]["context_id"])
        self.assertFalse(result["delivery_allowed"])

    def test_contract_changes_invalidate_receipt_and_unsupported_language_calls_nothing(self):
        source, before, _ = self.bundle(self.root / "binding", "A source statement.")
        pdf(before['mono'], ['忠实的原文陈述。'])
        visual.bilingual(source,before['mono'],before['dual'])
        contract = contracts.empty([1]); contract.pop("sha256"); contract["prompt"] = "Keep approved wording."
        contract = contracts.seal(contract)
        def auditor(packet, budget):
            return budget.invoke("offline", lambda timeout: (CLEAR, {}))
        with mock.patch.object(audit, "PROTOCOL_VALIDATED", True):
            result = audit.run(source, before, self.root / "contract", auditor, upstream_ready=True, translation_contract=contract, **semantic_fake.options())
            self.assertTrue(audit.verify_before_delivery(source, before, result["receipt"], translation_contract=contract))
            for key, value in (("prompt", "Different wording."), ("target_language", "fr"), ("source_language", "de")):
                changed = copy.deepcopy(contract); changed.pop("sha256"); changed[key] = value; changed = contracts.seal(changed)
                self.assertFalse(audit.verify_before_delivery(source, before, result["receipt"], translation_contract=changed))
        other = copy.deepcopy(contract); other.pop("sha256"); other["target_language"] = "fr"; other = contracts.seal(other)
        client = mock.Mock()
        result = audit.run(source, before, self.root / "unsupported", client, translation_contract=other)
        self.assertIn("REQUIRES_ENGLISH_TO_SIMPLIFIED_CHINESE", result["error_code"])
        client.assert_not_called(); self.assertEqual(result["model_calls"], 0)

    def test_glossary_content_and_translation_scope_bind_even_unchanged_pdf_bytes(self):
        source, before, _ = self.bundle(self.root / "contract-inputs", "A source statement.")
        prompt = self.root / "prompt.txt"; prompt.write_text("Keep terminology.", encoding="utf-8")
        glossary = self.root / "terms.csv"; glossary.write_text("source,target\nbound,界\n", encoding="utf-8")
        job = {"source_language": "en", "target_language": "zh-CN", "prompt_file": "prompt.txt", "glossaries": ["terms.csv"]}
        initial = contracts.from_job(job, self.root / "job.json", 1)
        def auditor(packet, budget):
            return budget.invoke("offline", lambda timeout: (CLEAR, {}))
        with mock.patch.object(audit, "PROTOCOL_VALIDATED", True):
            report = audit.run(source, before, self.root / "sealed-contract", auditor, upstream_ready=True, translation_contract=initial)
            glossary.write_text("source,target\nbound,边界\n", encoding="utf-8")
            changed = contracts.from_job(job, self.root / "job.json", 1)
            self.assertNotEqual(changed["sha256"], initial["sha256"])
            self.assertFalse(audit.verify_before_delivery(source, before, report["receipt"], translation_contract=changed))
            self.assertFalse(audit.verify_before_delivery(source, before, report["receipt"], translation_pages=[1, 2], translation_contract=initial))
        changed["prompt"] = "Tampered without resealing."
        with self.assertRaisesRegex(ValueError, "HASH_CHANGED"):
            contracts.validate(changed, [1])

    def test_postcheck_does_not_exempt_arbitrary_drawing_as_repair_background(self):
        source, before, region = self.bundle(self.root / "drawing", "A source statement.")
        for name, fill, expansion in (("black", (0, 0, 0), 0), ("oversized", (1, 1, 1), 2)):
            with self.subTest(name=name):
                path = self.root / (name + ".pdf")
                with fitz.open(before["mono"]) as doc:
                    box = fitz.Rect(region["bbox"]) + (-expansion, -expansion, expansion, expansion)
                    doc[0].draw_rect(box, fill=fill, color=fill)
                    doc.save(path)
                with fitz.open(source) as original, fitz.open(before["mono"]) as old, fitz.open(path) as changed:
                    proof = repair_objects.island(original[0], old[0], changed[0], region["bbox"])
                    self.assertFalse(proof["passed"])
                    self.assertIn("drawing_object_in_island", proof["evidence"]["after"]["reasons"])

    def test_terminal_adapter_cannot_translate_an_intentionally_source_language_page(self):
        source, mono, dual = (self.root / name for name in ("source.pdf", "mono.pdf", "dual.pdf"))
        pdf(source, ["Temperature is controlled."] * 2)
        shutil.copyfile(source, mono); visual.bilingual(source, mono, dual)
        before = {"mono": mono, "dual": dual}
        with fitz.open(mono) as doc:
            region = visual.regions(doc[0])[0]
        issue = self.issue(region, "温度受到控制。")
        finding = {"id": "f", "page": 1, **{key: value for key, value in issue.items() if key != "replacement"}}
        output = self.root / "out-of-scope"; output.mkdir()
        client = Vision(issue); budget = audit.Budget(6, 60)
        with mock.patch.object(visual, "NativeVision", return_value=client):
            with self.assertRaisesRegex(ValueError, "FINAL_FINDINGS_NOT_REPAIRED"):
                audit.visual_repairer(PROVIDER, mock.Mock(capability_verified=True), translation_contract=contracts.empty([2]))(
                    source, before, [finding], budget, output)
        self.assertEqual(budget.calls, 1)
        self.assertEqual(audit.sha(mono), audit.sha(output / "visual-repair/best.mono.pdf"))
        self.assertIn('"requested_translation_pages":[2]', client.prompts[0])

    def test_explicit_empty_contract_is_not_silently_replaced_with_defaults(self):
        source, before, _ = self.bundle(self.root / "empty-contract", "A source statement.")
        client = mock.Mock()
        result = audit.run(source, before, self.root / "empty-run", client, translation_contract={})
        self.assertEqual(result["error_code"], "INVALID_TRANSLATION_CONTRACT")
        client.assert_not_called()

    def test_prompt_mutation_during_terminal_audit_blocks_pipeline_completion(self):
        result, seen, _ = self.pipeline_case(1, "1", [1], preference=True, mutate_preferences=True)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "TRANSLATION_CONTRACT_CHANGED_DURING_PIPELINE")
        self.assertFalse(result["delivery_allowed"])
        self.assertNotIn("delivery_artifacts", result)
        self.assertIn("USER_PREFERENCE_9472", seen[0]["prompt"])


if __name__ == "__main__":
    unittest.main()
