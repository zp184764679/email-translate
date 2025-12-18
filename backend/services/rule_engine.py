"""
邮件规则引擎 - 自动分类规则处理

支持的条件字段：
- from_email: 发件人邮箱
- from_name: 发件人名称
- to_email: 收件人
- subject: 主题
- body: 正文
- has_attachment: 是否有附件
- language: 语言

支持的操作符：
- contains: 包含
- equals: 等于
- starts_with: 开头匹配
- ends_with: 结尾匹配
- regex: 正则表达式

支持的动作：
- move_to_folder: 移动到文件夹
- add_label: 添加标签
- remove_label: 移除标签
- mark_read: 标记已读
- mark_unread: 标记未读
- mark_flagged: 添加星标
- mark_unflagged: 移除星标
- skip_translate: 跳过翻译
"""

import re
import signal
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update


# 正则匹配超时设置（秒）
REGEX_TIMEOUT = 0.5  # 500ms


def regex_match_with_timeout(pattern: str, text: str, timeout: float = REGEX_TIMEOUT) -> bool:
    """
    带超时保护的正则匹配

    Args:
        pattern: 正则表达式模式
        text: 待匹配文本
        timeout: 超时时间（秒）

    Returns:
        是否匹配成功（超时返回 False）
    """
    result = [False]
    exception = [None]

    def do_match():
        try:
            result[0] = bool(re.search(pattern, text, re.IGNORECASE))
        except Exception as e:
            exception[0] = e

    thread = threading.Thread(target=do_match)
    thread.daemon = True
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        print(f"[RuleEngine] Regex timeout ({timeout}s): pattern={pattern[:50]}...")
        return False

    if exception[0]:
        print(f"[RuleEngine] Regex error: {exception[0]}")
        return False

    return result[0]


