"""
Migration script to convert is_admin to role field
"""
import sqlite3
import sys

def migrate_users_to_role():
    """Migrate users from is_admin to role field"""
    db_path = '/home/admin/shared/auth/users.db'
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if role column exists
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'role' not in columns:
            print("Adding role column...")
            cursor.execute("ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'user'")
            conn.commit()
        
        # Get all users
        cursor.execute("SELECT id, username, is_admin, role FROM users")
        users = cursor.fetchall()
        
        print(f"Found {len(users)} users to migrate")
        
        # Migrate each user
        migrated_count = 0
        for user_id, username, is_admin, current_role in users:
            # If role is NULL or empty, set based on is_admin
            if not current_role:
                if is_admin:
                    new_role = 'super_admin'  # Existing admins become super_admin
                else:
                    new_role = 'user'
                
                cursor.execute(
                    "UPDATE users SET role = ? WHERE id = ?",
                    (new_role, user_id)
                )
                print(f"  Migrated user '{username}' (id={user_id}): is_admin={is_admin} -> role='{new_role}'")
                migrated_count += 1
            else:
                print(f"  Skipped user '{username}' (id={user_id}): already has role='{current_role}'")
        
        conn.commit()
        print(f"\nMigration complete! Migrated {migrated_count} users.")
        
        # Show final state
        print("\nFinal user roles:")
        cursor.execute("SELECT id, username, is_admin, role FROM users")
        for user_id, username, is_admin, role in cursor.fetchall():
            print(f"  User '{username}' (id={user_id}): is_admin={is_admin}, role='{role}'")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"Error during migration: {e}", file=sys.stderr)
        return False

if __name__ == '__main__':
    success = migrate_users_to_role()
    sys.exit(0 if success else 1)
