# backup_manager.py
import os
import shutil
import sqlite3
import tarfile
import logging
from datetime import datetime, timedelta
import glob

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BackupManager")

BACKUP_DIR = os.path.expanduser("~/.nexustrader/backups")
DB_PATH = os.path.expanduser("~/.nexustrader/nexustrader.db")
CONFIG_PATH = os.path.expanduser("~/nexustrader/config.json")
BLOG_DIR = os.path.expanduser("~/nexustrader/blog")

def create_backup():
    """Creates a compressed backup containing the SQLite database, configuration, and blog logs."""
    try:
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = os.path.join(BACKUP_DIR, f"temp_backup_{timestamp}")
        os.makedirs(temp_dir, exist_ok=True)
        
        # 1. Safely backup SQLite database using VACUUM INTO to avoid table locks or corruption
        temp_db_path = os.path.join(temp_dir, "nexustrader.db")
        if os.path.exists(DB_PATH):
            conn = sqlite3.connect(DB_PATH)
            # Vacuum into a new file handles the online hot backup cleanly
            conn.execute(f"VACUUM INTO '{temp_db_path}'")
            conn.close()
            logger.info("SQLite database backed up cleanly using VACUUM.")
        else:
            logger.warning("Main database file not found. Skipping DB backup.")
            
        # 2. Copy config.json if it exists
        if os.path.exists(CONFIG_PATH):
            shutil.copy(CONFIG_PATH, os.path.join(temp_dir, "config.json"))
            logger.info("Configuration file config.json backed up.")
            
        # 3. Copy blog summaries directory if it exists
        if os.path.exists(BLOG_DIR):
            shutil.copytree(BLOG_DIR, os.path.join(temp_dir, "blog"), dirs_exist_ok=True)
            logger.info("Blog summaries directory backed up.")
            
        # 4. Create compressed tar.gz archive
        archive_name = f"backup_{timestamp}.tar.gz"
        archive_path = os.path.join(BACKUP_DIR, archive_name)
        
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(temp_dir, arcname="")
            
        # Cleanup temporary files
        shutil.rmtree(temp_dir)
        
        logger.info(f"Backup created successfully: {archive_path}")
        
        # Apply pruning/rotation policy to save disk space
        prune_backups()
        
        return archive_path
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        raise e

def prune_backups():
    """Implements a rolling rotation policy keeping the last 7 daily, 4 weekly, and 12 monthly backups."""
    try:
        backup_files = glob.glob(os.path.join(BACKUP_DIR, "backup_*.tar.gz"))
        if not backup_files:
            return
            
        now = datetime.now()
        backups_with_dates = []
        
        for bf in backup_files:
            basename = os.path.basename(bf)
            # Format: backup_YYYYMMDD_HHMMSS.tar.gz
            try:
                date_str = basename.split("_")[1]
                b_date = datetime.strptime(date_str, "%Y%m%d")
                backups_with_dates.append((bf, b_date))
            except Exception:
                # Skip invalid filenames
                continue
                
        # Sort backups from newest to oldest
        backups_with_dates.sort(key=lambda x: x[1], reverse=True)
        
        keep_paths = set()
        
        # Keep 7 daily backups
        for path, date in backups_with_dates:
            if (now - date).days <= 7:
                keep_paths.add(path)
                
        # Keep 4 weekly backups (one per week for last 28 days)
        for w in range(4):
            start_date = now - timedelta(days=(w + 1) * 7)
            end_date = now - timedelta(days=w * 7)
            for path, date in backups_with_dates:
                if start_date < date <= end_date:
                    keep_paths.add(path)
                    break # keep only the latest backup in this week window
                    
        # Keep 12 monthly backups (one per month for last 365 days)
        for m in range(12):
            # approximate month as 30 days
            start_date = now - timedelta(days=(m + 1) * 30)
            end_date = now - timedelta(days=m * 30)
            for path, date in backups_with_dates:
                if start_date < date <= end_date:
                    keep_paths.add(path)
                    break # keep only the latest backup in this month window
                    
        # Delete backups that do not fit the retention policy
        for path, _ in backups_with_dates:
            if path not in keep_paths:
                os.remove(path)
                logger.info(f"Pruned old backup archive: {path}")
                
    except Exception as e:
        logger.error(f"Error during backup pruning: {e}")

def restore_backup(archive_path):
    """Restores the database, config, and blog directories from a backup archive."""
    try:
        if not os.path.exists(archive_path):
            raise FileNotFoundError(f"Backup archive not found at: {archive_path}")
            
        temp_extract_dir = os.path.join(BACKUP_DIR, "temp_restore")
        if os.path.exists(temp_extract_dir):
            shutil.rmtree(temp_extract_dir)
        os.makedirs(temp_extract_dir, exist_ok=True)
        
        # Extract archive
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=temp_extract_dir)
            
        # 1. Restore SQLite database safely
        restored_db = os.path.join(temp_extract_dir, "nexustrader.db")
        if os.path.exists(restored_db):
            # Copy database to destination
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            shutil.copy(restored_db, DB_PATH)
            logger.info("SQLite database restored successfully.")
            
        # 2. Restore config.json
        restored_config = os.path.join(temp_extract_dir, "config.json")
        if os.path.exists(restored_config):
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            shutil.copy(restored_config, CONFIG_PATH)
            logger.info("Configuration file config.json restored.")
            
        # 3. Restore blog summary files
        restored_blog = os.path.join(temp_extract_dir, "blog")
        if os.path.exists(restored_blog):
            shutil.copytree(restored_blog, BLOG_DIR, dirs_exist_ok=True)
            logger.info("Blog summaries directory restored.")
            
        # Cleanup temporary files
        shutil.rmtree(temp_extract_dir)
        logger.info("Restore completed successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to restore backup: {e}")
        raise e

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "backup":
            create_backup()
        elif cmd == "restore" and len(sys.argv) > 2:
            restore_backup(sys.argv[2])
        else:
            print("Usage: python3 backup_manager.py [backup | restore <archive_path>]")
    else:
        create_backup()
