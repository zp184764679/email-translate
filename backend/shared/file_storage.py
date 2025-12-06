# shared/file_storage.py
# -*- coding: utf-8 -*-
"""
统一文件存储工具

文件存储结构:
    storage/
    ├── 2025-01/           # 按年月组织
    │   ├── caigou/        # 采购系统
    │   │   ├── invoices/  # 发票
    │   │   ├── contracts/ # 合同
    │   │   └── attachments/ # 附件
    │   ├── quotation/     # 报价系统
    │   │   ├── drawings/  # 图纸
    │   │   └── quotes/    # 报价单
    │   ├── hr/            # HR系统
    │   │   ├── contracts/ # 劳动合同
    │   │   └── documents/ # 员工文档
    │   └── exports/       # 导出的报表
    │       ├── excel/
    │       └── pdf/
    └── 2025-02/
        └── ...

使用方法:
    from shared.file_storage import FileStorage

    # 初始化存储（指定基础路径）
    storage = FileStorage(base_path="D:/company_storage")

    # 保存文件
    result = storage.save_file(
        file_bytes=file_content,
        original_filename="invoice.pdf",
        system="caigou",
        file_type="invoices"
    )
    # result = {"path": "D:/company_storage/2025-01/caigou/invoices/abc123.pdf",
    #           "url": "/storage/2025-01/caigou/invoices/abc123.pdf",
    #           "filename": "abc123.pdf"}

    # 保存Base64编码的文件
    result = storage.save_base64_file(
        base64_string="data:application/pdf;base64,...",
        original_filename="drawing.pdf",
        system="quotation",
        file_type="drawings"
    )
"""

import base64
import os
import uuid
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_STORAGE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage")
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'txt', 'zip'}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

# 系统和文件类型定义
SYSTEMS = {
    "caigou": {
        "name": "采购系统",
        "file_types": ["invoices", "contracts", "attachments", "rfq"]
    },
    "quotation": {
        "name": "报价系统",
        "file_types": ["drawings", "quotes", "exports"]
    },
    "hr": {
        "name": "人事系统",
        "file_types": ["contracts", "documents", "resumes", "certificates"]
    },
    "portal": {
        "name": "门户系统",
        "file_types": ["announcements", "documents"]
    },
    "scm": {
        "name": "供应链系统",
        "file_types": ["orders", "shipments", "invoices"]
    },
    "exports": {
        "name": "报表导出",
        "file_types": ["excel", "pdf", "csv"]
    }
}


