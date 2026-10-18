"""Generated keyword/identifier collisions and actual PDF boundary contracts."""
import itertools,json,unittest
from unittest import mock
import pymupdf as fitz
import test_repair_contract as previous
import expression_syntax as syntax
import repair_objects
import final_audit as audit
import visual_review as visual
import quantity_roles

class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.fixture=previous.ContractTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups);self.root=self.fixture.root

    def test_original_compact_boundary_collisions_are_rejected(self):
        for number,(operand,op,value) in enumerate((('To','+','23'),('In','-','41'),('by','+','23'))):
            with self.subTest(operand=operand):
                folder=self.root/('original-%02d'%number)
                source,before,region,issue,finding=self.fixture.scenario(folder,'Use '+operand+op+value+' as the bound.','界为 '+operand+'，偏置为'+op+value+'。')
                with self.assertRaisesRegex(ValueError,'FINAL_FINDINGS_NOT_REPAIRED'):
                    self.fixture.actual_adapter(source,before,issue,finding,folder/'adapter')

    def test_generated_boundary_spellings_cases_spaces_and_operators_keep_binary_role(self):
        for word in sorted(syntax.PROSE_BOUNDARIES):
            variants={word,word.title(),word.upper(),''.join(c.upper() if i%2 else c for i,c in enumerate(word))}
            for spelling,left,op,right in itertools.product(variants,('', ' ', '  ', '\t'),('+','-'),('',' ')):
                expression=spelling+left+op+right+'79'
                with self.subTest(expression=expression):
                    contract=repair_objects.text_contract('Use '+expression+' as the bound.')
                    self.assertFalse(contract['plain_editable'])
                    self.assertTrue(any(token['kind']=='arithmetic_expression' for token in contract['protected_tokens']))

    def test_actual_boundary_collision_family_rejects_adapter_postcheck_and_json_replay(self):
        combinations=list(itertools.product(('To','IN','by','at','Is','equals'),('',' '),('+','-'),('',' ')))
        for number,(word,gap,op,right_gap) in enumerate(combinations):
            folder=self.root/('negative-%02d'%number);value='23' if op=='+' else '41'
            source,before,region,issue,finding=self.fixture.scenario(folder,'Use '+word+gap+op+right_gap+value+' as the bound.','界为 '+word+'，偏置为'+op+value+'。')
            with self.assertRaisesRegex(ValueError,'FINAL_FINDINGS_NOT_REPAIRED'):
                self.fixture.actual_adapter(source,before,issue,finding,folder/'adapter')
            mono,dual=folder/'forced.mono.pdf',folder/'forced.dual.pdf';previous.pdf(mono,[issue['replacement']]);visual.bilingual(source,mono,dual)
            after={'mono':mono,'dual':dual};edits=[{'page':1,'region_id':region['id'],'bbox':region['bbox'],'method':'bounded_plain_prose'}]
            evidence=audit.repair_object_evidence(source,before,after,edits)
            for supplied in (evidence,json.loads(json.dumps(evidence))):
                check=audit.program_revalidate(source,before,after,[finding],{'repair_evidence':supplied})
                self.assertFalse(check['math_objects_passed']);self.assertFalse(check['passed'])

    def test_real_prose_prepositions_copulas_case_and_quantities_remain_repairable(self):
        sources=[('The voltage is fixed at +23 volts.','电压固定为+23伏。','at'),
            ('The voltage is limited to -41 volts.','电压限制为-41伏。','to'),
            ('The voltage is adjusted by +23 volts.','电压调整了+23伏。','by'),
            ('The voltage is +23 volts.','电压为+23伏。','is'),
            ('THE VOLTAGE IS FIXED AT +23 VOLTS.','电压固定为+23伏。','AT'),
            ('The voltage is fixed At +23 volts.','电压固定为+23伏。','At'),
            ('The voltage is fixed at 1e-3 volts.','电压固定为1e-3伏。',None),
            ('The voltage is fixed at (-5) volts.','电压固定为（-5）伏。','at')]
        sources.extend([('The voltage is fixed at + 23 volts.','电压固定为+23伏。','at'),
            ('The voltage is limited to - 41 volts.','电压限制为-41伏。','to'),
            ('The constant is +23.','常数为+23。','is')])
        for number,(text,replacement,left_word) in enumerate(sources):
            with self.subTest(text=text):
                folder=self.root/('positive-%02d'%number)
                source,before,region,issue,finding=self.fixture.scenario(folder,text,replacement)
                roles=[]
                if left_word:
                    with self.assertRaisesRegex(ValueError,'FINAL_FINDINGS_NOT_REPAIRED'):
                        self.fixture.actual_adapter(source,before,issue,finding,folder/'no-independent-role')
                    roles=[quantity_roles.confirm_from_operator(source,1,region['id'],left_word,
                        reason='Declared positive-control semantic oracle: this is a prose quantity, not a named operand.')]
                revised,budget,client=self.fixture.actual_adapter(source,before,issue,finding,folder/'adapter',source_quantity_roles=roles)
                supplied=json.loads(json.dumps(revised['repair_evidence']))
                self.assertTrue(audit.program_revalidate(source,before,revised['artifacts'],[finding],{'repair_evidence':supplied},source_quantity_roles=roles)['passed'])

if __name__=='__main__':unittest.main()
