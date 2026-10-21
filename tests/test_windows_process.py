"""Real Windows process-tree tests; no model, network, or credentials."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import chat_bridge as b


@unittest.skipUnless(os.name == 'nt', 'Windows Job Object regression')
class WindowsTreeTests(unittest.TestCase):
    def test_cleanup_modes_and_unrelated_process(self):
        sentinel = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        try:
            for mode in ('normal', 'timeout', 'cancel', 'output'):
                with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                    pidfile = Path(tmp) / 'pid'
                    child = "import time; time.sleep(30)"
                    script = ("import subprocess,sys,time,pathlib; "
                              "p=subprocess.Popen([sys.executable,'-c'," + repr(child) + "]); "
                              "pathlib.Path(" + repr(str(pidfile)) + ").write_text(str(p.pid)); "
                              + ("print('x'*200000,flush=True); " if mode == 'output' else '')
                              + ('time.sleep(30)' if mode != 'normal' else 'time.sleep(.2)'))
                    cancel = threading.Event()
                    timer = threading.Timer(.8, cancel.set) if mode == 'cancel' else None
                    if timer: timer.start()
                    start = time.monotonic()
                    try:
                        if mode == 'normal':
                            self.assertEqual(b.run_bounded([sys.executable, '-c', script], '', 5).returncode, 0)
                        else:
                            expected = {'timeout':'TIMEOUT','cancel':'CANCELLED','output':'OUTPUT_LIMIT'}[mode]
                            with self.assertRaises(b.BridgeError) as caught:
                                b.run_bounded([sys.executable, '-c', script], '', 1 if mode == 'timeout' else 5,
                                              cancel=cancel, limit=10000)
                            self.assertEqual(caught.exception.code, expected)
                    finally:
                        if timer: timer.cancel()
                    self.assertLess(time.monotonic() - start, 8)
                    self.assertTrue(pidfile.exists())
                    import ctypes
                    api = ctypes.WinDLL('kernel32', use_last_error=True)
                    api.OpenProcess.restype = ctypes.c_void_p
                    handle = api.OpenProcess(0x1000, False, int(pidfile.read_text()))
                    if handle:
                        code = ctypes.c_ulong()
                        api.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
                        api.CloseHandle(ctypes.c_void_p(handle))
                        self.assertNotEqual(code.value, 259, 'Grandchild is still alive')
                    self.assertIsNone(sentinel.poll(), 'Unrelated process was terminated')
        finally:
            sentinel.terminate(); sentinel.wait(timeout=5)



if __name__ == '__main__': unittest.main()
