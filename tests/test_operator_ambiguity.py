"""Unknown operator roles cannot become absent mathematics from prose shape."""
import copy,itertools,json,unittest,html,shutil
from unittest import mock
import pymupdf as fitz
import test_repair_contract as previous
import final_audit as audit
import repair_objects
import visual_review as visual

BAD=[('The bound is To +23 volts.','界为 To，偏置为+23伏。'),
    ('The bound is In -41 volts.','界为 In，偏置为-41伏。'),
    ('The threshold is tO +23 volts.','阈值为 tO，偏置为+23伏。'),
    ('The bound is To + 23 volts.','界为 To，偏置为+23伏。'),
    ('The bound is bY - 41 volts.','界为 bY，偏置为-41伏。'),
    ('The threshold is To +23 volts, where To is the initial threshold.','阈值为 To，偏置为+23伏，其中 To 为初始阈值。')]

class AmbiguityTests(unittest.TestCase):
    def setUp(self):
        self.fixture=previous.ContractTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups);self.root=self.fixture.root

    def test_original_quantity_frame_counterexamples_reject_adapter_and_actual_postcheck(self):
        for number,(text,replacement) in enumerate(BAD):
            with self.subTest(text=text):
                folder=self.root/('bad-%02d'%number)
                source,before,region,issue,finding=self.fixture.scenario(folder,text,replacement)
                with self.assertRaisesRegex(ValueError,'FINAL_FINDINGS_NOT_REPAIRED'):
                    self.fixture.actual_adapter(source,before,issue,finding,folder/'adapter')
                mono,dual=folder/'forced.mono.pdf',folder/'forced.dual.pdf';previous.pdf(mono,[replacement]);visual.bilingual(source,mono,dual)
                after={'mono':mono,'dual':dual};edits=[{'page':1,'region_id':region['id'],'bbox':region['bbox'],'method':'bounded_plain_prose'}]
                evidence=audit.repair_object_evidence(source,before,after,edits)
                check=audit.program_revalidate(source,before,after,[finding],{'repair_evidence':json.loads(json.dumps(evidence))})
                self.assertFalse(check['math_objects_passed']);self.assertFalse(check['passed'])

    def test_frames_case_and_whitespace_never_resolve_ambiguous_roles(self):
        for word,frame,left,right,op in itertools.product(('To','to','TO','tO','In','in','BY','by'),
            ('The bound is {} volts.','The bound is {} volts, where the name denotes a threshold.','The voltage is controlled {} volts.'),
            ('',' ','\t'),('',' '),('+','-')):
            text=frame.format(word+left+op+right+'29')
            with self.subTest(text=text):self.assertFalse(repair_objects.text_contract(text)['plain_editable'])

    def test_unsigned_prose_stays_automatic_and_signed_quantity_needs_independent_role(self):
        import quantity_roles
        text='The voltage is fixed at +23 volts.';replacement='电压固定为+23伏。'
        source,before,region,issue,finding=self.fixture.scenario(self.root/'quantity',text,replacement)
        with self.assertRaisesRegex(ValueError,'FINAL_FINDINGS_NOT_REPAIRED'):
            self.fixture.actual_adapter(source,before,issue,finding,self.root/'quantity/unknown')
        roles=[quantity_roles.confirm_from_operator(source,1,'block_0','at',reason='Independent positive-control oracle confirms prose at and unary quantity +23; not a model response.')]
        revised,budget,client=self.fixture.actual_adapter(source,before,issue,finding,self.root/'quantity/confirmed',source_quantity_roles=roles)
        self.assertTrue(audit.program_revalidate(source,before,revised['artifacts'],[finding],revised,source_quantity_roles=roles)['passed'])
        self.assertFalse(audit.program_revalidate(source,before,revised['artifacts'],[finding],revised)['passed'])
        unsigned='The voltage is fixed at 23 volts.'
        source,before,region,issue,finding=self.fixture.scenario(self.root/'unsigned',unsigned,'电压固定为23伏。')
        revised,_,_=self.fixture.actual_adapter(source,before,issue,finding,self.root/'unsigned/adapter')
        self.assertTrue(audit.program_revalidate(source,before,revised['artifacts'],[finding],revised)['passed'])

    def test_role_evidence_binding_and_math_objects_cannot_be_overridden(self):
        import quantity_roles
        source,before,region,issue,finding=self.fixture.scenario(self.root/'binding','The voltage is fixed at +23 volts.','电压固定为+23伏。')
        role=quantity_roles.confirm_from_operator(source,1,'block_0','at',reason='Independent positive-control intent.')
        for key,value in (('source_sha256','0'*64),('glyphs_sha256','0'*64),('boundary_text','To'),('authority','model_reply')):
            with self.subTest(key=key):
                bad=copy.deepcopy(role);bad[key]=value
                with self.assertRaises(ValueError):quantity_roles.validate_for_source(source,[bad])
        original,bundle,part=self.fixture.fixture.bundle(self.root/'unknown-font','The voltage is fixed at +23 volts.',unknown_font=True)
        role=quantity_roles.confirm_from_operator(original,1,part['id'],'at',reason='Confirmed quantity intent cannot authorize unknown font objects.')
        bad_issue=self.fixture.fixture.issue(part,'电压固定为+23伏。');bad_finding={'id':'f','page':1,**{k:v for k,v in bad_issue.items() if k!='replacement'}}
        with self.assertRaisesRegex(ValueError,'FINAL_FINDINGS_NOT_REPAIRED'):
            self.fixture.actual_adapter(original,bundle,bad_issue,bad_finding,self.root/'unknown-font/adapter',source_quantity_roles=[role])

    def test_confirmation_cannot_authorize_compound_expression_or_other_protected_objects(self):
        import quantity_roles
        for number,expression in enumerate(('+23+6','+23^2','(+23+6)','--23')):
            with self.subTest(expression=expression):
                source,_,region,_,_=self.fixture.scenario(self.root/('compound-%d'%number),
                    'The voltage is fixed at '+expression+' volts.','电压固定为+23伏。')
                with self.assertRaisesRegex(ValueError,'CANNOT_OVERRIDE_COMPOUND_EXPRESSION'):
                    quantity_roles.confirm_from_operator(source,1,region['id'],'at',reason='A confirmation cannot turn compound mathematics into a scalar.')
        source,before,region,issue,finding=self.fixture.scenario(self.root/'other-math',
            'The voltage is fixed at +23 volts; use x² as a bound.','电压固定为+23伏；以 x³ 为界。')
        roles=[quantity_roles.confirm_from_operator(source,1,region['id'],'at',reason='Confirms only the declared scalar quantity, not the other mathematical object.')]
        with self.assertRaisesRegex(ValueError,'FINAL_FINDINGS_NOT_REPAIRED'):
            self.fixture.actual_adapter(source,before,issue,finding,self.root/'other-math/adapter',source_quantity_roles=roles)

    def test_local_ambiguity_retains_that_region_while_ordinary_region_is_repaired(self):
        folder=self.root/'mixed';folder.mkdir();source=folder/'source.pdf';mono=folder/'before.mono.pdf';dual=folder/'before.dual.pdf'
        texts=['Temperature is controlled during the experiment.','The threshold is To +23 volts.']
        with fitz.open() as doc:
            page=doc.new_page(width=500,height=340)
            for top,text in zip((45,180),texts):
                page.insert_htmlbox((30,top,470,top+60),'<p>'+html.escape(text)+'</p>',
                    css='body {font-family:sans-serif;font-size:13pt;margin:0;} p {margin:0;}')
            doc.save(source)
        shutil.copyfile(source,mono);visual.bilingual(source,mono,dual);before={'mono':mono,'dual':dual}
        with fitz.open(mono) as doc:regions=visual.regions(doc[0])
        self.assertEqual(len(regions),2)
        issues=[self.fixture.fixture.issue(region,text) for region,text in zip(regions,['实验期间温度受控。','阈值为 To，偏置为+23伏。'])]
        findings=[{'id':'f%d'%n,'page':1,**{k:v for k,v in issue.items() if k!='replacement'}} for n,issue in enumerate(issues)]
        class MixedVision(previous.Vision):
            def inspect(self,prompt,images,timeout,schema=None):
                if schema and 'before' in schema.get('properties',{}):return super().inspect(prompt,images,timeout,schema)
                self.prompts.append(prompt);return {'issues':issues},{'input_tokens':1,'output_tokens':1}
        output=folder/'adapter';output.mkdir();budget=audit.Budget(6,60)
        with mock.patch.object(visual,'NativeVision',return_value=MixedVision(issues[0])):
            with self.assertRaisesRegex(ValueError,'FINAL_FINDINGS_NOT_REPAIRED'):
                audit.visual_repairer(previous.PROVIDER,mock.Mock(capability_verified=True))(source,before,findings,budget,output)
        report=json.loads((output/'visual-repair/review-report.json').read_text(encoding='utf-8'))
        page=report['pages'][0]
        self.assertEqual([edit['region']['id'] for edit in page['accepted_repairs']],[regions[0]['id']])
        resolutions=page['attempts'][0]['finding_resolutions']
        self.assertTrue(any(row['region_id']==regions[1]['id'] and row['status']=='requires_retranslation_or_manual' for row in resolutions))
        final=output/'visual-repair/best.mono.pdf'
        with fitz.open(final) as doc:
            text=doc[0].get_text();self.assertIn('实验期间温度受控',text);self.assertIn(texts[1],text)
        self.assertTrue(visual.regression_check(mono,final,1,[regions[0]['bbox']]))
        self.assertEqual(report['status'],'needs_manual_review')

if __name__=='__main__':unittest.main()
