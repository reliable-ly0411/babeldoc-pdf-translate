"""Offline state-machine tests on temporary synthetic PDFs; no model calls."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import pymupdf as fitz
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import final_audit as audit
import visual_review as visual
import semantic_offline_support as semantic_fake

CLEAR = {"verdict": "clear", "issues": []}
UNCERTAIN = {"verdict": "uncertain", "issues": []}


def pdf(path, text, pages=1, chinese=False, footer="", width=320):
    with fitz.open() as doc:
        for number in range(pages):
            page = doc.new_page(width=width, height=200)
            page.insert_text((30, 50), text, fontsize=11, fontname="china-s" if chinese else "helv")
            if footer:
                page.insert_text((30, 150), footer, fontsize=10)
        doc.save(path)


class FinalAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="final-audit-offline-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.source = self.base / "source.pdf"
        pdf(self.source, "A source statement.")
        self.artifacts = self.bundle(self.base / "base", "译文甲。")
        self.count = 0
        with fitz.open(self.artifacts["mono"]) as doc:
            self.region = visual.regions(doc[0])[0]["id"]
        self.issue = {"verdict": "defects", "issues": [{"region_id": self.region, "category": "translation", "severity": "major", "reason": "SYNTHETIC_PRIOR_FINDING"}]}

    def bundle(self, folder, text, pages=1, footer=""):
        folder.mkdir()
        mono, dual = folder / "mono.pdf", folder / "dual.pdf"
        pdf(mono, text, pages, True, footer)
        visual.bilingual(self.source, mono, dual)
        return {"mono": mono, "dual": dual}

    def fake(self, responses, seen=None):
        values = list(responses)
        def call(packet, budget):
            if seen is not None:
                seen.append(packet)
            value = copy.deepcopy(values.pop(0) if len(values) > 1 else values[0])
            return budget.invoke("offline-fake-vision", lambda timeout: (value, {"input_tokens": 1, "output_tokens": 1}))
        return call

    def run_audit(self, responses=(CLEAR,), **options):
        self.count += 1
        return audit.run(self.source, self.artifacts, self.base / ("audit" + str(self.count)), self.fake(responses), **options)

    def repair(self, source, current, findings, budget, folder):
        budget.invoke("offline-fake-repair", lambda timeout: ({}, {"input_tokens": 1, "output_tokens": 1}))
        revised = self.bundle(folder / "new", "译文乙。")
        return {"artifacts": revised, "addressed_findings": [finding["id"] for finding in findings]}

    def validator(self, source, before, after, findings, revised):
        return {"passed": True, "binding": audit.snapshot(source, after), "outside_region_regression_passed": True, "math_objects_passed": True}

    def test_actual_source_mono_dual_are_rendered_and_context_is_fresh(self):
        first = audit.packets(self.source, self.artifacts, self.base / "packets1")
        second = audit.packets(self.source, self.artifacts, self.base / "packets2")
        self.assertNotEqual(first[1], second[1])
        self.assertEqual(first[0], second[0])
        self.assertEqual(len(first[2][0]["images"]), 3)
        self.assertTrue(all(path.is_file() and path.stat().st_size for path in first[2][0]["images"]))
        self.assertIn("A source statement", first[2][0]["prompt"])
        self.assertIn("译文甲", first[2][0]["prompt"])

    def test_clear_execution_does_not_mean_validated_quality(self):
        result = self.run_audit(upstream_ready=True)
        self.assertEqual(result["execution_status"], "completed")
        self.assertEqual(result["audit_model_verdict"], "clear")
        self.assertEqual(result["quality_status"], "blocked_unvalidated_final_audit")
        self.assertFalse(result["delivery_allowed"])

    def test_source_mono_or_dual_byte_change_invalidates_audit(self):
        with mock.patch.object(audit, "PROTOCOL_VALIDATED", True):
            result = self.run_audit(upstream_ready=True, **semantic_fake.options())
            self.assertTrue(audit.verify_before_delivery(self.source, self.artifacts, result["receipt"]))
            for path in [self.source, *self.artifacts.values()]:
                old = path.read_bytes()
                path.write_bytes(old + b"\n% synthetic metadata change\n")
                self.assertFalse(audit.verify_before_delivery(self.source, self.artifacts, result["receipt"]))
                path.write_bytes(old)

    def test_missing_page_coverage_cannot_be_cleared_by_a_pass_marker(self):
        with mock.patch.object(audit, "PROTOCOL_VALIDATED", True):
            result = self.run_audit(upstream_ready=True)
            receipt = copy.deepcopy(result["receipt"])
            receipt["audited_pages"] = []
            self.assertFalse(audit.verify_before_delivery(self.source, self.artifacts, receipt))

    def test_known_regression_vetoes_clear_audit_and_delivery(self):
        with mock.patch.object(audit, "PROTOCOL_VALIDATED", True):
            result = self.run_audit(upstream_ready=True, known_regressions=lambda *args: [{"case_id": "generic_failed_row"}])
        self.assertEqual(result["quality_status"], "blocked_known_regression")
        self.assertFalse(result["quality_passed"])

    def test_final_layer_cannot_clear_an_upstream_failure(self):
        with mock.patch.object(audit, "PROTOCOL_VALIDATED", True):
            result = self.run_audit(upstream_ready=False)
        self.assertEqual(result["quality_status"], "blocked_upstream_validation")

    def test_uncertainty_is_not_repaired_or_silently_cleared(self):
        repair = mock.Mock()
        result = self.run_audit((UNCERTAIN,), repairer=repair, revalidate=self.validator)
        self.assertEqual(result["quality_status"], "needs_manual_uncertainty")
        repair.assert_not_called()

    def test_defects_without_safe_repair_adapter_require_manual_review(self):
        result = self.run_audit((self.issue,))
        self.assertEqual(result["execution_status"], "completed")
        self.assertEqual(result["quality_status"], "needs_manual_repair_limit_or_adapter")

    def test_targeted_repair_revalidation_then_fresh_reaudit_are_separate(self):
        seen = []
        with mock.patch.object(audit, "PROTOCOL_VALIDATED", True):
            result = audit.run(self.source, self.artifacts, self.base / "loop", self.fake([self.issue, CLEAR], seen),
                upstream_ready=True, repairer=self.repair, revalidate=self.validator, max_calls=5, **semantic_fake.options())
            self.assertTrue(result["delivery_allowed"])
            self.assertTrue(audit.verify_before_delivery(self.source, result["final_artifacts"], result["receipt"]))
        self.assertEqual(result["repair_rounds"], 1)
        self.assertEqual(result["model_calls"], 5)
        self.assertNotEqual(seen[0]["context_id"], seen[1]["context_id"])
        self.assertTrue(all("SYNTHETIC_PRIOR_FINDING" not in packet["prompt"] for packet in seen))

    def test_still_bad_after_limit_stops_without_infinite_loop(self):
        result = self.run_audit((self.issue, self.issue), repairer=self.repair, revalidate=self.validator, max_repair_rounds=1)
        self.assertEqual(result["repair_rounds"], 1)
        self.assertEqual(result["model_calls"], 3)
        self.assertEqual(result["quality_status"], "needs_manual_repair_limit_or_adapter")

    def test_new_audit_call_budget_is_reserved_before_repair(self):
        def spend_too_much(source, current, findings, budget, folder):
            budget.invoke("fake-repair", lambda timeout: ({}, {}))
            budget.invoke("fake-repair", lambda timeout: ({}, {}))
            return self.repair(source, current, findings, budget, folder)
        result = self.run_audit((self.issue,), repairer=spend_too_much, revalidate=self.validator, max_calls=3)
        self.assertEqual(result["error_code"], "FINAL_AUDIT_BUDGET_EXHAUSTED")
        self.assertEqual(result["model_calls"], 2)

    def test_stale_revalidation_receipt_is_rejected(self):
        before = audit.snapshot(self.source, self.artifacts)
        def stale(*args):
            return {"passed": True, "binding": before, "outside_region_regression_passed": True, "math_objects_passed": True}
        result = self.run_audit((self.issue,), repairer=self.repair, revalidate=stale)
        self.assertEqual(result["error_code"], "FINAL_REPAIR_REVALIDATION_FAILED")

    def test_findings_cannot_disappear_without_program_addressing(self):
        def forget(*args):
            result = self.repair(*args)
            result["addressed_findings"] = []
            return result
        result = self.run_audit((self.issue,), repairer=forget, revalidate=self.validator)
        self.assertEqual(result["error_code"], "FINAL_FINDINGS_NOT_ALL_ADDRESSED")

    def test_in_place_repair_is_rejected_and_audit_is_invalid(self):
        def mutate(source, current, findings, budget, folder):
            pdf(current["mono"], "译文乙。", chinese=True)
            return {"artifacts": current, "addressed_findings": [f["id"] for f in findings]}
        result = self.run_audit((self.issue,), repairer=mutate, revalidate=self.validator)
        self.assertEqual(result["error_code"], "REPAIR_MUTATED_PREVIOUS_ARTIFACTS")

    def test_unbudgeted_or_malformed_audit_result_fails_closed(self):
        result = audit.run(self.source, self.artifacts, self.base / "unbudgeted", lambda *args: CLEAR)
        self.assertEqual(result["error_code"], "AUDIT_CALL_NOT_IN_SHARED_BUDGET")
        malformed = {"verdict": "clear", "issues": self.issue["issues"]}
        self.assertEqual(self.run_audit((malformed,))["error_code"], "FINAL_AUDIT_CONCLUSION_INCONSISTENT")

    def test_real_pdf_or_render_changes_during_audit_fail(self):
        def mutate(packet, budget):
            packet["images"][0].write_bytes(b"synthetic changed image")
            return budget.invoke("fake", lambda timeout: (CLEAR, {}))
        result = audit.run(self.source, self.artifacts, self.base / "changed-render", mutate)
        self.assertEqual(result["error_code"], "FINAL_ARTIFACT_OR_RENDER_CHANGED_DURING_AUDIT")

    def test_program_revalidation_checks_pixel_regression_and_dual_composition(self):
        candidate = self.bundle(self.base / "candidate", "译文乙。")
        finding = {"id": "f", "page": 1, **self.issue["issues"][0]}
        result = audit.program_revalidate(self.source, self.artifacts, candidate, [finding], {})
        self.assertTrue(result["outside_region_regression_passed"])
        self.assertTrue(result["actual_dual_matches_source_and_final_mono"])
        other = self.base / "other-dual.pdf"
        pdf(other, "Wrong composition", width=640)
        candidate["dual"] = other
        self.assertFalse(audit.program_revalidate(self.source, self.artifacts, candidate, [finding], {})["passed"])

    def test_production_astra_is_rejected_and_local_vision_is_explicit(self):
        with self.assertRaisesRegex(ValueError, "ASTRA_DEVELOPMENT"):
            audit.stateless_auditor({"model": "gpt-6-astra", "vision": True, "type": "codex"})
        local = audit.stateless_auditor({"model": "local-vision", "vision": True, "type": "openai-compatible"})
        self.assertEqual(local.model, "local-vision")
        self.assertEqual(local.backend, "openai-compatible")

    def test_development_acceptance_cannot_repair_or_deliver(self):
        auditor = self.fake([CLEAR])
        auditor.purpose = "development_acceptance"
        with mock.patch.object(audit, "PROTOCOL_VALIDATED", True):
            result = audit.run(self.source, self.artifacts, self.base / "dev", auditor, upstream_ready=True, max_repair_rounds=0)
        self.assertEqual(result["quality_status"], "development_acceptance_only")
        self.assertFalse(result["delivery_allowed"])

    def test_pipeline_gate_requires_fresh_receipt_and_retains_known_veto(self):
        report = {"execution_status": "completed", "quality_passed": True, "known_regressions": [{"id": "old failure"}], "selected_pages": [1]}
        hook = audit.make_pipeline_hook(self.fake([CLEAR]), max_repair_rounds=0)
        with mock.patch.object(audit, "PROTOCOL_VALIDATED", True):
            audit.attach_pipeline_report(report, self.source, self.artifacts, self.base / "hook", hook)
        self.assertEqual(report["final_audit"]["quality_status"], "blocked_known_regression")
        self.assertFalse(report["delivery_allowed"])

    def test_no_hook_cannot_be_treated_as_delivery_success(self):
        report = {"execution_status": "completed", "quality_passed": True}
        audit.attach_pipeline_report(report, self.source, self.artifacts, self.base / "no-hook", None)
        self.assertFalse(report["quality_passed"])
        self.assertEqual(report["delivery_status"], "final_audit_not_run")

    def test_translation_scope_is_explicit_and_bound_for_delivery(self):
        seen = []
        with mock.patch.object(audit, "PROTOCOL_VALIDATED", True):
            result = audit.run(self.source, self.artifacts, self.base / "scope", self.fake([CLEAR], seen), upstream_ready=True, translation_pages=[1], **semantic_fake.options())
            self.assertTrue(audit.verify_before_delivery(self.source, self.artifacts, result["receipt"], translation_pages=[1]))
            self.assertFalse(audit.verify_before_delivery(self.source, self.artifacts, result["receipt"], translation_pages=[]))
        self.assertIn('"translated_pages":[1]', seen[0]["prompt"])

    def test_audit_execution_error_is_not_retried(self):
        def failed(packet,budget):
            def fail(timeout):raise RuntimeError('offline injected transport failure')
            return budget.invoke('fake',fail)
        result=audit.run(self.source,self.artifacts,self.base/'failure',failed)
        self.assertEqual(result['model_calls'],1)
        self.assertEqual(result['execution_status'],'failed_or_incomplete')
        self.assertEqual(result['model_ledger'][0]['state'],'failed')

    def test_config_dry_construction_cannot_claim_protocol_validation(self):
        cfg={'provider':{'type':'codex','model':'gpt-6-luna','vision':True,'retries':0},'max_repair_rounds':1,
             'limits':{'max_model_calls':6,'max_seconds':60}}
        path=self.base/'config.json';audit.save(path,cfg)
        with mock.patch.object(visual,'NativeVision') as client:
            hook=audit.from_config(path)
            self.assertTrue(callable(hook));client.assert_not_called()
            cfg['protocol_validated']=True;audit.save(path,cfg)
            with self.assertRaisesRegex(ValueError,'INVALID_FINAL_AUDIT_CONFIG'):audit.from_config(path)

    def test_visual_repair_adapter_reuses_normal_repair_and_shared_budget(self):
        provider={'type':'codex','model':'gpt-6-luna','vision':True,'retries':0,'timeout_seconds':5}
        final_auditor=mock.Mock(capability_verified=True)
        repair=audit.visual_repairer(provider,final_auditor)
        budget=audit.Budget(6,60)
        folder=self.base/'adapter';folder.mkdir()
        class Client:
            def inspect(self,*args,**kwargs):return {'issues':[]},{'input_tokens':1,'output_tokens':1}
        def normal_repair(cfg,session,*,source_quantity_roles=()):
            self.assertFalse(source_quantity_roles)
            session.verify_provider(cfg['provider']);records=[];session.ensure_vision(cfg,records)
            response,usage=session.invoke(session.client,'fresh repair request',[],cfg,budget,folder,{},schema=visual.SCHEMA)
            self.assertEqual(response,{'issues':[]});self.assertEqual(usage['input_tokens'],1)
            cfg['output'].mkdir();changed=self.bundle(cfg['output']/'result','译文乙。')
            for key,path in changed.items():path.rename(cfg['output']/('best.'+key+'.pdf'))
            with fitz.open(self.artifacts['mono']) as doc:region=visual.regions(doc[0])[0]
            return {'execution_status':'completed','pages':[{'page':1,'accepted_repairs':[{
                'region':region,'method':'bounded_plain_prose','issue':{'region_id':self.region}}]}]}
        finding={'id':'f','page':1,**self.issue['issues'][0]}
        with mock.patch.object(visual,'NativeVision',return_value=Client()),mock.patch.object(visual,'run',side_effect=normal_repair):
            result=repair(self.source,self.artifacts,[finding],budget,folder)
        self.assertEqual(result['addressed_findings'],['f']);self.assertEqual(budget.calls,1)

    def test_interrupt_is_journalled_and_same_output_cannot_restart(self):
        for error_type in (KeyboardInterrupt,SystemExit):
            with self.subTest(error_type=error_type.__name__):
                folder=self.base/('interrupt-'+error_type.__name__)
                def interrupted(packet,budget):
                    def stop(timeout):
                        ledger=json.loads((folder/'call-ledger.json').read_text(encoding='utf-8'))
                        self.assertEqual(ledger['calls'][0]['state'],'started')
                        self.assertEqual(json.loads((folder/'execution-marker.json').read_text())['state'],'started')
                        raise error_type()
                    return budget.invoke('offline-interrupted',stop)
                result=audit.run(self.source,self.artifacts,folder,interrupted)
                self.assertEqual(result['execution_status'],'interrupted')
                self.assertEqual(result['quality_status'],'needs_manual_interrupted')
                self.assertFalse(result['delivery_allowed'])
                ledger=(folder/'call-ledger.json').read_bytes()
                self.assertEqual(json.loads(ledger)['calls'][0]['state'],'interrupted')
                retry=mock.Mock()
                with self.assertRaises(FileExistsError):audit.run(self.source,self.artifacts,folder,retry)
                retry.assert_not_called();self.assertEqual((folder/'call-ledger.json').read_bytes(),ledger)

    def test_partial_directory_is_unknown_execution_not_a_resume_permission(self):
        folder=self.base/'partial';folder.mkdir()
        audit.save(folder/'execution-marker.json',{'state':'started'})
        audit.save(folder/'call-ledger.json',{'calls':[{'state':'started','native_usage':None}]})
        old=(folder/'call-ledger.json').read_bytes();client=mock.Mock()
        with self.assertRaises(FileExistsError):audit.run(self.source,self.artifacts,folder,client)
        client.assert_not_called();self.assertEqual((folder/'call-ledger.json').read_bytes(),old)

    def test_custom_hook_cannot_drop_upstream_known_regression(self):
        with mock.patch.object(audit,'PROTOCOL_VALIDATED',True):
            clear=self.run_audit(upstream_ready=True)
            report={'execution_status':'completed','quality_passed':True,'known_regressions':[{'id':'existing_failure'}],'selected_pages':[1]}
            audit.attach_pipeline_report(report,self.source,self.artifacts,self.base/'custom-hook',lambda *args:clear)
        self.assertFalse(report['delivery_allowed'])
        self.assertEqual(report['quality_status'],'blocked_known_regression')
        self.assertNotIn('delivery_artifacts',report)

    def test_prior_pass_for_another_candidate_is_not_reused(self):
        with mock.patch.object(audit,'PROTOCOL_VALIDATED',True):
            clear=self.run_audit(upstream_ready=True)
            changed=self.bundle(self.base/'other-candidate','译文丙。')
            report={'execution_status':'completed','quality_passed':True,'selected_pages':[1]}
            audit.attach_pipeline_report(report,self.source,changed,self.base/'reuse',lambda *args:clear)
        self.assertFalse(report['delivery_allowed'])

    def test_invalid_pdf_after_audit_returns_invalid_receipt_not_exception(self):
        with mock.patch.object(audit,'PROTOCOL_VALIDATED',True):
            clear=self.run_audit(upstream_ready=True)
            self.artifacts['dual'].write_bytes(b'not a PDF')
            self.assertFalse(audit.verify_before_delivery(self.source,self.artifacts,clear['receipt']))

    def test_stateless_adapter_constructs_fresh_clients_and_omits_cache(self):
        created=[];seen=[]
        class Client:
            def inspect(self,prompt,images,timeout,schema=None):
                seen.append((prompt,list(images),schema));return CLEAR,{'input_tokens':1,'output_tokens':1}
        def factory(cfg):
            self.assertNotIn('cache_dir',cfg);self.assertNotIn('diagnostics_dir',cfg)
            value=Client();created.append(value);return value
        producer=audit.stateless_auditor({'type':'codex','model':'gpt-6-luna','vision':True,'retries':0,
            'cache_dir':'prior-passed-cache','diagnostics_dir':'prior-report'},client_factory=factory)
        packet=audit.packets(self.source,self.artifacts,self.base/'fresh-packet')[2][0]
        budget=audit.Budget(2,60)
        producer(packet,budget);producer(packet,budget)
        self.assertEqual(len(created),2);self.assertIsNot(created[0],created[1])
        self.assertEqual(budget.calls,2);self.assertEqual(len(seen[0][1]),3)
        self.assertNotIn('prior-passed-cache',seen[0][0])

    def test_invalid_hook_or_regression_evidence_cannot_clear_quality(self):
        report={'execution_status':'completed','quality_passed':True}
        audit.attach_pipeline_report(report,self.source,self.artifacts,self.base/'invalid-hook',lambda *args:{'quality_passed':True})
        self.assertFalse(report['delivery_allowed'])
        self.assertEqual(report['final_audit']['error_code'],'INVALID_FINAL_AUDIT_HOOK_RESULT')
        result=self.run_audit(upstream_ready=True,known_regressions=lambda *args:None)
        self.assertEqual(result['error_code'],'INVALID_KNOWN_REGRESSION_RESULT')

    def test_insufficient_whole_document_budget_starts_no_audit_calls(self):
        source=self.base/'two-source.pdf';pdf(source,'A source statement.',pages=2)
        mono=self.base/'two-mono.pdf';pdf(mono,'译文甲。',pages=2,chinese=True)
        dual=self.base/'two-dual.pdf';visual.bilingual(source,mono,dual)
        client=mock.Mock()
        result=audit.run(source,{'mono':mono,'dual':dual},self.base/'small-budget',client,max_calls=1)
        self.assertEqual(result['model_calls'],0);client.assert_not_called()
        self.assertEqual(result['error_code'],'FINAL_AUDIT_BUDGET_EXHAUSTED')

    def test_wrong_dual_geometry_blocks_before_auditing(self):
        wrong=self.base/'wrong-dual.pdf';pdf(wrong,'Wrong dual width')
        client=mock.Mock()
        result=audit.run(self.source,{'mono':self.artifacts['mono'],'dual':wrong},self.base/'wrong-geometry',client)
        self.assertEqual(result['error_code'],'FINAL_DUAL_GEOMETRY_CHANGED')
        client.assert_not_called();self.assertFalse(result['delivery_allowed'])


if __name__ == "__main__":
    unittest.main()
