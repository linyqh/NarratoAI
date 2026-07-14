# NarratoAI headless core Makefile

.PHONY: help sync check test build

# 默认目标
.DEFAULT_GOAL := help

# 变量定义
# 颜色定义
GREEN := \033[32m
YELLOW := \033[33m
BLUE := \033[34m
RESET := \033[0m

help: ## 显示帮助信息
	@echo "$(GREEN)NarratoAI Core 管理命令$(RESET)"
	@echo ""
	@echo "$(YELLOW)可用命令:$(RESET)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  $(BLUE)%-15s$(RESET) %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync: ## 同步 Python 依赖
	uv sync

check: ## 验证核心包和 LLM provider 注册
	uv run python -m app

test: ## 运行测试
	uv run pytest -q

build: ## 构建 Docker 镜像
	@echo "$(GREEN)构建 headless core 镜像...$(RESET)"
	docker build -t narratoai-core .
