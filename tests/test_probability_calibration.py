import unittest
import os
import sqlite3
import tempfile
import probability_calibration

class TestProbabilityCalibration(unittest.TestCase):

    def test_brier_score_empty(self):
        self.assertEqual(probability_calibration.brier_score([], []), 0.25)

    def test_brier_score_perfect(self):
        preds = [1.0] * 15 + [0.0] * 15
        outs = [1] * 15 + [0] * 15
        self.assertEqual(probability_calibration.brier_score(preds, outs), 0.0)

    def test_brier_score_random(self):
        preds = [0.5] * 30
        outs = [1, 0] * 15
        self.assertEqual(probability_calibration.brier_score(preds, outs), 0.25)

    def test_brier_score_mismatched(self):
        self.assertEqual(probability_calibration.brier_score([1.0]*30, [1]*29), 0.25)

    def test_brier_score_insufficient_samples(self):
        self.assertEqual(probability_calibration.brier_score([1.0]*29, [1]*29), 0.25)

    def test_calibration_bins_empty(self):
        self.assertEqual(probability_calibration.calibration_bins([], []), [])

    def test_calibration_bins_grouping(self):
        preds = [0.1, 0.15, 0.9, 0.95]
        outs = [0, 0, 1, 1]
        bins = probability_calibration.calibration_bins(preds, outs)
        # Should have 2 bins: [0.1, 0.2) and [0.9, 1.0)
        self.assertEqual(len(bins), 2)
        self.assertEqual(bins[0]['count'], 2)
        self.assertEqual(bins[1]['count'], 2)

    def test_kelly_cap_poor_score(self):
        self.assertEqual(probability_calibration.kelly_cap_from_calibration(0.25, 30), 0.02)
        self.assertEqual(probability_calibration.kelly_cap_from_calibration(0.3, 30), 0.02)

    def test_kelly_cap_perfect_score(self):
        # Even perfect calibration gets capped at 0.15 by design
        self.assertEqual(probability_calibration.kelly_cap_from_calibration(0.0, 30), 0.15)

    def test_kelly_cap_insufficient_samples(self):
        self.assertEqual(probability_calibration.kelly_cap_from_calibration(0.0, 29), 0.05)

    def test_kelly_cap_at_known_calibration_levels(self):
        """Known win rates should produce expected Kelly caps."""
        # Perfect calibration (brier=0.0): cap = 0.15
        cap_perfect = probability_calibration.kelly_cap_from_calibration(0.0, n_samples=50)
        self.assertEqual(cap_perfect, 0.15)
        
        # Random calibration (brier=0.25): cap = 0.02
        cap_random = probability_calibration.kelly_cap_from_calibration(0.25, n_samples=50)
        self.assertEqual(cap_random, 0.02)
        
        # Poor but not terrible (brier=0.12): cap interpolated
        cap_mid = probability_calibration.kelly_cap_from_calibration(0.12, n_samples=50)
        self.assertGreater(cap_mid, 0.02)
        self.assertLess(cap_mid, 0.15)
        
        # Insufficient samples (< 30): falls back to conservative 0.05
        cap_few = probability_calibration.kelly_cap_from_calibration(0.0, n_samples=29)
        self.assertEqual(cap_few, 0.05)
        
        # Brier = 0.25 + small epsilon (exactly at threshold — also 0.02)
        cap_at_edge = probability_calibration.kelly_cap_from_calibration(0.251, n_samples=50)
        self.assertEqual(cap_at_edge, 0.02)
        
        # Calibration with very poor score (>0.3) still capped at 0.02
        cap_terrible = probability_calibration.kelly_cap_from_calibration(0.35, n_samples=50)
        self.assertEqual(cap_terrible, 0.02)

    def test_brier_score_with_known_outcomes(self):
        """Brier score on known prediction/outcome pairs."""
        # 80% win rate, predicted 70% consistently
        preds_biased = [0.7] * 100
        outs_biased = [1 if i < 80 else 0 for i in range(100)]
        bs = probability_calibration.brier_score(preds_biased, outs_biased)
        # expected Brier = 0.7^2*0.2 + 0.3^2*0.8 ... no let's compute:
        # (0.7-1)^2*80 + (0.7-0)^2*20 = 0.09*80 + 0.49*20 = 7.2 + 9.8 = 17.0
        # mean = 17/100 = 0.17
        self.assertAlmostEqual(bs, 0.17, places=2)
        
        # 60% win rate, well-calibrated predictions around 0.6
        preds_calibrated = [0.6] * 60 + [0.4] * 40
        outs_calibrated = [1] * 60 + [0] * 40
        bs_cal = probability_calibration.brier_score(preds_calibrated, outs_calibrated)
        # (0.6-1)^2*60 + (0.4-0)^2*40 = 0.16*60 + 0.16*40 = 16
        # mean = 16/100 = 0.16
        self.assertAlmostEqual(bs_cal, 0.16, places=2)

    def test_load_calibration_from_trades(self):
        # Create temp DB
        with tempfile.NamedTemporaryFile(delete=False) as f:
            db_path = f.name
        
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE trades (id INTEGER PRIMARY KEY, pnl REAL)")
            conn.commit()
            conn.close()
            
            res = probability_calibration.load_calibration_from_trades(db_path)
            self.assertEqual(res['n_samples'], 0)
            self.assertEqual(res['brier_score'], 0.25)
            self.assertEqual(res['kelly_cap'], 0.05)
            
            # Now let's add some data manually via connection
            conn = sqlite3.connect(db_path)
            # The function load_calibration_from_trades adds the predicted_win_probability column automatically
            conn.execute("INSERT INTO trades (pnl, predicted_win_probability) VALUES (10.0, 0.9)")
            conn.commit()
            conn.close()
            
            res = probability_calibration.load_calibration_from_trades(db_path)
            self.assertEqual(res['n_samples'], 1)
            # n_samples < 30 means brier score will return 0.25 and kelly cap will return 0.05
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

if __name__ == '__main__':
    unittest.main()
