"""Portable tree inference checks using fabricated trees/training observations."""
import builtins
import importlib
import json
import unittest
from unittest.mock import patch

import numpy as np

import possession_model.trees as trees_module
from possession_model.trees import TreeModel, export_sklearn


def stump(target, feature, threshold, missing_left, left_value, right_value):
    return {"class": target, "nodes": {
        "value": [0., left_value, right_value], "feature_idx": [feature, 0, 0],
        "num_threshold": [threshold, 0., 0.],
        "missing_go_to_left": [missing_left, False, False],
        "left": [1, 0, 0], "right": [2, 0, 0], "is_leaf": [False, True, True]}}


def invented_document():
    return {"format": "numeric-hgb-v1", "feature_names": ["first", "second"],
            "baseline": [.1, .2, .3],
            "trees": [stump(0, 0, 1., False, 2., -3.),
                      stump(1, 1, 0., True, 4., 5.)]}


class TreeTests(unittest.TestCase):
    def test_missing_routes_and_threshold_equality(self):
        model = TreeModel(invented_document())
        matrix = np.array([[0., 1.], [2., -1.], [np.nan, np.nan], [1., 0.]])
        actual = model.raw_scores(matrix, ["first", "second"])
        expected = [[2.1, 5.2, .3], [-2.9, 4.2, .3],
                    [-2.9, 4.2, .3], [2.1, 4.2, .3]]
        np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-14)

    def test_chunking_is_identical_and_inputs_are_unchanged(self):
        model = TreeModel(invented_document())
        matrix = np.array([[0., 1.], [2., -1.], [np.nan, np.nan], [1., 0.]], dtype=np.float32)
        original = matrix.copy()
        reference = model.raw_scores(matrix, model.names, chunk_size=8192)
        for chunk_size in (1, 2, 3, 7):
            np.testing.assert_array_equal(model.raw_scores(matrix, model.names, chunk_size), reference)
        np.testing.assert_array_equal(matrix, original)

    def test_invalid_chunk_size_cannot_return_uninitialised_output(self):
        model = TreeModel(invented_document())
        for chunk_size in (0, -1):
            with self.subTest(chunk_size=chunk_size):
                with self.assertRaises(ValueError):
                    model.raw_scores(np.zeros((2, 2)), model.names, chunk_size)

    def test_feature_schema_and_format_are_validated(self):
        model = TreeModel(invented_document())
        for matrix, names in ((np.zeros((2, 2)), ["second", "first"]),
                              (np.zeros((2, 3)), model.names), (np.zeros(2), model.names)):
            with self.assertRaises(ValueError):
                model.raw_scores(matrix, names)
        with self.assertRaises(ValueError):
            TreeModel({"format": "other"})

    def test_finite_log_scores_and_empty_input(self):
        model = TreeModel(invented_document())
        scores = model.scores(np.array([[0., 1.], [np.nan, np.nan]]), model.names)
        self.assertEqual(scores.dtype, np.float32)
        self.assertTrue(np.isfinite(scores).all())
        self.assertTrue(((scores >= -8) & (scores <= 0)).all())
        np.testing.assert_allclose(np.exp(scores).sum(axis=1), 1., atol=1e-6)
        self.assertEqual(model.raw_scores(np.empty((0, 2)), model.names).shape, (0, 3))
        self.assertEqual(model.scores(np.empty((0, 2)), model.names).shape, (0, 3))

    def test_runtime_module_import_and_inference_need_no_sklearn(self):
        original_import = builtins.__import__
        def guarded_import(name, *args, **kwargs):
            if name == "sklearn" or name.startswith("sklearn."):
                raise AssertionError("Runtime attempted to import training dependency")
            return original_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=guarded_import):
            runtime = importlib.reload(trees_module)
            model = runtime.TreeModel(invented_document())
            result = model.raw_scores(np.array([[np.nan, 0.]]), model.names)
        np.testing.assert_allclose(result, [[-2.9, 4.2, .3]])

    def test_sklearn_numeric_export_matches_training_predictor(self):
        try:
            from sklearn.ensemble import HistGradientBoostingClassifier
        except ImportError:
            self.skipTest("scikit-learn is optional and used for export verification only")
        rng = np.random.default_rng(1307)
        matrix = rng.normal(size=(360, 4)).astype(np.float32)
        labels = np.argmax(np.column_stack([matrix[:, 0], matrix[:, 1], -matrix[:, 0]]), axis=1)
        matrix[rng.random(matrix.shape) < .18] = np.nan
        estimator = HistGradientBoostingClassifier(
            max_iter=8, max_leaf_nodes=7, min_samples_leaf=7,
            learning_rate=.2, random_state=103, early_stopping=False).fit(matrix, labels)
        names = ["f0", "f1", "f2", "f3"]
        document = export_sklearn(estimator, names, {"scope": "invented test data"})
        # JSON round-trip also exercises the actual deployable numeric format.
        model = TreeModel(json.loads(json.dumps(document, allow_nan=False)))
        query = rng.normal(size=(71, 4)).astype(np.float32)
        query[rng.random(query.shape) < .25] = np.nan
        np.testing.assert_allclose(model.raw_scores(query, names, chunk_size=13),
                                   estimator._raw_predict(query), rtol=1e-12, atol=1e-12)


if __name__ == "__main__":
    unittest.main()
