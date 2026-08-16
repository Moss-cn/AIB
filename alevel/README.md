# A-Level 评估工具 (alevel)

基于《AI视频画质等级体系 A1–A10 完整构建方案》v1.0 草案实现的评估工具：
按方案定义的权重公式、等级阈值与一票否决规则，对 AI 生成视频给出 **A1–A10 技术画质等级**。

## 特性

- **纯规则引擎** (`alevel/engine.py` + `alevel/spec.py`)：全部阈值/权重/否决规则集中配置，忠实实现方案 3.2 / 3.3 / 3.4；支持 2–10 与 1–5 两种分制。
- **全自动评估（A–E 五项，无需人工评分）**：
  - A 有效空间分辨率：FFT 高频能量占比 + 降采样恢复保真度
  - B 时间稳定性：时间域高频能量（闪烁）+ 块匹配光流光滑度
  - C 结构完整性：运动补偿结构残余（morphing）+ cv2 可用时 Haar 人脸检出/抖动增强
  - D 物理一致性：主光照方向一致性 + 亮度时间稳定性（弱代理，置信度 low）
  - E 纹理自然度：块效应强度（弱代理，置信度 low）
- **重型探针接口** (`alevel/metrics/adapters.py`)：MediaPipe Hands / PaddleOCR / RAFT / Depth Anything / ArcFace 等方案 4.1 清单工具的插拔式骨架，装好依赖即可接入。
- **混合评估**：自动分 + 可选人工修正（JSON），人工修正优先。
- **报告**：JSON（机器可读）+ Markdown（中文人读）。
- **演示模式**：ffmpeg 生成 6 类已知性质的合成视频，端到端验证指标敏感性。
- **Web 版**：单文件 `index.html`（Pyodide 驱动自动指标，浏览器本地处理视频）。

## 安装

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # 仅 numpy；可选 opencv-python-headless 启用人脸增强
# 系统需有 ffmpeg (macOS: brew install ffmpeg)
```

## 快速开始

```bash
# 1) 演示: 生成合成视频并跑通全流程 (A–E 全自动)
python -m alevel.cli demo --outdir demo

# 2) 全自动评测真实视频 (无需人工评分)
python -m alevel.cli evaluate path/to/video.mp4 --out report.json

# 3) 纯人工评分 (标注/标定流程, 附录 A)
python -m alevel.cli grade --scores '{"A":4,"B":4,"C":5,"D":4,"E":4}'

# 4) 查看重型探针可用性
python -m alevel.cli probes
```

## 评分体系 (方案原文)

- 核心五项 A–E 每项 1–5 分；综合得分 = (A×0.20 + B×0.30 + C×0.20 + D×0.15 + E×0.15) × 2。
- 等级 A1–A10 阈值见 `alevel/spec.py#GRADES`；A8+ 需进阶维度 F/G/H。
- 一票否决：C 严重畸形 → 上限 A2；B 持续大幅闪烁/身份漂移 → 上限 A3。

## 已知方案缺陷（本工具忠实实现，见可行性报告 §2）

1. **等级表核心项要求不单调**：A4 需 C≥3，但 A5 仅需 B≥3（C 要求消失），结构分很低的视频仍可评 A5。建议改为要求累积。
2. **附录 C 与正文公式矛盾**：附录"综合得分 4.1 → A7"与 3.2 公式（应 8.4 → A7）不一致。
3. **"等效分辨率"隐喻**：A8+（等效 5K+）依赖 F/G/H 自动测量，当前属研究级，不宜对外承诺。

## 自动指标标定状态

`spec.CALIBRATION` 中的指标→分数映射为**占位默认值**，必须在真实 AI 视频语料上（人工标注 + 回归拟合）重新标定后才能作为正式判定依据。当前自动分仅供初筛/演示。

## 测试

```bash
python tests/run_all.py    # 17 项单元测试 (引擎 + 指标 + 端到端)
```