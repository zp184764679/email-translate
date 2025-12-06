# shared/validators.py
"""
统一数据验证模块
为Flask系统提供类似Pydantic的验证功能
"""
import re
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Union
from functools import wraps
from flask import request, jsonify


class ValidationError(Exception):
    """验证错误"""
    def __init__(self, field: str, message: str, code: str = 'VALIDATION_ERROR'):
        self.field = field
        self.message = message
        self.code = code
        super().__init__(f"{field}: {message}")


class Validator:
    """字段验证器基类"""

    def __init__(self, required: bool = True, default: Any = None, error_message: str = None):
        self.required = required
        self.default = default
        self.error_message = error_message

    def validate(self, value: Any, field_name: str) -> Any:
        """验证并转换值"""
        if value is None or value == '':
            if self.required:
                msg = self.error_message or f'{field_name} 是必填字段'
                raise ValidationError(field_name, msg, 'REQUIRED_FIELD')
            return self.default
        return self._validate(value, field_name)

    def _validate(self, value: Any, field_name: str) -> Any:
        """子类实现具体验证逻辑"""
        return value


class StringValidator(Validator):
    """字符串验证器"""

    def __init__(self, min_length: int = 0, max_length: int = None,
                 pattern: str = None, choices: List[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.min_length = min_length
        self.max_length = max_length
        self.pattern = pattern
        self.choices = choices

    def _validate(self, value: Any, field_name: str) -> str:
        if not isinstance(value, str):
            value = str(value)

        if self.min_length and len(value) < self.min_length:
            raise ValidationError(
                field_name,
                f'长度不能少于 {self.min_length} 个字符',
                'MIN_LENGTH'
            )

        if self.max_length and len(value) > self.max_length:
            raise ValidationError(
                field_name,
                f'长度不能超过 {self.max_length} 个字符',
                'MAX_LENGTH'
            )

        if self.pattern and not re.match(self.pattern, value):
            raise ValidationError(
                field_name,
                self.error_message or '格式不正确',
                'INVALID_FORMAT'
            )

        if self.choices and value not in self.choices:
            raise ValidationError(
                field_name,
                f'值必须是以下之一: {", ".join(self.choices)}',
                'INVALID_CHOICE'
            )

        return value


class IntegerValidator(Validator):
    """整数验证器"""

    def __init__(self, min_value: int = None, max_value: int = None, **kwargs):
        super().__init__(**kwargs)
        self.min_value = min_value
        self.max_value = max_value

    def _validate(self, value: Any, field_name: str) -> int:
        try:
            value = int(value)
        except (ValueError, TypeError):
            raise ValidationError(field_name, '必须是整数', 'INVALID_INTEGER')

        if self.min_value is not None and value < self.min_value:
            raise ValidationError(
                field_name,
                f'值不能小于 {self.min_value}',
                'MIN_VALUE'
            )

        if self.max_value is not None and value > self.max_value:
            raise ValidationError(
                field_name,
                f'值不能大于 {self.max_value}',
                'MAX_VALUE'
            )

        return value


class FloatValidator(Validator):
    """浮点数验证器"""

    def __init__(self, min_value: float = None, max_value: float = None,
                 precision: int = None, **kwargs):
        super().__init__(**kwargs)
        self.min_value = min_value
        self.max_value = max_value
        self.precision = precision

    def _validate(self, value: Any, field_name: str) -> float:
        try:
            value = float(value)
        except (ValueError, TypeError):
            raise ValidationError(field_name, '必须是数字', 'INVALID_FLOAT')

        if self.min_value is not None and value < self.min_value:
            raise ValidationError(
                field_name,
                f'值不能小于 {self.min_value}',
                'MIN_VALUE'
            )

        if self.max_value is not None and value > self.max_value:
            raise ValidationError(
                field_name,
                f'值不能大于 {self.max_value}',
                'MAX_VALUE'
            )

        if self.precision is not None:
            value = round(value, self.precision)

        return value


class BooleanValidator(Validator):
    """布尔值验证器"""

    def _validate(self, value: Any, field_name: str) -> bool:
        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            if value.lower() in ('true', '1', 'yes', 'on'):
                return True
            if value.lower() in ('false', '0', 'no', 'off'):
                return False

        if isinstance(value, int):
            return bool(value)

        raise ValidationError(field_name, '必须是布尔值', 'INVALID_BOOLEAN')


class DateValidator(Validator):
    """日期验证器"""

    def __init__(self, date_format: str = '%Y-%m-%d', **kwargs):
        super().__init__(**kwargs)
        self.date_format = date_format

    def _validate(self, value: Any, field_name: str) -> date:
        if isinstance(value, date):
            return value

        if isinstance(value, datetime):
            return value.date()

        if isinstance(value, str):
            try:
                return datetime.strptime(value, self.date_format).date()
            except ValueError:
                raise ValidationError(
                    field_name,
                    f'日期格式错误，应为 {self.date_format}',
                    'INVALID_DATE_FORMAT'
                )

        raise ValidationError(field_name, '无效的日期类型', 'INVALID_DATE')


class DateTimeValidator(Validator):
    """日期时间验证器"""

    def __init__(self, datetime_format: str = '%Y-%m-%d %H:%M:%S', **kwargs):
        super().__init__(**kwargs)
        self.datetime_format = datetime_format

    def _validate(self, value: Any, field_name: str) -> datetime:
        if isinstance(value, datetime):
            return value

        if isinstance(value, str):
            # 尝试多种格式
            formats = [
                self.datetime_format,
                '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%dT%H:%M:%SZ',
                '%Y-%m-%dT%H:%M:%S.%fZ',
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d'
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue

            raise ValidationError(
                field_name,
                f'日期时间格式错误',
                'INVALID_DATETIME_FORMAT'
            )

        raise ValidationError(field_name, '无效的日期时间类型', 'INVALID_DATETIME')


class EmailValidator(StringValidator):
    """邮箱验证器"""

    def __init__(self, **kwargs):
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        super().__init__(pattern=email_pattern, error_message='邮箱格式不正确', **kwargs)


class PhoneValidator(StringValidator):
    """手机号验证器（中国大陆）"""

    def __init__(self, **kwargs):
        phone_pattern = r'^1[3-9]\d{9}$'
        super().__init__(pattern=phone_pattern, error_message='手机号格式不正确', **kwargs)


class ListValidator(Validator):
    """列表验证器"""

    def __init__(self, item_validator: Validator = None,
                 min_items: int = 0, max_items: int = None, **kwargs):
        super().__init__(**kwargs)
        self.item_validator = item_validator
        self.min_items = min_items
        self.max_items = max_items

    def _validate(self, value: Any, field_name: str) -> list:
        if not isinstance(value, list):
            raise ValidationError(field_name, '必须是列表', 'INVALID_LIST')

        if len(value) < self.min_items:
            raise ValidationError(
                field_name,
                f'列表至少需要 {self.min_items} 个元素',
                'MIN_ITEMS'
            )

        if self.max_items is not None and len(value) > self.max_items:
            raise ValidationError(
                field_name,
                f'列表最多包含 {self.max_items} 个元素',
                'MAX_ITEMS'
            )

        if self.item_validator:
            validated = []
            for i, item in enumerate(value):
                try:
                    validated.append(
                        self.item_validator.validate(item, f'{field_name}[{i}]')
                    )
                except ValidationError as e:
                    raise ValidationError(field_name, f'第 {i+1} 项: {e.message}', e.code)
            return validated

        return value


class Schema:
    """数据验证模式"""

    def __init__(self, **fields):
        """
        Args:
            **fields: 字段名和验证器的映射
        """
        self.fields = fields

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证数据

        Args:
            data: 待验证的数据字典

        Returns:
            验证后的数据字典

        Raises:
            ValidationError: 验证失败
        """
        if not isinstance(data, dict):
            raise ValidationError('data', '数据必须是字典类型', 'INVALID_DATA')

        result = {}
        errors = []

        for field_name, validator in self.fields.items():
            try:
                value = data.get(field_name)
                result[field_name] = validator.validate(value, field_name)
            except ValidationError as e:
                errors.append({
                    'field': e.field,
                    'message': e.message,
                    'code': e.code
                })

        if errors:
            # 返回第一个错误
            first_error = errors[0]
            raise ValidationError(
                first_error['field'],
                first_error['message'],
                first_error['code']
            )

        return result


def validate_request(schema: Schema):
    """
    Flask请求验证装饰器

    Usage:
        @app.route('/api/users', methods=['POST'])
        @validate_request(Schema(
            name=StringValidator(min_length=2, max_length=50),
            email=EmailValidator(),
            age=IntegerValidator(min_value=0, max_value=150, required=False)
        ))
        def create_user(validated_data):
            # validated_data 包含验证后的数据
            pass
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                data = request.get_json()
                if data is None:
                    return jsonify({
                        'success': False,
                        'error': '请求体必须是JSON格式',
                        'code': 'INVALID_JSON'
                    }), 400

                validated_data = schema.validate(data)
                return f(validated_data, *args, **kwargs)

            except ValidationError as e:
                return jsonify({
                    'success': False,
                    'error': e.message,
                    'field': e.field,
                    'code': e.code
                }), 400

        return wrapper
    return decorator


# 便捷别名
String = StringValidator
Integer = IntegerValidator
Float = FloatValidator
Boolean = BooleanValidator
Date = DateValidator
DateTime = DateTimeValidator
Email = EmailValidator
Phone = PhoneValidator
List = ListValidator
