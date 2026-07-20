# tests/test_backup_manager.py
import unittest
import os
import shutil
import sqlite3
import backup_manager

class TestBackupManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.abspath("test_backup_workspace")
        os.makedirs(self.test_dir, exist_ok=True)
        
        # Override paths in backup_manager
        backup_manager.BACKUP_DIR = os.path.join(self.test_dir, "backups")
        backup_manager.DB_PATH = os.path.join(self.test_dir, "nexustrader.db")
        backup_manager.CONFIG_PATH = os.path.join(self.test_dir, "config.json")
        backup_manager.BLOG_DIR = os.path.join(self.test_dir, "blog")
        
        # Create a real, valid SQLite database
        conn = sqlite3.connect(backup_manager.DB_PATH)
        conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO settings (key, value) VALUES ('test_key', 'test_val')")
        conn.commit()
        conn.close()
        
        with open(backup_manager.CONFIG_PATH, "w") as f:
            f.write("mock-config")
        os.makedirs(backup_manager.BLOG_DIR, exist_ok=True)
        with open(os.path.join(backup_manager.BLOG_DIR, "summary.md"), "w") as f:
            f.write("mock-summary")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_create_backup_success(self):
        archive_path = backup_manager.create_backup()
        self.assertTrue(os.path.exists(archive_path))
        self.assertTrue(archive_path.endswith(".tar.gz"))
        
    def test_restore_backup_success(self):
        archive_path = backup_manager.create_backup()
        
        # Now delete files to verify restore restores them
        os.remove(backup_manager.DB_PATH)
        os.remove(backup_manager.CONFIG_PATH)
        shutil.rmtree(backup_manager.BLOG_DIR)
        
        res = backup_manager.restore_backup(archive_path)
        self.assertTrue(res)
        self.assertTrue(os.path.exists(backup_manager.DB_PATH))
        self.assertTrue(os.path.exists(backup_manager.CONFIG_PATH))
        self.assertTrue(os.path.exists(backup_manager.BLOG_DIR))
        
    def test_prune_backups(self):
        # Generate some mock backups with older dates
        os.makedirs(backup_manager.BACKUP_DIR, exist_ok=True)
        for i in range(15):
            date_str = (backup_manager.datetime.now() - backup_manager.timedelta(days=i)).strftime("%Y%m%d")
            path = os.path.join(backup_manager.BACKUP_DIR, f"backup_{date_str}_120000.tar.gz")
            with open(path, "w") as f:
                f.write("dummy-data")
                
        backup_manager.prune_backups()
        
        # Verify old backups are pruned
        remaining = os.listdir(backup_manager.BACKUP_DIR)
        # Should keep last 7 daily plus weekly ones
        self.assertLess(len(remaining), 15)
