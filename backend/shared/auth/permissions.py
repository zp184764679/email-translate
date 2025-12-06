"""
Permission checking utilities for role-based access control
"""
import json


class Roles:
    """Role constants"""
    USER = 'user'
    ADMIN = 'admin'
    SUPER_ADMIN = 'super_admin'


# Role hierarchy: higher number = higher privilege
ROLE_LEVELS = {
    Roles.USER: 0,
    Roles.ADMIN: 10,
    Roles.SUPER_ADMIN: 20
}


def get_role_level(role):
    """
    Get numeric level for a role
    
    Args:
        role: Role string (user, admin, super_admin)
        
    Returns:
        int: Numeric level of the role
    """
    return ROLE_LEVELS.get(role, -1)


def check_permission(user_role, required_roles):
    """
    Check if user role has required permission
    
    Args:
        user_role: User's role string
        required_roles: Single role string or list of allowed roles
        
    Returns:
        bool: True if user has permission
        
    Examples:
        check_permission('admin', ['admin', 'super_admin'])  # True
        check_permission('user', ['admin'])  # False
    """
    if isinstance(required_roles, str):
        required_roles = [required_roles]
    
    user_level = get_role_level(user_role)
    
    for required_role in required_roles:
        if user_level >= get_role_level(required_role):
            return True
    
    return False


def is_admin(user_role):
    """
    Check if user is admin or higher (admin or super_admin)
    
    Args:
        user_role: User's role string
        
    Returns:
        bool: True if user is admin or super_admin
    """
    return get_role_level(user_role) >= ROLE_LEVELS[Roles.ADMIN]


def is_super_admin(user_role):
    """
    Check if user is super admin
    
    Args:
        user_role: User's role string
        
    Returns:
        bool: True if user is super_admin
    """
    return user_role == Roles.SUPER_ADMIN


def has_system_permission(permissions, system_name):
    """
    Check if user has access to a specific system
    
    Args:
        permissions: JSON string or list of system permissions
        system_name: Name of the system (e.g., 'hr', 'quotation', '采购', 'account')

    Returns:
        bool: True if user has access to the system

    Examples:
        has_system_permission('["hr", "quotation"]', 'hr')  # True
        has_system_permission(['hr', 'quotation'], '采购')  # False
    """
    if not permissions:
        return False
    
    # Parse JSON if string
    if isinstance(permissions, str):
        try:
            permissions = json.loads(permissions)
        except:
            return False
    
    if not isinstance(permissions, list):
        return False
    
    return system_name in permissions


def can_manage_user(manager_role, target_role):
    """
    Check if manager can manage target user based on roles
    
    Rule: Can only manage users with lower or equal role level
    
    Args:
        manager_role: Role of the manager
        target_role: Role of the target user
        
    Returns:
        bool: True if manager can manage target user
        
    Examples:
        can_manage_user('super_admin', 'admin')  # True
        can_manage_user('admin', 'user')  # True
        can_manage_user('admin', 'super_admin')  # False
        can_manage_user('user', 'user')  # False (users cannot manage others)
    """
    manager_level = get_role_level(manager_role)
    target_level = get_role_level(target_role)
    
    # At least need to be admin to manage others
    if manager_level < ROLE_LEVELS[Roles.ADMIN]:
        return False
    
    # Can manage users with lower or equal level
    return manager_level >= target_level


def parse_permissions(permissions_json):
    """
    Safely parse permissions JSON string
    
    Args:
        permissions_json: JSON string of permissions
        
    Returns:
        list: List of system permissions, empty list if invalid
    """
    if not permissions_json:
        return []
    
    try:
        perms = json.loads(permissions_json) if isinstance(permissions_json, str) else permissions_json
        return perms if isinstance(perms, list) else []
    except:
        return []
