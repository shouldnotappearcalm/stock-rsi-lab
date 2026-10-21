from pathlib import Path
import importlib
import importlib.util
import struct
import tempfile
import unittest


class Pre2026BinaryCapTests(unittest.TestCase):
    def helper(self):
        name = 'scripts.prepare_price_delay_provider_pre2026'
        if importlib.util.find_spec(name) is None:
            self.fail('physical pre2026 provider preparation has not been implemented')
        return importlib.import_module(name).clip_feature

    def test_copies_original_prefix_with_start_offset_and_no_future_float(self):
        clip = self.helper()
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); source = root/'source.bin'; target = root/'target.bin'
            source.write_bytes(struct.pack('<4f', 1, 20, 30, 999))
            meta = clip(source, target, 2, 4)
            self.assertEqual(target.read_bytes(), struct.pack('<3f', 1, 20, 30))
            self.assertEqual(meta['last_index'], 2)
            self.assertEqual(meta['copied_values'], 2)

    def test_future_tail_perturbation_cannot_change_output(self):
        clip = self.helper()
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); source = root/'source.bin'
            source.write_bytes(struct.pack('<5f', 0, 10, 20, 30, 999))
            clip(source, root/'first.bin', 2, 4)
            source.write_bytes(struct.pack('<5f', 0, 10, 20, 30, -12345))
            clip(source, root/'second.bin', 2, 4)
            self.assertEqual((root/'first.bin').read_bytes(), (root/'second.bin').read_bytes())

    def test_future_only_feature_is_not_written_and_existing_output_is_preserved(self):
        clip = self.helper()
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); source = root/'source.bin'; target = root/'target.bin'
            source.write_bytes(struct.pack('<2f', 3, 999))
            self.assertIsNone(clip(source, target, 2, 4))
            self.assertFalse(target.exists())
            target.write_bytes(b'keep')
            with self.assertRaises(ValueError): clip(source, target, 2, 4)
            self.assertEqual(target.read_bytes(), b'keep')

    def test_invalid_header_or_extent_fails_before_output(self):
        clip = self.helper()
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); source = root/'source.bin'; target = root/'target.bin'
            for data in (b'bad', struct.pack('<2f', .5, 10), struct.pack('<2f', -1, 10), struct.pack('<3f', 3, 10, 20)):
                source.write_bytes(data)
                with self.assertRaises(ValueError): clip(source, target, 2, 4)
                self.assertFalse(target.exists())


if __name__ == '__main__': unittest.main()
