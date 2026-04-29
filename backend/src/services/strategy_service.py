"""策略服务模块

提供 Prompt 模板管理、策略配置管理、策略调度功能。
支持基于 APScheduler 的策略定时调度。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# 尝试导入核心模块
# ---------------------------------------------------------------------------

try:
    from src.core.agent_engine import AIAgentEngine

    _HAS_AGENT_ENGINE = True
except ImportError:
    _HAS_AGENT_ENGINE = False
    logger.warning("AIAgentEngine 不可用，策略服务将使用桩实现")


# ---------------------------------------------------------------------------
# AI Agent 引擎桩实现
# ---------------------------------------------------------------------------

class _AIAgentEngineStub:
    """AI Agent 引擎桩实现。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}

    async def make_decision(
        self,
        symbol: str,
        account_id: Optional[str] = None,
        model_name: Optional[str] = None,
        template_name: Optional[str] = None,
        extra_variables: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """运行策略，返回模拟结果。"""
        return {
            "strategy": symbol,
            "action": "hold",
            "symbol": symbol,
            "confidence": 0.5,
            "reasoning": "模拟策略执行",
            "timestamp": datetime.now().isoformat(),
        }


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class PromptTemplate:
    """Prompt 模板"""
    name: str
    category: str
    content: str
    variables: List[str] = field(default_factory=list)
    version: int = 1
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class StrategyConfig:
    """策略配置"""
    name: str
    prompt_template: str
    model: str = "gpt-4-turbo"
    provider: str = "openai"
    symbols: List[str] = field(default_factory=list)
    schedule_cron: Optional[str] = None
    schedule_interval: Optional[int] = None  # 秒
    is_enabled: bool = False
    params: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class StrategyJob:
    """策略调度任务"""
    strategy_name: str
    job_id: Optional[str] = None
    is_running: bool = False
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    error_count: int = 0


# ---------------------------------------------------------------------------
# StrategyService
# ---------------------------------------------------------------------------

class StrategyService:
    """策略服务

    提供 Prompt 模板管理、策略配置管理、策略调度功能。

    Usage::

        service = StrategyService()
        await service.initialize()

        # 管理模板
        templates = await service.get_prompt_templates()
        await service.save_prompt_template("my_strategy", "trading", "...")

        # 管理策略
        config = await service.get_strategy_config("momentum")
        await service.update_strategy_config("momentum", {"is_enabled": True})
        await service.start_strategy("momentum")
        await service.stop_strategy("momentum")

        await service.shutdown()
    """

    def __init__(
        self,
        agent_engine: Optional[Any] = None,
        agent_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        初始化策略服务。

        Args:
            agent_engine: AI Agent 引擎实例，为 None 时自动创建。
            agent_config: AI Agent 引擎配置。
        """
        if agent_engine is not None:
            self._agent_engine = agent_engine
        elif _HAS_AGENT_ENGINE:
            self._agent_engine = AIAgentEngine(agent_config or {})
        else:
            self._agent_engine = _AIAgentEngineStub(agent_config or {})

        # 模板存储 (内存 + 数据库)
        self._templates: Dict[str, PromptTemplate] = {}
        # 策略配置存储
        self._strategies: Dict[str, StrategyConfig] = {}
        # 调度任务
        self._jobs: Dict[str, StrategyJob] = {}
        # 调度器
        self._scheduler: Optional[Any] = None
        self._initialized = False

        logger.info("StrategyService 已创建")

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """初始化策略服务，加载数据库中的模板和策略配置。"""
        if self._initialized:
            return

        try:
            # 初始化调度器
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.jobstores.memory import MemoryJobStore

            self._scheduler = AsyncIOScheduler(
                jobstores={"default": MemoryJobStore()},
                job_defaults={
                    "coalesce": True,
                    "max_instances": 1,
                    "misfire_grace_time": 60,
                },
            )
            self._scheduler.start()
            logger.info("APScheduler 调度器已启动")

            # 从数据库加载模板
            await self._load_templates_from_db()

            # 从数据库加载策略配置
            await self._load_strategies_from_db()

            self._initialized = True
            logger.info(
                f"StrategyService 初始化完成, "
                f"模板数={len(self._templates)}, 策略数={len(self._strategies)}"
            )

        except ImportError:
            logger.warning("APScheduler 未安装，策略调度功能不可用")
            self._initialized = True
        except Exception as e:
            logger.error(f"StrategyService 初始化失败: {e}")
            self._initialized = True

    async def shutdown(self) -> None:
        """关闭策略服务，停止所有调度任务。"""
        # 停止所有运行中的策略
        for strategy_name in list(self._jobs.keys()):
            try:
                await self.stop_strategy(strategy_name)
            except Exception as e:
                logger.error(f"停止策略失败: {strategy_name}, 错误: {e}")

        # 关闭调度器
        if self._scheduler:
            try:
                self._scheduler.shutdown(wait=False)
                logger.info("调度器已关闭")
            except Exception as e:
                logger.error(f"关闭调度器异常: {e}")

        self._initialized = False
        logger.info("StrategyService 已关闭")

    # ------------------------------------------------------------------
    # Prompt 模板管理
    # ------------------------------------------------------------------

    async def get_prompt_templates(
        self,
        category: Optional[str] = None,
        active_only: bool = True,
    ) -> List[PromptTemplate]:
        """获取 Prompt 模板列表。

        Args:
            category:   按分类筛选。
            active_only: 是否仅返回启用的模板。

        Returns:
            PromptTemplate 列表。
        """
        templates = list(self._templates.values())

        if category:
            templates = [t for t in templates if t.category == category]
        if active_only:
            templates = [t for t in templates if t.is_active]

        # 按分类和名称排序
        templates.sort(key=lambda t: (t.category, t.name))
        return templates

    async def get_prompt_template(self, name: str) -> Optional[PromptTemplate]:
        """获取指定名称的 Prompt 模板。

        Args:
            name: 模板名称。

        Returns:
            PromptTemplate 对象，不存在返回 None。
        """
        return self._templates.get(name)

    async def save_prompt_template(
        self,
        name: str,
        category: str,
        content: str,
        variables: Optional[List[str]] = None,
        is_active: bool = True,
    ) -> PromptTemplate:
        """保存 Prompt 模板。

        如果同名模板已存在则更新，否则创建新模板。

        Args:
            name:      模板名称。
            category:  模板分类。
            content:   模板内容。
            variables: 模板变量列表。
            is_active: 是否启用。

        Returns:
            保存后的 PromptTemplate 对象。
        """
        # 自动提取变量
        if variables is None:
            variables = self._extract_variables(content)

        existing = self._templates.get(name)
        now = datetime.now()

        template = PromptTemplate(
            name=name,
            category=category,
            content=content,
            variables=variables,
            version=(existing.version + 1) if existing else 1,
            is_active=is_active,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )

        self._templates[name] = template

        # 持久化到数据库
        try:
            await self._save_template_to_db(template)
        except Exception as e:
            logger.error(f"模板持久化失败: {name}, 错误: {e}")

        action = "更新" if existing else "创建"
        logger.info(f"Prompt模板已{action}: {name} (v{template.version}, 分类={category})")
        return template

    async def delete_prompt_template(self, name: str) -> bool:
        """删除 Prompt 模板。

        Args:
            name: 模板名称。

        Returns:
            是否删除成功。
        """
        if name not in self._templates:
            logger.warning(f"模板不存在: {name}")
            return False

        del self._templates[name]

        try:
            await self._delete_template_from_db(name)
        except Exception as e:
            logger.error(f"模板删除持久化失败: {name}, 错误: {e}")

        logger.info(f"Prompt模板已删除: {name}")
        return True

    def render_prompt(
        self,
        template_name: str,
        variables: Dict[str, Any],
    ) -> str:
        """渲染 Prompt 模板。

        Args:
            template_name: 模板名称。
            variables:     变量字典。

        Returns:
            渲染后的 Prompt 字符串。

        Raises:
            ValueError: 模板不存在或缺少必要变量。
        """
        template = self._templates.get(template_name)
        if template is None:
            raise ValueError(f"模板不存在: {template_name}")

        content = template.content
        for var_name, var_value in variables.items():
            placeholder = f"{{{{{var_name}}}}}"
            content = content.replace(placeholder, str(var_value))

        return content

    @staticmethod
    def _extract_variables(content: str) -> List[str]:
        """从模板内容中提取变量名。"""
        pattern = r"\{\{(\w+)\}\}"
        matches = re.findall(pattern, content)
        return list(dict.fromkeys(matches))  # 去重并保持顺序

    # ------------------------------------------------------------------
    # 策略配置管理
    # ------------------------------------------------------------------

    async def get_strategy_config(self, name: str) -> Optional[StrategyConfig]:
        """获取策略配置。

        Args:
            name: 策略名称。

        Returns:
            StrategyConfig 对象，不存在返回 None。
        """
        return self._strategies.get(name)

    async def get_all_strategies(self) -> List[StrategyConfig]:
        """获取所有策略配置。

        Returns:
            StrategyConfig 列表。
        """
        return list(self._strategies.values())

    async def update_strategy_config(
        self,
        name: str,
        updates: Dict[str, Any],
    ) -> Optional[StrategyConfig]:
        """更新策略配置。

        Args:
            name:    策略名称。
            updates: 要更新的字段字典。

        Returns:
            更新后的 StrategyConfig 对象，不存在返回 None。
        """
        config = self._strategies.get(name)
        if config is None:
            logger.warning(f"策略不存在: {name}")
            return None

        now = datetime.now()
        for key, value in updates.items():
            if hasattr(config, key):
                setattr(config, key, value)
        config.updated_at = now

        # 持久化到数据库
        try:
            await self._save_strategy_to_db(config)
        except Exception as e:
            logger.error(f"策略配置持久化失败: {name}, 错误: {e}")

        logger.info(f"策略配置已更新: {name}, 字段: {list(updates.keys())}")
        return config

    async def create_strategy(
        self,
        name: str,
        prompt_template: str,
        model: str = "gpt-4-turbo",
        provider: str = "openai",
        symbols: Optional[List[str]] = None,
        schedule_cron: Optional[str] = None,
        schedule_interval: Optional[int] = None,
        is_enabled: bool = False,
        params: Optional[Dict[str, Any]] = None,
    ) -> StrategyConfig:
        """创建策略配置。

        Args:
            name:              策略名称。
            prompt_template:   使用的 Prompt 模板名称。
            model:             AI 模型名称。
            provider:          模型供应商。
            symbols:           关注的标的列表。
            schedule_cron:     Cron 调度表达式。
            schedule_interval: 间隔调度（秒）。
            is_enabled:        是否启用。
            params:            其他参数。

        Returns:
            新创建的 StrategyConfig 对象。
        """
        if name in self._strategies:
            raise ValueError(f"策略已存在: {name}")

        now = datetime.now()
        config = StrategyConfig(
            name=name,
            prompt_template=prompt_template,
            model=model,
            provider=provider,
            symbols=symbols or [],
            schedule_cron=schedule_cron,
            schedule_interval=schedule_interval,
            is_enabled=is_enabled,
            params=params or {},
            created_at=now,
            updated_at=now,
        )

        self._strategies[name] = config

        # 持久化
        try:
            await self._save_strategy_to_db(config)
        except Exception as e:
            logger.error(f"策略持久化失败: {name}, 错误: {e}")

        logger.info(f"策略已创建: {name}")
        return config

    async def delete_strategy(self, name: str) -> bool:
        """删除策略配置。

        Args:
            name: 策略名称。

        Returns:
            是否删除成功。
        """
        if name not in self._strategies:
            return False

        # 先停止策略
        if name in self._jobs:
            await self.stop_strategy(name)

        del self._strategies[name]

        try:
            await self._delete_strategy_from_db(name)
        except Exception as e:
            logger.error(f"策略删除持久化失败: {name}, 错误: {e}")

        logger.info(f"策略已删除: {name}")
        return True

    # ------------------------------------------------------------------
    # 策略调度
    # ------------------------------------------------------------------

    async def start_strategy(self, name: str) -> bool:
        """启动策略调度。

        Args:
            name: 策略名称。

        Returns:
            是否启动成功。
        """
        config = self._strategies.get(name)
        if config is None:
            logger.warning(f"策略不存在: {name}")
            return False

        if name in self._jobs:
            logger.warning(f"策略已在运行中: {name}")
            return True

        if self._scheduler is None:
            logger.error("调度器未初始化，无法启动策略")
            return False

        job = StrategyJob(strategy_name=name)

        try:
            # 创建调度任务
            if config.schedule_cron:
                job.job_id = self._scheduler.add_job(
                    self._execute_strategy,
                    trigger="cron",
                    **self._parse_cron(config.schedule_cron),
                    args=[name],
                    id=f"strategy_{name}",
                    replace_existing=True,
                ).id
            elif config.schedule_interval:
                job.job_id = self._scheduler.add_job(
                    self._execute_strategy,
                    trigger="interval",
                    seconds=config.schedule_interval,
                    args=[name],
                    id=f"strategy_{name}",
                    replace_existing=True,
                ).id
            else:
                # 无调度配置，立即执行一次
                self._scheduler.add_job(
                    self._execute_strategy,
                    args=[name],
                    id=f"strategy_{name}_once",
                )

            self._jobs[name] = job
            config.is_enabled = True

            logger.info(f"策略已启动: {name} (调度: {config.schedule_cron or f'间隔{config.schedule_interval}s' or '单次'})")
            return True

        except Exception as e:
            logger.error(f"启动策略失败: {name}, 错误: {e}")
            return False

    async def stop_strategy(self, name: str) -> bool:
        """停止策略调度。

        Args:
            name: 策略名称。

        Returns:
            是否停止成功。
        """
        job = self._jobs.get(name)
        if job is None:
            logger.warning(f"策略未在运行: {name}")
            return False

        try:
            if self._scheduler and job.job_id:
                try:
                    self._scheduler.remove_job(job.job_id)
                except Exception:
                    pass

            del self._jobs[name]

            config = self._strategies.get(name)
            if config:
                config.is_enabled = False

            logger.info(f"策略已停止: {name}")
            return True

        except Exception as e:
            logger.error(f"停止策略失败: {name}, 错误: {e}")
            return False

    async def run_strategy_once(self, name: str) -> Dict[str, Any]:
        """手动执行一次策略。

        Args:
            name: 策略名称。

        Returns:
            策略执行结果。
        """
        return await self._execute_strategy(name)

    def get_running_strategies(self) -> List[StrategyJob]:
        """获取所有运行中的策略任务。

        Returns:
            StrategyJob 列表。
        """
        return list(self._jobs.values())

    # ------------------------------------------------------------------
    # 策略执行
    # ------------------------------------------------------------------

    async def _execute_strategy(self, strategy_name: str) -> Dict[str, Any]:
        """执行策略。

        Args:
            strategy_name: 策略名称。

        Returns:
            执行结果字典。
        """
        config = self._strategies.get(strategy_name)
        if config is None:
            logger.error(f"执行策略失败: 策略不存在 {strategy_name}")
            return {"error": f"策略不存在: {strategy_name}"}

        job = self._jobs.get(strategy_name)
        if job:
            job.is_running = True

        start_time = datetime.now()
        logger.info(f"开始执行策略: {strategy_name}")

        try:
            # 获取 Prompt 模板
            template = self._templates.get(config.prompt_template)
            if template is None:
                logger.error(f"Prompt模板不存在: {config.prompt_template}")
                return {"error": f"模板不存在: {config.prompt_template}"}

            # 渲染 Prompt
            prompt = template.content
            context = {
                "symbols": ", ".join(config.symbols) if config.symbols else "全部",
                "current_time": start_time.isoformat(),
                **config.params,
            }

            # 调用 AI Agent 引擎
            result = await self._agent_engine.make_decision(
                symbol=strategy_name,
                extra_variables=context,
            )

            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"策略执行完成: {strategy_name}, "
                f"耗时={elapsed:.2f}s, 结果={result}"
            )

            # 更新任务状态
            if job:
                job.is_running = False
                job.last_run = start_time
                job.run_count += 1

            return {
                "strategy": strategy_name,
                "status": "success",
                "result": result,
                "elapsed_seconds": elapsed,
                "executed_at": start_time.isoformat(),
            }

        except Exception as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.error(f"策略执行异常: {strategy_name}, 错误: {e}, 耗时={elapsed:.2f}s")

            if job:
                job.is_running = False
                job.error_count += 1

            return {
                "strategy": strategy_name,
                "status": "error",
                "error": str(e),
                "elapsed_seconds": elapsed,
                "executed_at": start_time.isoformat(),
            }

    # ------------------------------------------------------------------
    # 数据库持久化
    # ------------------------------------------------------------------

    async def _load_templates_from_db(self) -> None:
        """从数据库加载 Prompt 模板。"""
        try:
            from src.database.connection import get_async_session
            from sqlalchemy import select
            from src.database.schema import PromptTemplateORM

            async with get_async_session() as session:
                stmt = select(PromptTemplateORM).where(
                    PromptTemplateORM.is_active == True  # noqa: E712
                )
                result = await session.execute(stmt)
                orms = result.scalars().all()

                for orm in orms:
                    variables = []
                    if orm.variables:
                        try:
                            variables = json.loads(orm.variables)
                        except (json.JSONDecodeError, TypeError):
                            variables = []

                    template = PromptTemplate(
                        name=orm.name,
                        category=orm.category,
                        content=orm.content,
                        variables=variables,
                        version=orm.version,
                        is_active=orm.is_active,
                        created_at=orm.created_at,
                        updated_at=orm.updated_at,
                    )
                    self._templates[orm.name] = template

                logger.debug(f"从数据库加载了 {len(orms)} 个 Prompt 模板")

        except Exception as e:
            logger.warning(f"从数据库加载模板失败: {e}")

    async def _save_template_to_db(self, template: PromptTemplate) -> None:
        """保存 Prompt 模板到数据库。"""
        from src.database.connection import get_async_session
        from sqlalchemy import select
        from src.database.schema import PromptTemplateORM

        async with get_async_session() as session:
            existing = await session.execute(
                select(PromptTemplateORM).where(PromptTemplateORM.name == template.name)
            )
            orm = existing.scalar_one_or_none()

            variables_json = json.dumps(template.variables) if template.variables else None

            if orm:
                orm.category = template.category
                orm.content = template.content
                orm.variables = variables_json
                orm.version = template.version
                orm.is_active = template.is_active
            else:
                orm = PromptTemplateORM(
                    name=template.name,
                    category=template.category,
                    content=template.content,
                    variables=variables_json,
                    version=template.version,
                    is_active=template.is_active,
                )
                session.add(orm)

            await session.flush()

    async def _delete_template_from_db(self, name: str) -> None:
        """从数据库删除 Prompt 模板。"""
        from src.database.connection import get_async_session
        from sqlalchemy import select
        from src.database.schema import PromptTemplateORM

        async with get_async_session() as session:
            result = await session.execute(
                select(PromptTemplateORM).where(PromptTemplateORM.name == name)
            )
            orm = result.scalar_one_or_none()
            if orm:
                await session.delete(orm)
                await session.flush()

    async def _load_strategies_from_db(self) -> None:
        """从数据库加载策略配置。"""
        try:
            from src.database.connection import get_async_session
            from sqlalchemy import select
            from src.database.schema import SystemConfigORM

            async with get_async_session() as session:
                # 策略配置存储在 system_config 表中，key 以 "strategy_" 开头
                stmt = select(SystemConfigORM).where(
                    SystemConfigORM.key.like("strategy_%")
                )
                result = await session.execute(stmt)
                orms = result.scalars().all()

                for orm in orms:
                    try:
                        data = json.loads(orm.value)
                        config = StrategyConfig(
                            name=data.get("name", orm.key.replace("strategy_", "")),
                            prompt_template=data.get("prompt_template", ""),
                            model=data.get("model", "gpt-4-turbo"),
                            provider=data.get("provider", "openai"),
                            symbols=data.get("symbols", []),
                            schedule_cron=data.get("schedule_cron"),
                            schedule_interval=data.get("schedule_interval"),
                            is_enabled=data.get("is_enabled", False),
                            params=data.get("params", {}),
                            created_at=orm.created_at,
                            updated_at=orm.updated_at,
                        )
                        self._strategies[config.name] = config
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"解析策略配置失败: {orm.key}, 错误: {e}")

                logger.debug(f"从数据库加载了 {len(orms)} 个策略配置")

        except Exception as e:
            logger.warning(f"从数据库加载策略配置失败: {e}")

    async def _save_strategy_to_db(self, config: StrategyConfig) -> None:
        """保存策略配置到数据库。"""
        from src.database.connection import get_async_session
        from sqlalchemy import select
        from src.database.schema import SystemConfigORM

        key = f"strategy_{config.name}"
        value = json.dumps({
            "name": config.name,
            "prompt_template": config.prompt_template,
            "model": config.model,
            "provider": config.provider,
            "symbols": config.symbols,
            "schedule_cron": config.schedule_cron,
            "schedule_interval": config.schedule_interval,
            "is_enabled": config.is_enabled,
            "params": config.params,
        }, ensure_ascii=False)

        async with get_async_session() as session:
            existing = await session.execute(
                select(SystemConfigORM).where(SystemConfigORM.key == key)
            )
            orm = existing.scalar_one_or_none()

            if orm:
                orm.value = value
            else:
                orm = SystemConfigORM(key=key, value=value)
                session.add(orm)

            await session.flush()

    async def _delete_strategy_from_db(self, name: str) -> None:
        """从数据库删除策略配置。"""
        from src.database.connection import get_async_session
        from sqlalchemy import select
        from src.database.schema import SystemConfigORM

        key = f"strategy_{name}"
        async with get_async_session() as session:
            result = await session.execute(
                select(SystemConfigORM).where(SystemConfigORM.key == key)
            )
            orm = result.scalar_one_or_none()
            if orm:
                await session.delete(orm)
                await session.flush()

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_cron(cron_expr: str) -> Dict[str, Any]:
        """解析简单的 Cron 表达式为 APScheduler 参数。

        支持格式:
        - "0 9 * * 1-5" (标准 5 字段)
        - "*/5 * * * *" (每 5 分钟)

        Args:
            cron_expr: Cron 表达式字符串。

        Returns:
            APScheduler cron 触发器参数字典。
        """
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"无效的 Cron 表达式（需要 5 个字段）: {cron_expr}")

        return {
            "minute": parts[0],
            "hour": parts[1],
            "day": parts[2],
            "month": parts[3],
            "day_of_week": parts[4],
        }
