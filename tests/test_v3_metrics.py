import unittest
import numpy as np
from experiments.v3.contracts import TargetBatch
from experiments.v3.evaluate import score_match
from validation.metrics import pm


class MetricTests(unittest.TestCase):
    def test_unknown_prediction_frame_miss_temporal_fill(self):
        truth = TargetBatch(np.array([0,0,0,1,1,1],np.int8), '0'*64)
        r = score_match(truth, np.array([3,0,0,1,3,1],np.int8), np.ones(6,np.int16), 25.)
        self.assertEqual(r['graded_frames'], 6)
        self.assertEqual(r['spell_f1_mean'], 1.)
        self.assertLess(r['H_f1'], 1.)

    def score(self,y,p,periods=None):
        return score_match(TargetBatch(np.array(y,np.int8),'0'*64),np.array(p,np.int8),
            np.ones(len(y),np.int16) if periods is None else np.array(periods,np.int16),25.)

    def test_pooled_spell_counts_not_team_average(self):
        y=[0,0,2,0,0,2,0,0,2,1,1]; p=[0,0,2,0,0,2,0,0,2,0,0]
        r=self.score(y,p)
        self.assertAlmostEqual(r['spell_f1_mean'],6/8)
        self.assertNotAlmostEqual(r['spell_f1_mean'],(6/7+0)/2)

    def test_short_unknown_gap_cannot_match_transitions(self):
        y=[0,1,-1,0,0]; p=[0,0,3,0,1]
        r=self.score(y,p)
        for tol in (12,25):
            self.assertEqual(r['transitions_'+str(tol)],dict(tp=0,fp=1,fn=1,precision=0.,recall=0.,f1=0.))

    def test_adjacent_periods_cannot_match(self):
        r=self.score([0,1,0,0],[0,0,0,1],[1,1,2,2])
        self.assertEqual(r['transitions_25']['tp'],0)
        self.assertEqual(r['transitions_25']['fn'],1)

    def test_transition_inclusive_edges_and_destination_type(self):
        for tol in (12,25):
            y=[0]*40+[1]*70
            for shift in (-tol,tol):
                p=[0]*(40+shift)+[1]*(70-shift)
                self.assertEqual(self.score(y,p)['transitions_'+str(tol)]['tp'],1)
            p=[0]*(41+tol)+[1]*(69-tol)
            self.assertEqual(self.score(y,p)['transitions_'+str(tol)]['tp'],0)
            self.assertEqual(self.score(y,[0]*40+[2]*70)['transitions_'+str(tol)]['tp'],0)

    def test_all_x_and_absent_classes_are_zero(self):
        r=self.score([0]*10,[3]*10)
        self.assertEqual(r['spell_f1_mean'],0.)
        self.assertEqual(r['macro_f1'],0.)
        r=self.score([0]*10,[0]*10)
        self.assertAlmostEqual(r['macro_f1'],1/3)

    def test_dead_splits_spells_no_dead_spells(self):
        r=self.score([0,0,2,2,0,0],[0,0,2,2,0,0])
        self.assertEqual(r['spells']['n_gt'],2)
        self.assertEqual(self.score([2]*4,[2]*4)['spell_f1_mean'],0.)

    def test_inactive_known_truth_does_not_score(self):
        r=self.score([0,0,0],[1,0,1],[0,1,0])
        self.assertEqual(r['graded_frames'],1)
        self.assertEqual(r['H_f1'],1.)

    def test_non_native_fps_and_float_codes_refused(self):
        t=TargetBatch(np.zeros(3,np.int8),'0'*64)
        with self.assertRaises(ValueError): score_match(t,np.zeros(3,np.int8),np.ones(3,np.int16),24.)
        with self.assertRaises(ValueError): score_match(t,np.zeros(3,float),np.ones(3,np.int16),25.)


if __name__ == '__main__': unittest.main()
