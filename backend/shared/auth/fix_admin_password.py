"""Fix admin password in MySQL"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from password_utils import hash_password
from sqlalchemy import create_engine, text

# MySQL configuration
db_url = 'mysql+pymysql://app:app@localhost/account?charset=utf8mb4'
engine = create_engine(db_url)

# Generate correct password hash
password = 'admin123'
hashed = hash_password(password)
print(f"Generated hash: {hashed}")

# Update the admin user
with engine.connect() as conn:
    result = conn.execute(text(
        "UPDATE users SET hashed_password = :hash WHERE username = 'admin'"
    ), {"hash": hashed})
    conn.commit()
    print(f"Updated {result.rowcount} row(s)")

# Verify
with engine.connect() as conn:
    result = conn.execute(text("SELECT username, hashed_password FROM users WHERE username = 'admin'"))
    row = result.fetchone()
    print(f"Verified: {row[0]} -> {row[1][:20]}...")
