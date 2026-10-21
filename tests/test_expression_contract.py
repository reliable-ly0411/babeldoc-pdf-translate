"""Unary quantities and indivisible binary expressions through real PDF paths."""
import json,unittest,re
from pathlib import Path
import pymupdf as fitz
import test_repair_contract as previous
import final_audit as audit
import repair_objects
import visual_review as visual
import quantity_roles

class ExpressionTests(unittest.TestCase):
    def setUp(self):
        self.fixture=previous.ContractTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root

    def test_binary_expressions_cannot_be_split_into_independent_quantities(self):
        expressions=['5+6','5-6','17+29','17 + 29','17 +29','17+ 29','17 - 29',
            '5+-6','5 - -6','5-(-6)','(5+6)','(5)+(6)','5+6*7','(5+6)*7',
            '-(-5)','+(+5)','--5','-5^2','5^-2',
            '5:6','5–6','5—6','5(6)','5 6','5 volts:6 volts','5;6',
            '5 . 6','5. 6','5·6',
            '5 volts+6 volts','5 volts + 6 volts','theta+6','theta + 6','-5+6','5−6']
        for number,expression in enumerate(expressions):
            with self.subTest(expression=expression):
                folder=self.root/('negative-%02d'%number)
                text='Use '+expression+' as the bound, rather than two independent values.'
                # Proposed text deliberately preserves old decimal-token order
                # for the original failure; other variants are counterexamples
                # to treating any binary/grouped expression as ordinary prose.
                old_literals=re.findall(r'[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?',expression)
                replacement='界为'+old_literals[0]+''.join('，偏置为'+value for value in old_literals[1:])+'。'
                source,before,region,issue,finding=self.fixture.scenario(folder,text,replacement)
                with fitz.open(before['mono']) as doc:self.assertFalse(visual.repairable(doc[0],region,issue))
                with self.assertRaisesRegex(ValueError,'FINAL_FINDINGS_NOT_REPAIRED'):
                    self.fixture.actual_adapter(source,before,issue,finding,folder/'adapter')
                mono,dual=folder/'forced.mono.pdf',folder/'forced.dual.pdf'
                previous.pdf(mono,[replacement]);visual.bilingual(source,mono,dual);after={'mono':mono,'dual':dual}
                edits=[{'page':1,'region_id':region['id'],'bbox':region['bbox'],'method':'bounded_plain_prose'}]
                evidence=audit.repair_object_evidence(source,before,after,edits)
                check=audit.program_revalidate(source,before,after,[finding],{'repair_evidence':evidence})
                self.assertFalse(check['math_objects_passed']);self.assertFalse(check['passed'])

    def test_signed_scientific_grouped_and_unit_quantities_remain_safe(self):
        values=[('-5','-5'),('+5','+5'),('1e-3','1e-3'),('-1e-3','-1e-3'),
            ('+1.25e+2','+1.25e+2'),('(-5)','（-5）'),('(+5)','（+5）'),('−5','−5'),('5','5'),('.25','.25'),('-.25','-.25')]
        variants=[('The voltage is controlled at '+source_value+' volts.','电压被控制在'+target_value+'伏。') for source_value,target_value in values]
        variants.append(('The voltage is -5 volts and the bias is +6 volts.','电压为-5伏，偏置为+6伏。'))
        for number,(text,replacement) in enumerate(variants):
            with self.subTest(text=text):
                folder=self.root/('positive-%02d'%number)
                source,before,region,issue,finding=self.fixture.scenario(folder,text,replacement)
                roles=[]
                if number==len(variants)-1:
                    words=[('is',0),('is',1)]
                else:
                    words=[('at',0)] if values[number][0].startswith(('+','-','−','(')) else []
                if words:
                    with self.assertRaisesRegex(ValueError,'FINAL_FINDINGS_NOT_REPAIRED'):
                        self.fixture.actual_adapter(source,before,issue,finding,folder/'no-independent-role')
                    roles=[quantity_roles.confirm_from_operator(source,1,region['id'],word,occurrence=occurrence,
                        reason='Independent positive-control intent confirms this prose quantity role.') for word,occurrence in words]
                revised,budget,client=self.fixture.actual_adapter(source,before,issue,finding,folder/'adapter',source_quantity_roles=roles)
                check=audit.program_revalidate(source,before,revised['artifacts'],[finding],revised,source_quantity_roles=roles)
                self.assertTrue(check['passed']);self.assertEqual(budget.calls,2)
                evidence=json.loads((folder/'adapter/actual-edit-object-evidence.json').read_text(encoding='utf-8'))
                self.assertTrue(audit.program_revalidate(source,before,revised['artifacts'],[finding],{'repair_evidence':evidence},source_quantity_roles=roles)['passed'])

    def test_expression_tree_keeps_operator_roles_and_boundary_not_just_numeric_order(self):
        for expression in ('5+6','17 + 29','5 - -6','5 volts + 6 volts','theta + 6'):
            with self.subTest(expression=expression):
                contract=repair_objects.text_contract('Use '+expression+' as a bound.')
                self.assertFalse(contract['plain_editable'])
                trees=[token for token in contract['protected_tokens'] if token['kind']=='arithmetic_expression']
                self.assertTrue(trees)
                self.assertEqual(len(trees),1)
                self.assertIn('expression_tree',trees[0])
        text='The voltage is -5 volts and the bias is +6 volts.'
        self.assertFalse(repair_objects.text_contract(text)['plain_editable'])
        independent=repair_objects.text_contract(text,confirmed_boundaries=[match.span() for match in re.finditer(r'\bis\b',text)])
        self.assertTrue(independent['plain_editable'])
        self.assertEqual(independent['decimal_identity'],['-5','+6'])

if __name__=='__main__':unittest.main()
