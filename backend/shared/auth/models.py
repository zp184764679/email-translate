"""
Shared user model for authentication
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
import json

Base = declarative_base()

class User(Base):
    """User model for authentication"""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100))
    emp_no = Column(String(50))  # Employee number

    # User type: 'employee' or 'supplier'
    user_type = Column(String(20), default='employee', nullable=False)

    # Role levels (for employees): user, supervisor, admin, super_admin
    # For suppliers, this field is not used
    role = Column(String(20), default='user')

    # System permissions: JSON array of accessible systems ['hr', 'quotation', '采购', 'account']
    # For suppliers, only ['采购'] is meaningful
    permissions = Column(String)

    # Supplier-specific field: reference to supplier ID in caigou system
    supplier_id = Column(Integer, nullable=True)

    # Organization structure fields (reference to HR system)
    department_id = Column(Integer, nullable=True)  # 部门ID
    department_name = Column(String(100), nullable=True)  # 部门名称（冗余存储便于查询）
    position_id = Column(Integer, nullable=True)  # 岗位ID
    position_name = Column(String(100), nullable=True)  # 岗位名称
    team_id = Column(Integer, nullable=True)  # 团队ID
    team_name = Column(String(100), nullable=True)  # 团队名称

    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)  # Deprecated, kept for backward compatibility
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        """Convert user to dictionary (excluding password)"""
        # Parse permissions JSON
        try:
            perms = json.loads(self.permissions) if self.permissions else []
        except:
            perms = []

        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'emp_no': self.emp_no,
            'user_type': self.user_type,
            'role': self.role,
            'permissions': perms,
            'supplier_id': self.supplier_id,
            'department_id': self.department_id,
            'department_name': self.department_name,
            'position_id': self.position_id,
            'position_name': self.position_name,
            'team_id': self.team_id,
            'team_name': self.team_name,
            'is_active': self.is_active,
            'is_admin': self.is_admin,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def is_supplier(self):
        """Check if user is a supplier"""
        return self.user_type == 'supplier'

    def is_employee(self):
        """Check if user is an employee"""
        return self.user_type == 'employee'

    def has_permission(self, system_name):
        """Check if user has permission to access a system"""
        try:
            perms = json.loads(self.permissions) if self.permissions else []
            return system_name in perms
        except:
            return False

    def get_role_level(self):
        """Get role level (higher number = higher privilege)"""
        ROLE_LEVELS = {
            'user': 0,
            'supervisor': 0.5,
            'admin': 1,
            'super_admin': 2
        }
        return ROLE_LEVELS.get(self.role, 0)


# Database setup - MySQL configuration
AUTH_DB_USER = os.getenv('AUTH_DB_USER', 'app')
AUTH_DB_PASSWORD = os.getenv('AUTH_DB_PASSWORD', 'app')
AUTH_DB_HOST = os.getenv('AUTH_DB_HOST', 'localhost')
AUTH_DB_NAME = os.getenv('AUTH_DB_NAME', 'account')

auth_engine = None
AuthSessionLocal = None


def init_auth_db():
    """Initialize authentication database (MySQL)"""
    global auth_engine, AuthSessionLocal

    # Create MySQL engine
    db_url = f'mysql+pymysql://{AUTH_DB_USER}:{AUTH_DB_PASSWORD}@{AUTH_DB_HOST}/{AUTH_DB_NAME}?charset=utf8mb4'
    auth_engine = create_engine(
        db_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=False
    )

    # Create session
    AuthSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=auth_engine)

    # Create tables if they don't exist
    Base.metadata.create_all(bind=auth_engine)

    # Create default admin user if no users exist
    from .password_utils import hash_password
    session = AuthSessionLocal()
    try:
        user_count = session.query(User).count()
        if user_count == 0:
            admin_user = User(
                username='admin',
                email='admin@jzchardware.cn',
                hashed_password=hash_password('admin123'),
                full_name='系统管理员',
                role='super_admin',
                permissions=json.dumps(['hr', 'quotation', '采购', 'account']),
                is_active=True,
                is_admin=True
            )
            session.add(admin_user)
            session.commit()
            print("Created default admin user: admin / admin123")
    except Exception as e:
        print(f"Auth DB init warning: {e}")
        session.rollback()
    finally:
        session.close()

    return auth_engine


def get_auth_db():
    """Get database session"""
    if AuthSessionLocal is None:
        init_auth_db()
    session = AuthSessionLocal()
    try:
        yield session
    finally:
        session.close()

class RegistrationRequest(Base):
    """Registration request model for user account creation approval"""
    __tablename__ = 'registration_requests'

    id = Column(Integer, primary_key=True, index=True)
    emp_no = Column(String(50), nullable=False, index=True)
    full_name = Column(String(100), nullable=False)
    username = Column(String(50), nullable=False, index=True)  # 用户设置的用户名
    email = Column(String(100), nullable=False, index=True)  # 用户设置的邮箱
    hashed_password = Column(String(255), nullable=False)  # 用户设置的密码(哈希后)
    department = Column(String(100))
    title = Column(String(100))
    factory_name = Column(String(100))
    status = Column(String(20), default='pending')  # pending, approved, rejected
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    reviewed_by = Column(Integer)  # User ID of admin who reviewed
    reviewed_at = Column(DateTime)
    rejection_reason = Column(String(500))
    processed_at = Column(DateTime)  # When request was approved/rejected

    def to_dict(self):
        """Convert request to dictionary"""
        return {
            'id': self.id,
            'emp_no': self.emp_no,
            'full_name': self.full_name,
            'email': self.email,
            'department': self.department,
            'title': self.title,
            'factory_name': self.factory_name,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'reviewed_by': self.reviewed_by,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'rejection_reason': self.rejection_reason
        }
