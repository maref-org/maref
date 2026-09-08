# 《软件学报》投稿快速参考

## 关键链接

| 链接 | URL |
|------|-----|
| **期刊官网** | http://www.jos.org.cn |
| **投稿系统** | http://www.jos.org.cn (作者中心) |
| **编辑部邮箱** | jos@iscas.ac.cn |
| **编辑部电话** | 010-62562563 |

## 关键信息

| 项目 | 值 |
|------|-----|
| **ISSN** | 1000-9825 |
| **CN** | 11-2560/TP |
| **主办单位** | 中国科学院软件研究所 + 中国计算机学会 |
| **审稿周期** | 3-6 个月 |
| **录用率** | ~20% |
| **版面费** | 免费 |
| **语言要求** | 必须中文（2009年起不接受英文） |
| **审稿制度** | 单盲审稿制 |

## 论文信息

| 字段 | 内容 |
|------|------|
| **中文标题** | MAREF：面向多Agent系统的递归演化治理框架 |
| **英文标题** | MAREF: A Recursive Evolution Governance Framework for Multi-Agent Systems |
| **中文关键词** | 多Agent系统；Agent治理；形式化验证；国密合规；状态机；安全治理 |
| **英文关键词** | Multi-Agent Systems; Agent Governance; Formal Verification; National Cryptography Compliance; State Machine; Security Governance |

## 重要规定

| 规定 | 说明 |
|------|------|
| **原创性** | 必须是原创性论文，未在任何正式出版物上刊载 |
| **一稿一投** | 不允许一稿多投 |
| **中文文献** | 必须引用国内文献并进行比较 |
| **署名规范** | 署名数量/顺序以初投稿为准，不得修改 |
| **LaTeX 支持** | 投稿时接受 LaTeX（上传 PS 文件），录用后需改用 Word |

## arXiv/Zenodo 发布

**重要**: MAREF 白皮书已在 Zenodo 发布（DOI: 10.5281/zenodo.22432290）

**建议**: 联系编辑部确认是否影响投稿资格

**联系邮件模板**:
```
主题：关于预印本平台发布后投稿的咨询

尊敬的《软件学报》编辑部：

您好！我们计划投稿一篇关于多Agent系统治理框架的论文。该论文的技术白皮书已在 Zenodo 预印本平台发布（DOI: 10.5281/zenodo.22432290）。

请问：
1. 预印本平台发布是否影响投稿资格？
2. 如何在投稿时说明情况？

论文标题：MAREF：面向多Agent系统的递归演化治理框架

谢谢！
```

## 中文文献补充

**《软件学报》明确要求**: 必须引用国内文献并进行比较

**需要补充的中文文献**:
- 国内 Agent 框架研究
- 国密标准（GB/T 32918 系列）
- 等保标准（GB/T 22239-2019）
- AI 安全政策（《智能体规范应用》）
- 国内 Agent 治理相关论文

## 文件清单

| 文件 | 用途 | 状态 |
|------|------|------|
| `jos-sample.tex` | 主文档 | ✅ |
| `jos-body.tex` | 正文 | ✅ |
| `jos-bib.bib` | 参考文献 | ✅ |
| `jos-sample.pdf` | PDF 文件 | ❌ 需编译 |
| `SUBMISSION-GUIDE.md` | 详细投稿指南 | ✅ |
| `QUICK-REFERENCE.md` | 快速参考卡片 | ✅ |

## 投稿步骤

1. 访问 http://www.jos.org.cn
2. 点击 "作者中心"
3. 注册账号
4. 登录系统
5. 新建投稿
6. 填写稿件信息
7. 上传文件
8. 提交

## 编译 PDF

```bash
# 安装 LaTeX（如果未安装）
brew install --cask mactex

# 编译论文
cd papers/jos-template
xelatex jos-sample.tex
bibtex jos-sample
xelatex jos-sample.tex
xelatex jos-sample.tex
```

---

*创建时间: 2026-09-08*
*更新时间: 2026-09-08*
