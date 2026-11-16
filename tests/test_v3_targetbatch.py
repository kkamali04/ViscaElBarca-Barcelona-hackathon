"""Invented label-only ownership regressions; independent acceptance is separate."""
import unittest

import numpy as np

from experiments.v3.contracts import TargetBatch


class TargetBatchSnapshotTests(unittest.TestCase):
    def assert_snapshot(self, source):
        values = source.copy()
        writable = source.flags.writeable
        batch = TargetBatch(source, "a" * 64)
        self.assertIsNot(batch.labels, source)
        self.assertFalse(np.shares_memory(batch.labels, source))
        self.assertTrue(batch.labels.flags.owndata)
        self.assertTrue(batch.labels.flags.c_contiguous)
        self.assertFalse(batch.labels.flags.writeable)
        self.assertEqual(source.flags.writeable, writable)
        np.testing.assert_array_equal(batch.labels, values)
        self.assertEqual(batch.labels.dtype, np.dtype(np.int8))
        self.assertEqual(batch.observation_digest, "a" * 64)
        return batch

    def test_readonly_owner_can_restore_flags_without_changing_snapshot(self):
        source = np.array([-1, 0, 1, 2], dtype=np.int8)
        source.flags.writeable = False
        batch = self.assert_snapshot(source)
        source.flags.writeable = True
        source[:] = 2
        np.testing.assert_array_equal(batch.labels, [-1, 0, 1, 2])
        self.assertFalse(batch.labels.flags.writeable)

    def test_writable_owner_mutation_and_flags_preserved(self):
        source = np.array([0, 1, 2], dtype=np.int8)
        batch = self.assert_snapshot(source)
        source[:] = -1
        np.testing.assert_array_equal(batch.labels, [0, 1, 2])
        self.assertTrue(source.flags.writeable)

    def test_strided_and_readonly_views_do_not_alias_their_owner(self):
        for readonly in (False, True):
            with self.subTest(readonly=readonly):
                owner = np.array([-1, 0, 1, 2], dtype=np.int8)
                source = owner[::-1]
                source.flags.writeable = not readonly
                batch = self.assert_snapshot(source)
                owner[:] = -1
                np.testing.assert_array_equal(batch.labels, [2, 1, 0, -1])
                self.assertEqual(source.flags.writeable, not readonly)

    def test_contiguous_readonly_view_and_independent_batches(self):
        owner = np.array([-1, 0, 1, 2], dtype=np.int8)
        view = owner[1:]
        view.flags.writeable = False
        first = self.assert_snapshot(view)
        second = self.assert_snapshot(view)
        self.assertFalse(np.shares_memory(first.labels, second.labels))
        owner[:] = -1
        np.testing.assert_array_equal(first.labels, [0, 1, 2])
        np.testing.assert_array_equal(second.labels, [0, 1, 2])

    def test_empty_and_singleton_snapshots(self):
        for values in ([], [-1], [0], [1], [2]):
            for readonly in (False, True):
                with self.subTest(values=values, readonly=readonly):
                    source = np.array(values, dtype=np.int8)
                    source.flags.writeable = not readonly
                    self.assert_snapshot(source)

    def test_exact_array_dtype_and_vector_shape_preserved(self):
        for source in ([0], np.array([0], dtype=np.int64), np.array([0.], dtype=np.float32),
                       np.array([True]), np.array(0, dtype=np.int8), np.array([[0]], dtype=np.int8)):
            with self.subTest(source=repr(source)), self.assertRaises(ValueError):
                TargetBatch(source, "a" * 64)

    def test_illegal_codes_rejected_without_changing_caller_flags(self):
        for code in (-128, -2, 3, 127):
            for readonly in (False, True):
                source = np.array([0, code], dtype=np.int8)
                source.flags.writeable = not readonly
                with self.subTest(code=code, readonly=readonly), self.assertRaises(ValueError):
                    TargetBatch(source, "a" * 64)
                self.assertEqual(source.flags.writeable, not readonly)
                np.testing.assert_array_equal(source, [0, code])


if __name__ == "__main__":
    unittest.main()
