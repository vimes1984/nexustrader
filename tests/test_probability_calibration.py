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
        self.assertEqual(probability_calibration.kelly_cap_from_calibration(0.0, 30), 1.0)

    def test_kelly_cap_insufficient_samples(self):
        self.assertEqual(probability_calibration.kelly_cap_from_calibration(0.0, 29), 0.05)

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
