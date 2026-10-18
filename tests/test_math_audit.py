"""A delimiter count alone must not hide changed mathematical arguments."""
import unittest
from audit_l1quad_page5 import v0_arguments


class FormulaAuditTests(unittest.TestCase):
    def test_complete_nested_arguments_and_whitespace(self):
        self.assertEqual(v0_arguments('V 0 = V (e p(0),e v(0),e R(0),e Ω(0)).'),
            ['ep(0)','ev(0)','eR(0)','eΩ(0)'])

    def test_lost_separators_are_observable(self):
        self.assertEqual(len(v0_arguments('V0=V(ep(0)ev(0)eR(0)eΩ(0))')),1)

    def test_changed_argument_order_is_not_equivalent(self):
        self.assertNotEqual(v0_arguments('V0=V(ep(0),ev(0),eR(0),eΩ(0))'),
            v0_arguments('V0=V(ev(0),ep(0),eR(0),eΩ(0))'))

    def test_unclosed_or_missing_definition_is_not_success(self):
        for text in ('V0=V(ep(0),ev(0)', 'V0+1'):
            with self.assertRaises(ValueError):v0_arguments(text)


if __name__=='__main__':unittest.main()
