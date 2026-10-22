"""Compiler guardrails; set TITBIT_WASM_VARARGS to the LLVM 18 helper executable."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HELPER = os.environ.get('TITBIT_WASM_VARARGS')
HEADER = '''target triple = "i386-pc-windows-msvc"
target datalayout = "e-p:32:32-i64:64-n8:16:32-S32"
'''


@unittest.skipUnless(HELPER, 'TITBIT_WASM_VARARGS is not set')
class PackedVarargsTests(unittest.TestCase):
    def lower(self, text):
        with tempfile.TemporaryDirectory() as folder:
            source, output = [Path(folder) / name for name in ('input.ll', 'output.ll')]
            source.write_text(text)
            result = subprocess.run([HELPER, str(source), str(output)],
                                    capture_output=True, text=True)
            return result, output.read_text() if output.exists() else ''

    def test_native_libc_cannot_bind_to_packed_import(self):
        result, text = self.lower(HEADER + '''
declare i32 @printf(ptr, ...)
define i32 @run(ptr %fmt) {
  %r = call i32 (ptr, ...) @printf(ptr %fmt, i32 17, double 4.25)
  ret i32 %r
}
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('@titbit_va_printf(', text)
        self.assertNotIn('@printf(', text)

    def test_wrong_target_fails(self):
        result, text = self.lower(HEADER.replace('i386-pc-windows-msvc', 'wasm32-unknown-unknown'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('expected Microsoft i386 source IR', result.stderr)
        self.assertEqual(text, '')

    def test_namespace_collision_fails(self):
        result, text = self.lower(HEADER + '''
declare i32 @printf(ptr, ...)
declare i32 @titbit_va_printf(ptr, ptr)
''')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('reserved packed-varargs symbol collision', result.stderr)
        self.assertEqual(text, '')

    def test_musttail_cannot_leave_dangling_slots(self):
        result, text = self.lower(HEADER + '''
declare i32 @target(i32, ...)
define i32 @source(i32 %x, ...) {
  %r = musttail call i32 (i32, ...) @target(i32 %x, ...)
  ret i32 %r
}
''')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('musttail cannot pass a caller-owned buffer', result.stderr)
        self.assertEqual(text, '')

    def test_raw_va_arg_requires_source_adapter(self):
        result, text = self.lower(HEADER + '''
define double @source(ptr %args) {
  %r = va_arg ptr %args, double
  ret double %r
}
''')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('va_arg instruction requires source slot macros', result.stderr)
        self.assertEqual(text, '')


if __name__ == '__main__':
    unittest.main()
