"""Verify the installed engine's declared bitstring contract and byte API."""
import importlib.metadata as metadata
import unittest
from packaging.requirements import Requirement


class DependencyCompatibilityTests(unittest.TestCase):
    def test_bitstring_version_satisfies_engine_and_its_bitarray_requirement(self):
        requirements=[Requirement(r) for r in metadata.requires('babeldoc')]
        requirement=next(r for r in requirements if r.name.lower()=='bitstring')
        self.assertIn(metadata.version('bitstring'),requirement.specifier)
        for item in metadata.requires('bitstring'):
            dependency=Requirement(item)
            if dependency.name.lower()=='bitarray':
                self.assertIn(metadata.version('bitarray'),dependency.specifier)

    def test_babeldoc_render_stream_api_handles_nested_bytes_without_conversion(self):
        from babeldoc.format.pdf.document_il.backend.pdf_creater import BitStream
        path=BitStream(b'10 20 m 30 40 l ')
        stream=BitStream(b'q ')
        stream.append(path)
        stream.append(b'S Q\n')
        self.assertEqual(stream.tobytes(),b'q 10 20 m 30 40 l S Q\n')


if __name__=='__main__':
    unittest.main()
