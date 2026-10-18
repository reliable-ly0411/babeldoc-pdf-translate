"""Independent rc13 boundary reproductions through actual bounded receivers."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'scripts')]
import audit_receipts as durable
import chat_bridge
import final_audit as final
import native_capture
import pdf_objects
import semantic_filesystem
import semantic_offline_support as fake
import visual_review as visual
from test_semantic_final import pdf


class ReviewBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='rc14-bounds-');self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.provider={'type':'codex','model':'offline-native','retries':0,'timeout_seconds':30}
        executable=mock.patch.object(chat_bridge,'executable',return_value='offline-codex')
        executable.start();self.addCleanup(executable.stop)

    def client(self,raw):
        client=visual.NativeVision(self.provider)
        def invoke(argv,prompt,**options):
            Path(argv[argv.index('-o')+1]).write_bytes(raw)
            return SimpleNamespace(returncode=0,stdout='{"type":"turn.completed","usage":{"input_tokens":9,"output_tokens":4}}\n',stderr='PRIVATE_TRANSPORT_MARKER')
        return client,invoke

    def test_65537_answer_preserves_explicit_prefix_capture_and_native_usage_before_rejection(self):
        raw=b'A'*65537;client,invoke=self.client(raw);folder=self.root/'oversize'
        with mock.patch.object(client.native,'invoke',side_effect=invoke):
            with self.assertRaises(chat_bridge.BridgeError) as error:
                client.inspect_raw('fixture',[],30,schema={'type':'object'},record_dir=folder)
        self.assertEqual(error.exception.code,'VISION_ANSWER_INCOMPLETE_CAPTURE')
        self.assertEqual(error.exception.native_usage,{'input_tokens':9,'output_tokens':4})
        self.assertEqual((folder/'answer.prefix').read_bytes(),raw[:65536])
        self.assertFalse((folder/'answer.raw').exists())
        value=json.loads((folder/'capture.json').read_text(encoding='utf-8'))
        self.assertEqual(value['answer_capture']['observed_file_bytes'],65537)
        self.assertEqual(value['answer_capture']['captured_bytes'],65536)
        self.assertFalse(value['answer_capture']['complete_capture'])
        self.assertIsNone(value['answer_sha256'])
        self.assertEqual(value['answer_capture']['captured_prefix_sha256'],hashlib.sha256(raw[:65536]).hexdigest())
        self.assertTrue((folder/'stdout.utf8').is_file())
        self.assertNotIn(b'PRIVATE_TRANSPORT_MARKER',(folder/'capture.json').read_bytes())

    def test_exact_capture_boundary_and_no_capture_bridge_boundary(self):
        client,invoke=self.client(b'A'*65536)
        with mock.patch.object(client.native,'invoke',side_effect=invoke):
            raw,_=client.inspect_raw('fixture',[],30,record_dir=self.root/'exact')
        self.assertEqual(len(raw),65536)
        client,invoke=self.client(b'A'*(chat_bridge.MAX_REPLY+1))
        with mock.patch.object(client.native,'invoke',side_effect=invoke):
            with self.assertRaisesRegex(chat_bridge.BridgeError,'VISION_ANSWER_INCOMPLETE_CAPTURE'):
                client.inspect_raw('fixture',[],30)

    def test_actual_receiver_reads_at_most_one_extra_byte_and_never_fakes_full_hash(self):
        path=self.root/'large';path.write_bytes(b'B'*(2*1024*1024));calls=[];original=Path.open
        class Reader:
            def __enter__(self):self.stream=original(path,'rb');return self
            def __exit__(self,*args):self.stream.close()
            def fileno(self):return self.stream.fileno()
            def read(self,size=-1):
                calls.append(size)
                if size<0 or size>65537:raise AssertionError('UNBOUNDED READ')
                return self.stream.read(size)
        with mock.patch.object(Path,'open',return_value=Reader()):
            prefix,value=native_capture.observe(path,65536)
        self.assertEqual(calls,[65537]);self.assertEqual(len(prefix),65536)
        self.assertEqual(value['observed_file_bytes'],2*1024*1024)
        self.assertIsNone(value['full_sha256']);self.assertFalse(value['complete_capture'])

    def test_null_native_glyph_mask_is_rejected_before_pixmap_conversion(self):
        # The actual Windows probe produced a null native pixmap for a large
        # glyph. Passing it into Pixmap causes a native access violation.
        with mock.patch.object(pdf_objects.m,'fz_bound_glyph',return_value=pdf_objects.m.FzRect(0,0,2,2)), \
             mock.patch.object(pdf_objects.m,'fz_render_glyph_pixmap',return_value=SimpleNamespace(m_internal=None)), \
             mock.patch.object(pdf_objects.fitz,'Pixmap',side_effect=AssertionError('NULL PIXMAP CONVERSION')) as convert:
            with self.assertRaisesRegex(ValueError,'NATIVE_CLIP_MASK_UNAVAILABLE'):
                pdf_objects.sampled_clip_ink(None,0,pdf_objects.m.FzMatrix(),pdf_objects.fitz.Rect(0,0,10,10))
        convert.assert_not_called()

    def test_real_deep_atomic_probe_cleans_only_its_new_directories(self):
        root=self.root/'output';root.mkdir();unrelated=root/'untouched';unrelated.write_bytes(b'original')
        result=semantic_filesystem.preflight(root/'s00')
        self.assertTrue(result['same_directory_atomic_publish'])
        self.assertFalse((root/'s00').exists());self.assertEqual(unrelated.read_bytes(),b'original')

    def test_atomic_or_deep_path_failure_is_before_visual_and_semantic_calls(self):
        source=self.root/'source.pdf';mono=self.root/'mono.pdf';dual=self.root/'dual.pdf'
        box=(30,40,410,90);pdf(source,[(box,'The controller stabilizes the vehicle.')]);pdf(mono,[(box,'控制器使飞行器保持稳定。')])
        visual.bilingual(source,mono,dual);client=mock.Mock()
        with mock.patch.object(semantic_filesystem.durable,'publish',side_effect=FileNotFoundError('synthetic269 boundary')):
            result=final.run(source,{'mono':mono,'dual':dual},self.root/'audit',client,**fake.options())
        self.assertEqual(result['model_calls'],0);client.assert_not_called()
        self.assertEqual(result['error_code'],'FINAL_AUDIT_DURABLE_PATH_UNSUPPORTED')

    def test_native_windows_170_output_checks_actual_269_pending_path(self):
        # Records host capability without changing long-path OS settings.
        stem='z'*(170-len(str(self.root))-1);output=self.root/stem
        self.assertEqual(len(str(output)),170)
        try:
            result=semantic_filesystem.preflight(output/'s00')
            self.assertTrue(result['passed'])
        except ValueError as error:
            self.assertEqual(str(error),'FINAL_AUDIT_DURABLE_PATH_UNSUPPORTED')
        self.assertFalse(output.exists())


if __name__=='__main__':unittest.main()