class FileStorage:
    """统一文件存储管理器"""

    def __init__(self, base_path: str = None, url_prefix: str = "/storage"):
        """
        初始化文件存储管理器

        Args:
            base_path: 文件存储基础路径，默认为项目根目录下的storage文件夹
            url_prefix: URL前缀，用于生成访问URL
        """
        self.base_path = base_path or DEFAULT_STORAGE_PATH
        self.url_prefix = url_prefix
        self._ensure_base_folder()

    def _ensure_base_folder(self):
        """确保基础存储文件夹存在"""
        Path(self.base_path).mkdir(parents=True, exist_ok=True)

    def _get_month_folder(self, dt: datetime = None) -> str:
        """
        获取年月文件夹名
        格式: YYYY-MM

        Args:
            dt: 日期时间对象，默认为当前时间

        Returns:
            年月文件夹名，如 "2025-01"
        """
        if dt is None:
            dt = datetime.now()
        return dt.strftime('%Y-%m')

    def _get_storage_path(self, system: str, file_type: str, month: str = None) -> str:
        """
        获取完整的存储路径

        Args:
            system: 系统标识 (caigou, quotation, hr, etc.)
            file_type: 文件类型 (invoices, drawings, etc.)
            month: 年月，默认为当前月份

        Returns:
            完整的文件夹路径
        """
        if month is None:
            month = self._get_month_folder()

        return os.path.join(self.base_path, month, system, file_type)

    def _ensure_storage_path(self, system: str, file_type: str, month: str = None) -> str:
        """
        确保存储路径存在并返回

        Args:
            system: 系统标识
            file_type: 文件类型
            month: 年月

        Returns:
            创建好的完整路径
        """
        path = self._get_storage_path(system, file_type, month)
        Path(path).mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def allowed_file(filename: str, allowed_extensions: set = None) -> bool:
        """
        检查文件类型是否允许

        Args:
            filename: 文件名
            allowed_extensions: 允许的扩展名集合，默认使用全局配置

        Returns:
            是否允许
        """
        if allowed_extensions is None:
            allowed_extensions = ALLOWED_EXTENSIONS
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

    @staticmethod
    def get_extension(filename: str) -> str:
        """获取文件扩展名"""
        if '.' in filename:
            return filename.rsplit('.', 1)[1].lower()
        return 'bin'

    @staticmethod
    def generate_filename(original_filename: str, include_timestamp: bool = True) -> str:
        """
        生成唯一文件名

        Args:
            original_filename: 原始文件名
            include_timestamp: 是否包含时间戳

        Returns:
            唯一文件名
        """
        ext = FileStorage.get_extension(original_filename)
        unique_id = uuid.uuid4().hex[:12]

        if include_timestamp:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            return f"{timestamp}_{unique_id}.{ext}"

        return f"{unique_id}.{ext}"

    @staticmethod
    def calculate_md5(file_bytes: bytes) -> str:
        """计算文件MD5值"""
        return hashlib.md5(file_bytes).hexdigest()

    def save_file(
        self,
        file_bytes: bytes,
        original_filename: str,
        system: str,
        file_type: str,
        custom_filename: str = None,
        validate_extension: bool = True,
        validate_size: bool = True,
        month: str = None
    ) -> Dict[str, Any]:
        """
        保存文件到存储系统

        Args:
            file_bytes: 文件字节内容
            original_filename: 原始文件名
            system: 系统标识 (caigou, quotation, hr, etc.)
            file_type: 文件类型 (invoices, drawings, etc.)
            custom_filename: 自定义文件名，不提供则自动生成
            validate_extension: 是否验证文件扩展名
            validate_size: 是否验证文件大小
            month: 指定存储月份，默认当前月份

        Returns:
            {
                "success": True/False,
                "path": "完整文件路径",
                "url": "访问URL",
                "filename": "存储的文件名",
                "original_filename": "原始文件名",
                "size": 文件大小(字节),
                "md5": "文件MD5值",
                "error": "错误信息（如果有）"
            }
        """
        try:
            # 验证文件扩展名
            if validate_extension and not self.allowed_file(original_filename):
                return {
                    "success": False,
                    "error": f"不支持的文件类型。允许的类型: {', '.join(ALLOWED_EXTENSIONS)}"
                }

            # 验证文件大小
            file_size = len(file_bytes)
            if validate_size and file_size > MAX_FILE_SIZE:
                return {
                    "success": False,
                    "error": f"文件太大。最大允许: {MAX_FILE_SIZE / 1024 / 1024}MB"
                }

            if file_size == 0:
                return {
                    "success": False,
                    "error": "文件内容为空"
                }

            # 确保存储路径存在
            storage_path = self._ensure_storage_path(system, file_type, month)

            # 生成文件名
            if custom_filename:
                filename = custom_filename
            else:
                filename = self.generate_filename(original_filename)

            # 完整文件路径
            file_path = os.path.join(storage_path, filename)

            # 保存文件
            with open(file_path, 'wb') as f:
                f.write(file_bytes)

            # 生成URL
            month_folder = month or self._get_month_folder()
            file_url = f"{self.url_prefix}/{month_folder}/{system}/{file_type}/{filename}"

            # 计算MD5
            file_md5 = self.calculate_md5(file_bytes)

            logger.info(f"文件已保存: {file_path} ({file_size} bytes)")

            return {
                "success": True,
                "path": file_path,
                "url": file_url,
                "filename": filename,
                "original_filename": original_filename,
                "size": file_size,
                "md5": file_md5
            }

        except Exception as e:
            logger.error(f"文件保存失败: {str(e)}")
            return {
                "success": False,
                "error": f"文件保存失败: {str(e)}"
            }

    def save_base64_file(
        self,
        base64_string: str,
        original_filename: str,
        system: str,
        file_type: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        保存Base64编码的文件

        Args:
            base64_string: Base64编码的文件内容（可带data:前缀）
            original_filename: 原始文件名
            system: 系统标识
            file_type: 文件类型
            **kwargs: 传递给save_file的其他参数

        Returns:
            与save_file相同的返回格式
        """
        try:
            # 移除data:前缀
            if ',' in base64_string:
                base64_string = base64_string.split(',')[1]

            # 解码
            file_bytes = base64.b64decode(base64_string)

            return self.save_file(file_bytes, original_filename, system, file_type, **kwargs)

        except Exception as e:
            logger.error(f"Base64解码失败: {str(e)}")
            return {
                "success": False,
                "error": f"Base64解码失败: {str(e)}"
            }

    def delete_file(self, file_path: str) -> bool:
        """
        删除文件

        Args:
            file_path: 文件路径

        Returns:
            是否删除成功
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"文件已删除: {file_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"文件删除失败: {str(e)}")
            return False

    def get_file(self, url: str) -> Optional[str]:
        """
        根据URL获取文件完整路径

        Args:
            url: 文件URL（如 /storage/2025-01/caigou/invoices/abc.pdf）

        Returns:
            文件完整路径，如果文件不存在返回None
        """
        # 移除URL前缀
        if url.startswith(self.url_prefix):
            relative_path = url[len(self.url_prefix):].lstrip('/')
        else:
            relative_path = url.lstrip('/')

        file_path = os.path.join(self.base_path, relative_path)

        if os.path.exists(file_path):
            return file_path
        return None

    def list_files(
        self,
        system: str = None,
        file_type: str = None,
        month: str = None,
        extension: str = None
    ) -> list:
        """
        列出文件

        Args:
            system: 系统标识（可选）
            file_type: 文件类型（可选）
            month: 年月（可选）
            extension: 文件扩展名过滤（可选）

        Returns:
            文件信息列表
        """
        files = []

        # 构建搜索路径
        if month:
            search_months = [month]
        else:
            # 列出所有月份
            search_months = []
            if os.path.exists(self.base_path):
                for item in os.listdir(self.base_path):
                    if os.path.isdir(os.path.join(self.base_path, item)) and '-' in item:
                        search_months.append(item)

        for m in search_months:
            month_path = os.path.join(self.base_path, m)

            # 系统目录
            if system:
                systems_to_check = [system]
            else:
                systems_to_check = []
                if os.path.exists(month_path):
                    for item in os.listdir(month_path):
                        if os.path.isdir(os.path.join(month_path, item)):
                            systems_to_check.append(item)

            for sys in systems_to_check:
                sys_path = os.path.join(month_path, sys)

                # 文件类型目录
                if file_type:
                    types_to_check = [file_type]
                else:
                    types_to_check = []
                    if os.path.exists(sys_path):
                        for item in os.listdir(sys_path):
                            if os.path.isdir(os.path.join(sys_path, item)):
                                types_to_check.append(item)

                for ft in types_to_check:
                    ft_path = os.path.join(sys_path, ft)

                    if os.path.exists(ft_path):
                        for filename in os.listdir(ft_path):
                            file_path = os.path.join(ft_path, filename)
                            if os.path.isfile(file_path):
                                # 扩展名过滤
                                if extension and not filename.lower().endswith(f'.{extension.lower()}'):
                                    continue

                                stat = os.stat(file_path)
                                files.append({
                                    "filename": filename,
                                    "path": file_path,
                                    "url": f"{self.url_prefix}/{m}/{sys}/{ft}/{filename}",
                                    "size": stat.st_size,
                                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                                    "month": m,
                                    "system": sys,
                                    "file_type": ft
                                })

        # 按修改时间倒序排列
        files.sort(key=lambda x: x["modified"], reverse=True)
        return files

    def get_storage_stats(self) -> Dict[str, Any]:
        """
        获取存储统计信息

        Returns:
            {
                "total_files": 总文件数,
                "total_size": 总大小(字节),
                "by_system": {系统: {files: 数量, size: 大小}},
                "by_month": {月份: {files: 数量, size: 大小}}
            }
        """
        stats = {
            "total_files": 0,
            "total_size": 0,
            "by_system": {},
            "by_month": {}
        }

        files = self.list_files()

        for f in files:
            stats["total_files"] += 1
            stats["total_size"] += f["size"]

            # 按系统统计
            sys = f["system"]
            if sys not in stats["by_system"]:
                stats["by_system"][sys] = {"files": 0, "size": 0}
            stats["by_system"][sys]["files"] += 1
            stats["by_system"][sys]["size"] += f["size"]

            # 按月份统计
            month = f["month"]
            if month not in stats["by_month"]:
                stats["by_month"][month] = {"files": 0, "size": 0}
            stats["by_month"][month]["files"] += 1
            stats["by_month"][month]["size"] += f["size"]

        return stats


# 创建全局实例
file_storage = FileStorage()


# 便捷函数
def save_file(file_bytes: bytes, original_filename: str, system: str, file_type: str, **kwargs) -> Dict[str, Any]:
    """便捷函数：保存文件"""
    return file_storage.save_file(file_bytes, original_filename, system, file_type, **kwargs)


def save_base64_file(base64_string: str, original_filename: str, system: str, file_type: str, **kwargs) -> Dict[str, Any]:
    """便捷函数：保存Base64文件"""
    return file_storage.save_base64_file(base64_string, original_filename, system, file_type, **kwargs)


def delete_file(file_path: str) -> bool:
    """便捷函数：删除文件"""
    return file_storage.delete_file(file_path)


def get_file(url: str) -> Optional[str]:
    """便捷函数：获取文件路径"""
    return file_storage.get_file(url)
