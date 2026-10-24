#!/bin/bash
# 编译《软件学报》LaTeX 论文
# 使用方法: bash compile.sh

set -e

echo "=== 编译《软件学报》论文 ==="
echo "文件: jos-sample.tex"
echo ""

# 检查 xelatex
if ! command -v xelatex &> /dev/null; then
    echo "❌ 错误: 未找到 xelatex"
    echo ""
    echo "请先安装 LaTeX:"
    echo "  brew install --cask mactex"
    echo ""
    echo "或使用在线编译器:"
    echo "  https://www.overleaf.com"
    exit 1
fi

echo "✅ 找到 xelatex: $(which xelatex)"
echo ""

# 编译
echo "第一次编译..."
xelatex -interaction=nonstopmode jos-sample.tex

echo "运行 BibTeX..."
bibtex jos-sample

echo "第二次编译..."
xelatex -interaction=nonstopmode jos-sample.tex

echo "第三次编译..."
xelatex -interaction=nonstopmode jos-sample.tex

echo ""
echo "✅ 编译完成!"
echo "PDF 文件: jos-sample.pdf"
echo ""
echo "请检查 PDF 是否正确生成"