class RuleEngine:
    """邮件规则引擎"""

    def __init__(self, db: AsyncSession, account_id: int):
        self.db = db
        self.account_id = account_id
        self.rules = []

    async def load_rules(self):
        """加载账户的所有启用规则（按优先级排序）"""
        from database.models import EmailRule

        result = await self.db.execute(
            select(EmailRule)
            .where(EmailRule.account_id == self.account_id, EmailRule.is_active == True)
            .order_by(EmailRule.priority.asc())
        )
        self.rules = result.scalars().all()
        print(f"[RuleEngine] Loaded {len(self.rules)} active rules for account {self.account_id}")

    def evaluate_conditions(self, email: dict, conditions: dict) -> bool:
        """
        评估邮件是否满足条件

        条件格式：
        {
            "logic": "AND",  # AND 或 OR
            "rules": [
                {"field": "from_email", "operator": "contains", "value": "@supplier.com"},
                {"field": "subject", "operator": "contains", "value": "报价"}
            ]
        }
        """
        logic = conditions.get("logic", "AND").upper()
        rules = conditions.get("rules", [])

        if not rules:
            return False

        results = []
        for rule in rules:
            field = rule.get("field", "")
            operator = rule.get("operator", "contains")
            value = rule.get("value", "")

            # 获取邮件字段值
            email_value = self._get_email_field(email, field)

            # 执行条件匹配
            match = self._match_condition(email_value, operator, value, field)
            results.append(match)

        if logic == "AND":
            return all(results)
        else:  # OR
            return any(results)

    def _get_email_field(self, email: dict, field: str) -> Any:
        """获取邮件的指定字段值"""
        # 处理特殊字段
        if field == "has_attachment":
            attachments = email.get("attachments", [])
            return len(attachments) > 0 if isinstance(attachments, list) else False
        elif field == "language":
            return email.get("language_detected", "")
        elif field == "subject":
            return email.get("subject_original", "")
        elif field == "body":
            return email.get("body_original", "")

        # 普通字段直接获取
        value = email.get(field, "")
        return value if value is not None else ""

    def _match_condition(self, email_value: Any, operator: str, value: str, field: str) -> bool:
        """执行单个条件匹配"""
        # 处理布尔字段
        if field == "has_attachment":
            if operator == "equals":
                target = value.lower() in ("true", "1", "yes")
                return email_value == target
            return False

        # 字符串匹配
        if email_value is None:
            email_value = ""
        email_value_str = str(email_value).lower()
        value_lower = str(value).lower()

        if operator == "contains":
            return value_lower in email_value_str
        elif operator == "equals":
            return email_value_str == value_lower
        elif operator == "starts_with":
            return email_value_str.startswith(value_lower)
        elif operator == "ends_with":
            return email_value_str.endswith(value_lower)
        elif operator == "regex":
            # 使用超时保护的正则匹配，防止 ReDoS 攻击
            return regex_match_with_timeout(value, str(email_value))
        elif operator == "not_contains":
            return value_lower not in email_value_str
        elif operator == "not_equals":
            return email_value_str != value_lower

        return False

    async def apply_actions(self, email_id: int, actions: list, use_savepoint: bool = True) -> Dict[str, Any]:
        """
        对邮件执行动作（带事务保护）

        动作格式：
        [
            {"type": "move_to_folder", "folder_id": 5},
            {"type": "add_label", "label_id": 3},
            {"type": "mark_read"},
            {"type": "mark_flagged"}
        ]

        Args:
            email_id: 邮件ID
            actions: 动作列表
            use_savepoint: 是否使用保存点（用于回滚部分失败）
        """
        from database.models import Email, email_folder_mappings, email_label_mappings

        result = {
            "success": True,
            "actions_applied": [],
            "skip_translate": False,
            "error_message": None
        }

        # 使用 savepoint 实现原子性操作
        # 如果任何动作失败，可以回滚到 savepoint
        savepoint = None
        if use_savepoint:
            try:
                savepoint = await self.db.begin_nested()
            except Exception:
                # 某些情况下无法创建 nested transaction，继续执行
                savepoint = None

        try:
            for action in actions:
                action_type = action.get("type", "")

                if action_type == "move_to_folder":
                    folder_id = action.get("folder_id")
                    if folder_id:
                        await self._move_to_folder(email_id, folder_id)
                        result["actions_applied"].append(f"move_to_folder:{folder_id}")

                elif action_type == "add_label":
                    label_id = action.get("label_id")
                    if label_id:
                        await self._add_label(email_id, label_id)
                        result["actions_applied"].append(f"add_label:{label_id}")

                elif action_type == "remove_label":
                    label_id = action.get("label_id")
                    if label_id:
                        await self._remove_label(email_id, label_id)
                        result["actions_applied"].append(f"remove_label:{label_id}")

                elif action_type == "mark_read":
                    await self._update_email_field(email_id, "is_read", True)
                    result["actions_applied"].append("mark_read")

                elif action_type == "mark_unread":
                    await self._update_email_field(email_id, "is_read", False)
                    result["actions_applied"].append("mark_unread")

                elif action_type == "mark_flagged":
                    await self._update_email_field(email_id, "is_flagged", True)
                    result["actions_applied"].append("mark_flagged")

                elif action_type == "mark_unflagged":
                    await self._update_email_field(email_id, "is_flagged", False)
                    result["actions_applied"].append("mark_unflagged")

                elif action_type == "skip_translate":
                    result["skip_translate"] = True
                    result["actions_applied"].append("skip_translate")

            # 所有动作成功，提交 savepoint
            if savepoint:
                await savepoint.commit()

        except Exception as e:
            error_msg = f"Failed to apply action: {e}"
            print(f"[RuleEngine] {error_msg}")
            result["success"] = False
            result["error_message"] = str(e)

            # 回滚到 savepoint
            if savepoint:
                try:
                    await savepoint.rollback()
                    print(f"[RuleEngine] Rolled back actions for email {email_id}")
                except Exception:
                    pass

        return result

    async def _move_to_folder(self, email_id: int, folder_id: int):
        """移动邮件到文件夹"""
        from database.models import email_folder_mappings
        from sqlalchemy import insert, delete

        # 先删除现有的文件夹关联（如果需要独占）
        # 注意：这里假设邮件可以属于多个文件夹，所以不删除
        # 如果需要独占，取消下面的注释
        # await self.db.execute(
        #     delete(email_folder_mappings).where(
        #         email_folder_mappings.c.email_id == email_id
        #     )
        # )

        # 添加到新文件夹
        try:
            await self.db.execute(
                insert(email_folder_mappings).values(
                    email_id=email_id,
                    folder_id=folder_id
                )
            )
        except Exception:
            # 可能已存在，忽略
            pass

    async def _add_label(self, email_id: int, label_id: int):
        """为邮件添加标签"""
        from database.models import email_label_mappings
        from sqlalchemy import insert

        try:
            await self.db.execute(
                insert(email_label_mappings).values(
                    email_id=email_id,
                    label_id=label_id
                )
            )
        except Exception:
            # 可能已存在，忽略
            pass

    async def _remove_label(self, email_id: int, label_id: int):
        """移除邮件标签"""
        from database.models import email_label_mappings
        from sqlalchemy import delete

        await self.db.execute(
            delete(email_label_mappings).where(
                email_label_mappings.c.email_id == email_id,
                email_label_mappings.c.label_id == label_id
            )
        )

    async def _update_email_field(self, email_id: int, field: str, value: Any):
        """更新邮件字段"""
        from database.models import Email

        await self.db.execute(
            update(Email).where(Email.id == email_id).values(**{field: value})
        )

    async def _update_rule_stats(self, rule_id: int):
        """更新规则匹配统计"""
        from database.models import EmailRule

        await self.db.execute(
            update(EmailRule)
            .where(EmailRule.id == rule_id)
            .values(
                match_count=EmailRule.match_count + 1,
                last_match_at=datetime.utcnow()
            )
        )

    async def _log_execution(
        self,
        rule_id: int,
        email_id: int,
        matched: bool,
        actions_applied: List[str],
        actions_success: bool,
        error_message: str = None,
        matched_conditions: dict = None
    ):
        """记录规则执行日志"""
        from database.models import RuleExecution

        try:
            execution = RuleExecution(
                rule_id=rule_id,
                email_id=email_id,
                account_id=self.account_id,
                matched=matched,
                actions_applied=actions_applied,
                actions_success=actions_success,
                error_message=error_message,
                matched_conditions=matched_conditions
            )
            self.db.add(execution)
            # 不立即 commit，让调用者决定何时 commit
        except Exception as e:
            print(f"[RuleEngine] Failed to log execution: {e}")

    async def process_email(self, email_data: dict, email_id: int, log_executions: bool = True) -> Dict[str, Any]:
        """
        处理单封邮件，返回应用的规则信息

        Args:
            email_data: 邮件数据字典
            email_id: 邮件ID
            log_executions: 是否记录执行日志

        Returns:
            {
                "applied_rules": ["规则1", "规则2"],
                "skip_translate": False,
                "actions_applied": ["move_to_folder:5", "add_label:3"],
                "execution_logs": [...]
            }
        """
        result = {
            "applied_rules": [],
            "skip_translate": False,
            "actions_applied": [],
            "execution_logs": []
        }

        for rule in self.rules:
            try:
                # 评估条件
                matched = self.evaluate_conditions(email_data, rule.conditions)

                if matched:
                    # 执行动作
                    action_result = await self.apply_actions(email_id, rule.actions)

                    # 记录结果
                    result["applied_rules"].append(rule.name)
                    result["actions_applied"].extend(action_result.get("actions_applied", []))

                    if action_result.get("skip_translate"):
                        result["skip_translate"] = True

                    # 更新规则统计
                    await self._update_rule_stats(rule.id)

                    # 记录执行日志
                    if log_executions:
                        await self._log_execution(
                            rule_id=rule.id,
                            email_id=email_id,
                            matched=True,
                            actions_applied=action_result.get("actions_applied", []),
                            actions_success=action_result.get("success", True),
                            error_message=action_result.get("error_message"),
                            matched_conditions={"rule_name": rule.name, "conditions": rule.conditions}
                        )

                    result["execution_logs"].append({
                        "rule_id": rule.id,
                        "rule_name": rule.name,
                        "matched": True,
                        "actions_applied": action_result.get("actions_applied", []),
                        "success": action_result.get("success", True)
                    })

                    print(f"[RuleEngine] Rule '{rule.name}' matched email {email_id}")

                    # 如果设置了停止处理，跳出循环
                    if rule.stop_processing:
                        print(f"[RuleEngine] Stop processing after rule '{rule.name}'")
                        break

            except Exception as e:
                error_msg = str(e)
                print(f"[RuleEngine] Error processing rule '{rule.name}': {error_msg}")

                # 即使失败也记录日志
                if log_executions:
                    await self._log_execution(
                        rule_id=rule.id,
                        email_id=email_id,
                        matched=False,
                        actions_applied=[],
                        actions_success=False,
                        error_message=error_msg
                    )

        return result

    async def test_rules(self, email_data: dict) -> List[Dict[str, Any]]:
        """
        测试规则匹配（不实际执行动作）

        Returns:
            [
                {"rule_id": 1, "rule_name": "规则1", "matched": True, "actions": [...]},
                {"rule_id": 2, "rule_name": "规则2", "matched": False, "actions": []}
            ]
        """
        results = []

        for rule in self.rules:
            matched = self.evaluate_conditions(email_data, rule.conditions)
            results.append({
                "rule_id": rule.id,
                "rule_name": rule.name,
                "matched": matched,
                "actions": rule.actions if matched else [],
                "priority": rule.priority
            })

        return results
