"""Real-adapter and real post-check consistency for protected editing contracts."""
import copy
import json
from pathlib import Path
import sys
import unittest
import shutil
import unicodedata
from unittest import mock

import pymupdf as fitz
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'scripts')]
import final_audit as audit
import repair_objects
import visual_review as visual
import test_final_audit_boundaries as boundary
Vision,PROVIDER,pdf=boundary.Vision,boundary.PROVIDER,boundary.pdf


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture=boundary.ReviewBoundaryTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root

    def scenario(self,folder,source,replacement):
        folder.mkdir();original=folder/'source.pdf';mono=folder/'before.mono.pdf';dual=folder/'before.dual.pdf'
        pdf(original,[source]);shutil.copyfile(original,mono);visual.bilingual(original,mono,dual)
        before={'mono':mono,'dual':dual}
        with fitz.open(mono) as doc:
            region=visual.regions(doc[0])[0]
            self.assertIn(unicodedata.normalize('NFKC',source),unicodedata.normalize('NFKC',doc[0].get_text()).replace('\n',' '))
        issue=self.fixture.issue(region,replacement)
        finding={'id':'f','page':1,**{k:v for k,v in issue.items() if k!='replacement'}}
        return original,before,region,issue,finding

    def actual_adapter(self,source,before,issue,finding,folder, *, source_quantity_roles=()):
        folder.mkdir();client=Vision(issue);budget=audit.Budget(6,60)
        with mock.patch.object(visual,'NativeVision',return_value=client):
            revised=audit.visual_repairer(PROVIDER,mock.Mock(capability_verified=True),source_quantity_roles=source_quantity_roles)(source,before,[finding],budget,folder)
        return revised,budget,client

    def test_fraction_and_function_families_rejected_by_actual_adapter_and_real_postcheck(self):
        variants=[('Use ½ as a bound.','使用 ⅓ 作为界。'),('Use ¼ as a bound.','使用 ¾ 作为界。'),
            ('Use ⅚ as a bound.','使用 ⅔ 作为界。'),('Use exp(theta) as a bound.','采用 exp(phi) 为界。'),
            ('Use kernel(alpha) as a bound.','采用 kernel(beta) 为界。'),
            ('Use nested(kernel(theta)) as a bound.','采用 nested(kernel(phi)) 为界。'),
            ('Use arbitrary_71(theta) as a bound.','采用 arbitrary_71(phi) 为界。'),
            ('Use values[index] as a bound.','采用 values[other] 为界。'),
            ('Use theta-phi as a bound.','采用 theta-psi 为界。'),
            ('Use 5/8 as a bound.','使用 3/8 作为界。')]
        for number,(text,replacement) in enumerate(variants):
            with self.subTest(text=text):
                folder=self.root/('negative-%02d'%number)
                source,before,region,issue,finding=self.scenario(folder,text,replacement)
                with fitz.open(before['mono']) as doc:self.assertFalse(visual.repairable(doc[0],region,issue))
                with self.assertRaisesRegex(ValueError,'FINAL_FINDINGS_NOT_REPAIRED'):
                    self.actual_adapter(source,before,issue,finding,folder/'adapter')
                mono,dual=folder/'forced.mono.pdf',folder/'forced.dual.pdf'
                pdf(mono,[replacement]);visual.bilingual(source,mono,dual);after={'mono':mono,'dual':dual}
                edits=[{'page':1,'region_id':region['id'],'bbox':region['bbox'],'method':'bounded_plain_prose'}]
                evidence=audit.repair_object_evidence(source,before,after,edits)
                check=audit.program_revalidate(source,before,after,[finding],{'repair_evidence':evidence})
                self.assertFalse(check['math_objects_passed']);self.assertFalse(check['passed'])
                proof=evidence['edits'][0]['object_proof']
                self.assertTrue(proof['required_source_tokens'])
                self.assertFalse(proof['passed'])
                if '(' in text or '[' in text:
                    self.assertFalse(proof['protected_opaque_identity_preserved'])

    def test_safe_long_sentences_and_numeric_units_pass_real_adapter_and_postcheck(self):
        variants=[('Temperature is controlled during the experiment.','实验期间温度受控。'),
            ('The voltage is controlled at 5 volts.','电压被控制在5伏。'),
            ('The current is limited to 10 amperes.','电流限制为10安培。'),
            ('The output level is fixed at 12.5 volts.','输出电压固定在12.5伏。')]
        for number,(text,replacement) in enumerate(variants):
            with self.subTest(text=text):
                folder=self.root/('positive-%02d'%number)
                source,before,region,issue,finding=self.scenario(folder,text,replacement)
                with fitz.open(before['mono']) as doc:self.assertTrue(visual.repairable(doc[0],region,issue))
                revised,budget,client=self.actual_adapter(source,before,issue,finding,folder/'adapter')
                check=audit.program_revalidate(source,before,revised['artifacts'],[finding],revised)
                self.assertTrue(check['passed']);self.assertTrue(check['math_objects_passed'])
                proof=revised['repair_evidence']['edits'][0]['object_proof']
                self.assertTrue(proof['protected_decimal_identity_preserved'])
                self.assertTrue(proof['actual_text_changes'])
                for role in ('source','before','after'):
                    self.assertTrue(all(token['glyph_evidence'] for token in proof['evidence'][role]['text_contract']['protected_tokens']))
                self.assertEqual(budget.calls,2)
                report=json.loads((folder/'adapter/visual-repair/review-report.json').read_text(encoding='utf-8'))
                self.assertFalse(report['pages'][0]['final_prose_completeness_findings'])
                attempt=report['pages'][0]['attempts'][0]
                dispositions=attempt['finding_resolutions']
                self.assertGreaterEqual(len(dispositions),2)
                self.assertTrue(all(item['status']=='verified_addressed_by_same_edit' for item in dispositions))
                self.assertTrue(attempt['acceptance']['actual_prose_recheck_passed'])
                self.assertEqual(audit.sha(source),audit.sha(before['mono']))

    def test_changed_decimal_value_fails_preflight_and_independent_actual_text_contract(self):
        source,before,region,issue,finding=self.scenario(self.root/'decimal','The voltage is controlled at 5 volts.','电压被控制在6伏。')
        with self.assertRaisesRegex(ValueError,'FINAL_FINDINGS_NOT_REPAIRED'):
            self.actual_adapter(source,before,issue,finding,self.root/'decimal/adapter')
        mono=self.root/'decimal/forced.mono.pdf';dual=self.root/'decimal/forced.dual.pdf'
        pdf(mono,[issue['replacement']]);visual.bilingual(source,mono,dual)
        after={'mono':mono,'dual':dual};edits=[{'page':1,'region_id':region['id'],'bbox':region['bbox'],'method':'bounded_plain_prose'}]
        evidence=audit.repair_object_evidence(source,before,after,edits)
        check=audit.program_revalidate(source,before,after,[finding],{'repair_evidence':evidence})
        self.assertFalse(check['math_objects_passed']);self.assertFalse(check['passed'])

    def test_source_objects_cannot_disappear_by_using_a_plain_before_region(self):
        folder=self.root/'source-object';folder.mkdir()
        source=folder/'source.pdf';mono=folder/'before.mono.pdf';dual=folder/'before.dual.pdf'
        pdf(source,['Use kernel(theta) as a bound.']);pdf(mono,['Use this bound.'])
        visual.bilingual(source,mono,dual);before={'mono':mono,'dual':dual}
        with fitz.open(mono) as doc:region=visual.regions(doc[0])[0]
        issue=self.fixture.issue(region,'使用此界。');finding={'id':'f','page':1,**{k:v for k,v in issue.items() if k!='replacement'}}
        with self.assertRaisesRegex(ValueError,'FINAL_FINDINGS_NOT_REPAIRED'):
            self.actual_adapter(source,before,issue,finding,folder/'adapter')

    def test_conflicting_same_region_candidates_do_not_clear_any_finding(self):
        source,before,region,issue,finding=self.scenario(self.root/'conflict','Temperature is controlled during the experiment.','实验期间温度受控。')
        alternate={**issue,'replacement':'实验期间温度不受控。'}
        class Conflicting(Vision):
            def inspect(self,prompt,images,timeout,schema=None):
                if schema and 'before' in schema.get('properties',{}):return super().inspect(prompt,images,timeout,schema)
                self.prompts.append(prompt);return {'issues':[issue,alternate]},{'input_tokens':1}
        folder=self.root/'conflict/adapter';folder.mkdir();client=Conflicting(issue);budget=audit.Budget(6,60)
        with mock.patch.object(visual,'NativeVision',return_value=client):
            with self.assertRaisesRegex(ValueError,'FINAL_FINDINGS_NOT_REPAIRED'):
                audit.visual_repairer(PROVIDER,mock.Mock(capability_verified=True))(source,before,[finding],budget,folder)
        report=json.loads((folder/'visual-repair/review-report.json').read_text(encoding='utf-8'))
        resolutions=report['pages'][0]['attempts'][0]['finding_resolutions']
        self.assertEqual(len(resolutions),3)
        self.assertTrue(all(record['status']=='requires_manual_review' for record in resolutions))
        self.assertTrue(report['pages'][0]['final_prose_completeness_findings'])

    def test_clear_model_reply_does_not_clear_actual_unchanged_prose_warning(self):
        text='Temperature is controlled during the experiment.'
        source,before,region,issue,finding=self.scenario(self.root/'unchanged',text,text)
        with self.assertRaisesRegex(ValueError,'FINAL_FINDINGS_NOT_REPAIRED'):
            self.actual_adapter(source,before,issue,finding,self.root/'unchanged/adapter')
        report=json.loads((self.root/'unchanged/adapter/visual-repair/review-report.json').read_text(encoding='utf-8'))
        attempt=report['pages'][0]['attempts'][0]
        self.assertFalse(attempt['accepted'])
        self.assertFalse(attempt['acceptance']['actual_prose_recheck_passed'])
        self.assertTrue(all(record['status']=='requires_manual_review' for record in attempt['finding_resolutions']))

    def test_math_font_compatibility_digits_are_opaque_while_plain_decimal_units_are_editable(self):
        self.assertFalse(repair_objects.text_contract('Use 𝟝 as a bound.')['plain_editable'])
        self.assertFalse(repair_objects.text_contract('Use 1𝟝 as a bound.')['plain_editable'])
        plain=repair_objects.text_contract('The voltage is controlled at 5 volts.')
        chinese=repair_objects.text_contract('电压被控制在5伏。')
        self.assertTrue(plain['plain_editable']);self.assertTrue(chinese['plain_editable'])
        self.assertEqual(plain['decimal_identity'],chinese['decimal_identity'])


if __name__=='__main__':unittest.main()
