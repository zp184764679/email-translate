"""
Portal Integration Service - Portal 项目管理系统集成服务

提供从邮件系统调用 Portal API 的功能：
1. 查询/匹配项目
2. 创建任务
3. 创建项目（如果需要）
"""
import os
import logging
import requests
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class PortalIntegrationService:
    """Portal 集成服务"""

    def __init__(self):
        # Portal API 地址
        self.portal_api_url = os.getenv('PORTAL_API_URL', 'https://jzchardware.cn/api')
        # 服务令牌（用于服务间认证）
        self.service_token = os.getenv('EMAIL_SERVICE_TOKEN')
        self.timeout = 30
        # 本地请求禁用代理
        self.no_proxy = {'http': None, 'https': None}

    def _get_headers(self, user_token: Optional[str] = None) -> Dict[str, str]:
        """
        构建请求头

        Args:
            user_token: 用户的 Portal token（用于以用户身份操作）
        """
        headers = {
            'Content-Type': 'application/json',
        }
        if user_token:
            headers['Authorization'] = f'Bearer {user_token}'
        elif self.service_token:
            # 使用服务令牌
            headers['X-Email-Service-Token'] = self.service_token
        return headers

    # ==================== 项目匹配 ====================

    def match_projects(
        self,
        order_no: Optional[str] = None,
        customer_name: Optional[str] = None,
        part_number: Optional[str] = None,
        user_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        在 Portal 中搜索匹配的项目

        Args:
            order_no: 订单号/PO 号
            customer_name: 客户名称
            part_number: 品番号/部件号
            user_token: 用户 token

        Returns:
            {
                'success': True,
                'matches': [
                    {'id': 1, 'name': '...', 'score': 100, 'match_field': 'order_no'},
                    ...
                ],
                'best_match': {...} or None
            }
        """
        matches = []

        try:
            # 1. 按订单号精确匹配
            if order_no:
                result = self._search_projects(keyword=order_no, user_token=user_token)
                if result.get('success') and result.get('data', {}).get('items'):
                    for project in result['data']['items']:
                        if project.get('order_no') == order_no:
                            matches.append({
                                **project,
                                'score': 100,
                                'match_field': 'order_no',
                                'match_reason': f"订单号精确匹配: {order_no}"
                            })

            # 2. 按品番号匹配
            if part_number:
                result = self._search_projects(keyword=part_number, user_token=user_token)
                if result.get('success') and result.get('data', {}).get('items'):
                    for project in result['data']['items']:
                        proj_part = project.get('part_number', '')
                        if proj_part and part_number in proj_part:
                            # 检查是否已存在
                            if not any(m['id'] == project['id'] for m in matches):
                                matches.append({
                                    **project,
                                    'score': 80,
                                    'match_field': 'part_number',
                                    'match_reason': f"品番号匹配: {part_number}"
                                })

            # 3. 按客户名称模糊匹配
            if customer_name and len(customer_name) >= 2:
                result = self._search_projects(keyword=customer_name, user_token=user_token)
                if result.get('success') and result.get('data', {}).get('items'):
                    for project in result['data']['items']:
                        proj_customer = project.get('customer_name', '')
                        if proj_customer and customer_name.lower() in proj_customer.lower():
                            # 检查是否已存在
                            if not any(m['id'] == project['id'] for m in matches):
                                matches.append({
                                    **project,
                                    'score': 60,
                                    'match_field': 'customer_name',
                                    'match_reason': f"客户名称匹配: {customer_name}"
                                })

            # 按分数排序
            matches.sort(key=lambda x: x['score'], reverse=True)

            return {
                'success': True,
                'matches': matches,
                'best_match': matches[0] if matches else None,
                'match_count': len(matches)
            }

        except Exception as e:
            logger.error(f"[PortalIntegration] 项目匹配失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'matches': [],
                'best_match': None
            }

    def _search_projects(
        self,
        keyword: str,
        page: int = 1,
        page_size: int = 10,
        user_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        搜索项目

        Args:
            keyword: 搜索关键词
            page: 页码
            page_size: 每页数量
            user_token: 用户 token
        """
        try:
            url = f"{self.portal_api_url}/projects"
            params = {
                'keyword': keyword,
                'page': page,
                'page_size': page_size
            }

            response = requests.get(
                url,
                params=params,
                headers=self._get_headers(user_token),
                timeout=self.timeout,
                proxies=self.no_proxy
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'data': data
                }
            else:
                return {
                    'success': False,
                    'error': f'Portal API 返回错误: {response.status_code}'
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def get_project(self, project_id: int, user_token: Optional[str] = None) -> Dict[str, Any]:
        """
        获取项目详情

        Args:
            project_id: 项目 ID
            user_token: 用户 token
        """
        try:
            url = f"{self.portal_api_url}/projects/{project_id}"

            response = requests.get(
                url,
                headers=self._get_headers(user_token),
                timeout=self.timeout,
                proxies=self.no_proxy
            )

            if response.status_code == 200:
                return {
                    'success': True,
                    'data': response.json()
                }
            elif response.status_code == 404:
                return {
                    'success': False,
                    'error': '项目不存在'
                }
            else:
                return {
                    'success': False,
                    'error': f'Portal API 返回错误: {response.status_code}'
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    # ==================== 项目创建 ====================

    def create_project(
        self,
        name: str,
        description: Optional[str] = None,
        customer_name: Optional[str] = None,
        order_no: Optional[str] = None,
        part_number: Optional[str] = None,
        priority: str = 'normal',
        planned_start_date: Optional[str] = None,
        planned_end_date: Optional[str] = None,
        source_email_id: Optional[int] = None,
        user_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        在 Portal 创建新项目

        Args:
            name: 项目名称
            description: 项目描述
            customer_name: 客户名称
            order_no: 订单号
            part_number: 品番号
            priority: 优先级
            planned_start_date: 计划开始日期
            planned_end_date: 计划结束日期
            source_email_id: 来源邮件 ID
            user_token: 用户 token

        Returns:
            {'success': True, 'project': {...}}
        """
        try:
            url = f"{self.portal_api_url}/projects"

            data = {
                'name': name,
                'description': description,
                'customer_name': customer_name,
                'order_no': order_no,
                'part_number': part_number,
                'priority': priority,
                'source_email_id': source_email_id,
            }

            if planned_start_date:
                data['planned_start_date'] = planned_start_date
            if planned_end_date:
                data['planned_end_date'] = planned_end_date

            response = requests.post(
                url,
                json=data,
                headers=self._get_headers(user_token),
                timeout=self.timeout,
                proxies=self.no_proxy
            )

            if response.status_code in (200, 201):
                return {
                    'success': True,
                    'project': response.json()
                }
            else:
                error_msg = response.text
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error') or error_data.get('message') or str(error_data)
                except (ValueError, KeyError) as json_err:
                    logger.debug(f"Failed to parse error response as JSON: {json_err}")
                return {
                    'success': False,
                    'error': f'创建项目失败: {error_msg}'
                }
        except Exception as e:
            logger.error(f"[PortalIntegration] 创建项目失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    # ==================== 任务创建 ====================

    def create_task(
        self,
        project_id: int,
        title: str,
        description: Optional[str] = None,
        task_type: str = 'general',
        priority: str = 'normal',
        due_date: Optional[str] = None,
        start_date: Optional[str] = None,
        assigned_to_id: Optional[int] = None,
        action_items: Optional[List[str]] = None,
        source_email_id: Optional[int] = None,
        source_email_subject: Optional[str] = None,
        user_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        在 Portal 创建任务

        Args:
            project_id: 项目 ID
            title: 任务标题
            description: 任务描述
            task_type: 任务类型
            priority: 优先级
            due_date: 截止日期
            start_date: 开始日期
            assigned_to_id: 负责人 ID
            action_items: 待办事项列表
            source_email_id: 来源邮件 ID
            source_email_subject: 来源邮件主题
            user_token: 用户 token

        Returns:
            {'success': True, 'task': {...}}
        """
        try:
            url = f"{self.portal_api_url}/projects/{project_id}/tasks"

            data = {
                'title': title,
                'description': description,
                'task_type': task_type,
                'priority': priority,
                'assigned_to_id': assigned_to_id,
                'source_email_id': source_email_id,
                'source_email_subject': source_email_subject,
            }

            if due_date:
                data['due_date'] = due_date
            if start_date:
                data['start_date'] = start_date
            if action_items:
                data['checklist'] = [{'content': item, 'is_done': False} for item in action_items]

            response = requests.post(
                url,
                json=data,
                headers=self._get_headers(user_token),
                timeout=self.timeout,
                proxies=self.no_proxy
            )

            if response.status_code in (200, 201):
                return {
                    'success': True,
                    'task': response.json()
                }
            else:
                error_msg = response.text
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error') or error_data.get('message') or str(error_data)
                except (ValueError, KeyError) as json_err:
                    logger.debug(f"Failed to parse error response as JSON: {json_err}")
                return {
                    'success': False,
                    'error': f'创建任务失败: {error_msg}'
                }
        except Exception as e:
            logger.error(f"[PortalIntegration] 创建任务失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    # ==================== 组合操作 ====================

    def create_task_from_email(
        self,
        email_id: int,
        email_subject: str,
        extraction_data: Dict[str, Any],
        project_id: Optional[int] = None,
        create_project: bool = False,
        project_name: Optional[str] = None,
        user_modifications: Optional[Dict[str, Any]] = None,
        user_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        从邮件创建任务的完整流程

        Args:
            email_id: 邮件 ID
            email_subject: 邮件主题
            extraction_data: AI 提取的数据
            project_id: 关联的项目 ID（如果已匹配）
            create_project: 是否需要创建新项目
            project_name: 新项目名称（create_project=True 时必需）
            user_modifications: 用户修改后的数据
            user_token: 用户 token

        Returns:
            {
                'success': True,
                'project': {...} or None,
                'task': {...},
                'created_project': True/False
            }
        """
        # 合并 AI 提取数据和用户修改
        final_data = {**extraction_data}
        if user_modifications:
            final_data.update(user_modifications)

        created_project = None

        try:
            # 1. 如果需要创建项目
            if create_project:
                if not project_name:
                    project_name = final_data.get('suggested_project_name') or final_data.get('project_name') or f"邮件项目-{email_id}"

                project_result = self.create_project(
                    name=project_name,
                    description=final_data.get('description'),
                    customer_name=final_data.get('customer_name'),
                    order_no=final_data.get('order_no'),
                    part_number=final_data.get('part_number'),
                    priority=final_data.get('priority', 'normal'),
                    planned_start_date=final_data.get('start_date'),
                    planned_end_date=final_data.get('due_date'),
                    source_email_id=email_id,
                    user_token=user_token
                )

                if not project_result.get('success'):
                    return {
                        'success': False,
                        'error': f"创建项目失败: {project_result.get('error')}"
                    }

                created_project = project_result['project']
                project_id = created_project.get('id')

            # 2. 验证项目 ID
            if not project_id:
                return {
                    'success': False,
                    'error': '未指定项目 ID，且未创建新项目'
                }

            # 3. 创建任务
            task_result = self.create_task(
                project_id=project_id,
                title=final_data.get('title') or f"邮件任务: {email_subject[:50]}",
                description=final_data.get('description'),
                task_type=final_data.get('task_type', 'general'),
                priority=final_data.get('priority', 'normal'),
                due_date=final_data.get('due_date'),
                start_date=final_data.get('start_date'),
                assigned_to_id=final_data.get('assigned_to_id'),
                action_items=final_data.get('action_items'),
                source_email_id=email_id,
                source_email_subject=email_subject,
                user_token=user_token
            )

            if not task_result.get('success'):
                return {
                    'success': False,
                    'error': f"创建任务失败: {task_result.get('error')}",
                    'project': created_project,
                    'created_project': create_project
                }

            return {
                'success': True,
                'project': created_project,
                'task': task_result['task'],
                'project_id': project_id,
                'created_project': create_project
            }

        except Exception as e:
            logger.error(f"[PortalIntegration] 从邮件创建任务失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'project': created_project,
                'created_project': create_project if created_project else False
            }

    # ==================== 员工匹配 ====================

    def get_employees(
        self,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        user_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取员工列表（用于任务分配）

        Args:
            search: 搜索关键词（姓名）
            page: 页码
            page_size: 每页数量
            user_token: 用户 token
        """
        try:
            url = f"{self.portal_api_url}/hr/employees"
            params = {
                'page': page,
                'page_size': page_size
            }
            if search:
                params['search'] = search

            response = requests.get(
                url,
                params=params,
                headers=self._get_headers(user_token),
                timeout=self.timeout,
                proxies=self.no_proxy
            )

            if response.status_code == 200:
                return {
                    'success': True,
                    'data': response.json()
                }
            else:
                return {
                    'success': False,
                    'error': f'Portal API 返回错误: {response.status_code}'
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def match_employee(self, name: str, user_token: Optional[str] = None) -> Dict[str, Any]:
        """
        根据姓名匹配员工

        Args:
            name: 员工姓名
            user_token: 用户 token

        Returns:
            {'success': True, 'employee': {...}, 'fuzzy': bool}
        """
        if not name:
            return {'success': False, 'error': '姓名不能为空'}

        try:
            result = self.get_employees(search=name, page_size=5, user_token=user_token)

            if not result.get('success'):
                return result

            items = result.get('data', {}).get('items', [])

            # 精确匹配
            for emp in items:
                emp_name = emp.get('name') or emp.get('full_name') or ''
                if emp_name == name:
                    return {
                        'success': True,
                        'employee': emp,
                        'fuzzy': False
                    }

            # 模糊匹配（返回第一个）
            if items:
                return {
                    'success': True,
                    'employee': items[0],
                    'fuzzy': True
                }

            return {
                'success': False,
                'error': '未找到匹配的员工'
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    # ==================== 健康检查 ====================

    def check_health(self) -> Dict[str, Any]:
        """检查 Portal 系统健康状态"""
        try:
            response = requests.get(
                f"{self.portal_api_url}/health",
                timeout=5,
                proxies=self.no_proxy
            )
            return {
                'status': 'healthy' if response.status_code == 200 else 'unhealthy',
                'url': self.portal_api_url,
                'response_code': response.status_code
            }
        except Exception as e:
            return {
                'status': 'unreachable',
                'url': self.portal_api_url,
                'error': str(e)
            }


# 创建单例实例
portal_integration_service = PortalIntegrationService()
