#!/bin/bash
# 快速启动脚本

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         LLM-Agent 负面信息选择实验框架                        ║"
echo "║                    快速启动脚本                               ║"
echo "╚════════════════════════════════════════════════════════════════╝"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo ""
echo "📁 项目目录: $PROJECT_DIR"
echo ""

# 1. 检查依赖
echo "【步骤1】检查依赖..."
if ! python3 -c "import pydantic, pandas, matplotlib, seaborn, aiohttp, yaml" 2>/dev/null; then
    echo "⚠️  部分依赖缺失，安装中..."
    pip3 install -q -r requirements.txt
    echo "✓ 依赖安装完成"
else
    echo "✓ 所有依赖已安装"
fi

# 2. 检查 .env 文件
echo ""
echo "【步骤2】检查配置文件..."
if [ -f ".env" ]; then
    echo "✓ .env 文件已存在"
    API_KEY=$(grep "ZHIPU_API_KEY" .env | cut -d'=' -f2)
    if [ -z "$API_KEY" ] || [ "$API_KEY" = "your_key_here" ]; then
        echo "⚠️  API密钥未配置！"
        echo "   请编辑 .env 文件并填入正确的密钥"
    else
        echo "✓ API密钥已配置"
    fi
else
    echo "✗ .env 文件不存在"
    echo "   创建 .env 文件..."
    cp .env.example .env
    echo "⚠️  请编辑 .env 文件并填入API密钥"
fi

# 3. 运行集成测试
echo ""
echo "【步骤3】运行集成测试..."
if python3 test_integration.py > /dev/null 2>&1; then
    echo "✓ 集成测试通过"
else
    echo "✗ 集成测试失败"
    exit 1
fi

# 4. 显示下一步
echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                    快速启动完成！                             ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "下一步："
echo ""
echo "1. 运行 Pilot 试验 (快速验证, ~5分钟):"
echo "   python3 main.py"
echo ""
echo "2. 查看可视化结果:"
echo "   python3 main.py --visualize"
echo ""
echo "3. 查看统计摘要:"
echo "   python3 main.py --stats"
echo ""
echo "4. 查看文档:"
echo "   - QUICKSTART.md       - 快速开始指南"
echo "   - README.md           - 项目文档"
echo "   - DEVELOPMENT_SUMMARY.md - 开发总结"
echo ""
