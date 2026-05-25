# Multisim MCP PRD v0.1

## 1. 文档信息

- **产品名**：Multisim MCP
-([ni.com](https://www.ni.com/docs/en-US/bundle/multisim/page/topics/automation-api.html?srsltid=AfmBOoplyEZqgq6y1HuPvH_jQGnEGczgN3O4aguyEMUJ5hqrhkRsB1K6&utm_source=chatgpt.com))ows 本地 MCP Server
- **部署方式**：随用户本机安装，依赖本地已安装的 NI Multisim
- **面向对象**：AI Agent、电子设计工程师、教学实验用户、自动化仿真用户

---

## 2. 产品定义

Multisim MCP 是一个运行在 Windows 本地的 MCP 服务，用于把 NI Multisim 的已有自动化能力封装成可被大模型和 Agent 调用的结构化工具。

它的核心定位不是“AI 代替用户在 GUI 里拖元件画图”，而是：

1. **把已有电路作为可编排对象**，支持打开、检查、修改、仿真、导出。
2. **把 netlist 作为一等输入/输出**，支持从文本电路定义驱动仿真与设计迭代。
3. **把 Multisim 的分析能力工具化**，允许 AI 自动完成参数扫描、器件替换、结果读取与设计改进建议。
4. **把“从需求到拓扑”限制为模板/参数/netlist 生成**，而不是直接控制 GUI 做自由绘图。

---

## 3. 背景与机会

当前大模型在电子电路方向的主要短板不是“不会分析”，而是**无法稳定地操作 EDA 工具**。Multisim 虽具备成熟的仿真能力，但其交互模式主要面向人工操作。与此同时，Multisim 官方 Automation API 已经提供了对以下能力的自动化访问：

- 打开设计文件与 netlist
- 枚举元件、输入、输出、变体、分段
- 运行仿真与分析
- 修改 RLC 值
- 替换兼容器件
- 配置输入数据与输出请求
- 获取仿真结果
- 导出电路图截图、BOM、Netlist

这使得构建一个“AI ↔ Multisim”之间的中间控制层具备现实基础。

---

## 4. 产品目标

### 4.1 V0.1 目标

Multisim MCP v0.1 要实现以下闭环：

1. **加载电路**
   - 打开 `.ms14` 设计文件
   - 打开 `.cir` / `.txt` netlist

2. **理解电路**
   - 枚举当前元件
   - 枚举输入源
   - 枚举输出节点/探针
   - 枚举 sections / variants
   - 生成 netlist / BOM / 电路截图

3. **修改电路**
   - 修改 R / L / C 基础元件数值
   - 通过模板或 netlist 重生成功能实现 source 参数修改
   - 替换兼容元件（同类器件优先）

4. **执行分析**
   - Run / Pause / Resume / Stop 仿真
   - AC Sweep
   - DC 基础仿真与 DC Operating Point 相关流程
   - Transient 分析

5. **读取结果**
   - 请求输出
   - 读取输出数据
   - 读取波形/测量结果
   - 导出 netlist 与图像用于复核

6. **AI 设计迭代**
   - 基于需求生成模板选择 + 参数表
   - 基于需求生成 netlist
   - 基于仿真结果提出设计迭代建议
   - 基于预定义模板自动完成参数优化与器件替换

### 4.2 V0.1 非目标

以下内容明确不纳入 v0.1：

- 从空白画布开始自由放置新元件与导线
- 复杂 GUI 级别拖拽、旋转、布线自动化
- PCB 布局与 Ultiboard 全自动化
- 任意数据库管理与元件库编辑
- 完整模拟人类在 Multisim GUI 中的所有操作
- 云端远程控制他人设备上的 Multisim

---

## 5. 官方能力边界转化为产品边界

### 5.1 可依赖能力

产品只建立在官方自动化边界明确支持的能力上：

- COM Automation API 可控制仿真与分析
- 可打开已有电路或 netlist
- 可枚举元件、输入、输出
- 可通过 `RLCValue` 修改基础 RLC 元件值
- 可通过 `ReplaceComponent` 替换数据库中的兼容器件
- 可通过 `SetInputDataRaw/SetInputDataSampled` 注入输入数据
- 可通过 `SetOutputRequest/GetOutputData` 获取结果
- 可通过 `ReportNetList/ReportBOM/GetCircuitImage` 导出信息

### 5.2 必须规避的边界

产品设计必须显式规避以下超范围行为：

- API 不支持在空白设计中自由放置新元件或导线
- `ReplaceComponent` 不支持直接替换 RLC，RLC 需要用数值属性改
- 替换元件可能导致引脚不匹配，从而丢失网络连接
- 输入输出在替换元件后需要重新枚举
- 输入数据与输出请求在每次仿真前都应重新设置
- 仿真运行时不允许做某些结构修改
- 部分高级电路编辑仅能通过模板或 netlist 侧绕行实现

这直接决定了 v0.1 的设计哲学：

> **首版只做“结构化自动化仿真与迭代”，不做“自由式原理图编辑器代理”。**

---

## 6. 目标用户

### 6.1 电子工程学生 / 教学实验用户
需求：
- 根据题目自动生成基础拓扑建议
- 自动计算元件初值
- 一键运行仿真并读波形
- 导出结果用于报告

### 6.2 模拟电路工程师
需求：
- 快速比较多组器件替换结果
- 自动跑 sweep
- 让 AI 根据指标给出下一轮参数建议

### 6.3 AI Agent / 研究者
需求：
- 把 Multisim 变成可调用工具
- 将自然语言需求转为 netlist / 参数表
- 批量仿真并自动归纳结果

---

## 7. 核心使用场景

### 场景 A：打开已有设计并批量调参
用户输入：
> 打开这个放大器电路，把 R1 从 1k 扫到 10k，观察增益变化。

系统流程：
1. 打开 `.ms14`
2. 枚举元件与输出
3. 修改 R1 数值
4. 运行 AC Sweep 或多次仿真
5. 读取输出数据
6. 汇总结果并给出最优参数建议

### 场景 B：从文本需求生成 netlist
用户输入：
> 给我一个 5V 单电源 RC 低通滤波器，截止频率约 1kHz。

系统流程：
1. LLM 识别需求类型为“模板可解”
2. 选择 RC 低通模板
3. 生成参数表或 netlist
4. 用 Multisim 打开 netlist
5. 运行 AC 分析
6. 输出波形与调优建议

### 场景 C：兼容器件替换
用户输入：
> 把 D1 换成另一个快恢复二极管，比较整流效果。

系统流程：
1. 枚举 D1 当前信息
2. 选择同类器件候选
3. 调用替换
4. 重新枚举输入输出
5. 重跑仿真并比较结果

### 场景 D：注入外部输入波形
用户输入：
> 给 V1 输入一个采样波形，重复播放，然后观察输出波形。

系统流程：
1. 枚举 Inputs
2. 绑定指定源
3. 写入 sampled/raw data
4. 设置输出请求
5. 运行 transient
6. 拉取输出数据

---

## 8. 产品原则

1. **基于官方能力，而不是假装全能**
2. **所有修改必须可解释、可回滚、可复核**
3. **优先 netlist / 模板驱动，而不是 GUI 驱动**
4. **所有 AI 输出必须落到结构化对象上**
5. **每一步都必须能导出证据：netlist、图像、数据、日志**

---

## 9. 系统范围与总体架构

## 9.1 架构概览

```text
User / AI Agent
      ↓
MCP Client
      ↓
Multisim MCP Server (Windows Local)
      ├─ Session Manager
      ├─ Multisim COM Adapter
      ├─ Netlist Generator / Parser
      ├─ Template Engine
      ├─ Analysis Orchestrator
      ├─ Result Normalizer
      └─ Safety & Validation Layer
      ↓
NI Multisim (Desktop)
```

## 9.2 模块说明

### A. Session Manager
- 维护当前打开的 circuit session
- 管理文件路径、active variant、仿真状态
- 控制串行访问，避免并发修改冲突

### B. Multisim COM Adapter
- 对 COM Automation API 做统一封装
- 屏蔽底层对象、异常格式与同步/阻塞调用细节

### C. Netlist Generator / Parser
- 从模板 + 参数表生成 netlist
- 校验生成结果是否满足最小可仿真要求
- 支持导入/导出 netlist

### D. Template Engine
- 内置首批常用模板
- 负责从需求归类到拓扑模板
- 约束 AI 首版生成空间，提升稳定性

### E. Analysis Orchestrator
- 统一管理 AC/DC/Transient 执行流程
- 负责输出请求配置、运行时序、结果回收

### F. Result Normalizer
- 把波形、测量值、节点结果转成统一 JSON 结构
- 便于 AI 解读、上层前端展示和后续自动决策

### G. Safety & Validation Layer
- 在执行前校验元件是否存在、仿真是否停止、参数是否合法
- 防止无意义替换、输入输出未刷新、覆盖原文件等操作风险

---

## 10. V0.1 功能需求

## 10.1 文件与会话管理

### F-001 打开设计文件
**描述**：打开一个已有的 `.ms14` 设计文件，并创建当前会话。  
**输入**：文件路径  
**输出**：会话状态、文件名、是否成功  
**校验**：文件存在、扩展名有效、Multisim 可打开  
**异常**：文件不存在、格式不支持、Multisim 未安装或未授权

### F-002 打开 netlist 文件
**描述**：打开 `.cir` / `.txt` netlist 文件并在 Multisim 中生成可仿真对象。  
**输出**：会话状态、文件名、原始 netlist 摘要

### F-003 保存/另存为
**描述**：保存当前设计；支持另存为新文件，避免覆盖源文件。  
**默认策略**：所有 AI 自动修改后的结果优先走 `SaveAs`

### F-004 导出电路截图
**描述**：导出 top-level circuit image 供人工复核与日志记录。  
**用途**：调试、报告、回归测试、前端预览

---

## 10.2 电路对象枚举与读取

### F-010 枚举元件
**描述**：列出当前电路元件 RefDes 列表及必要元数据。  
**最小输出字段**：
- refdes
- section（如有）
- category/group/family（若可得）
- current_value（对 RLC）

### F-011 枚举输入源
**描述**：列出可作为输入的 source 名称，用于后续注入数据或替换输入。

### F-012 枚举输出点
**描述**：列出可请求输出数据的 probe / output 名称。

### F-013 枚举 section / variant
**描述**：列出多 section 器件和设计变体，支持更准确替换与批量试验。

### F-014 导出 netlist
**描述**：导出当前设计的 netlist。  
**用途**：
- 供 AI 读取拓扑
- 供版本管理
- 供外部 SPICE 检查
- 作为变更后的审计证据

### F-015 导出 BOM
**描述**：导出当前设计 BOM，用于器件审计与教学用途。

---

## 10.3 电路修改能力

### F-020 修改 R/L/C 数值
**描述**：修改基础电阻、电容、电感数值。  
**适用范围**：仅基础 RLC 元件；不承诺覆盖高级器件模型。  
**前置条件**：仿真必须停止  
**输出**：修改前后数值

### F-021 替换兼容器件
**描述**：将指定元件替换为数据库中的另一兼容器件。  
**约束**：
- 首版只允许同类替换
- 默认要求用户或 AI 明确给出 group / family / component name
- 替换后必须重新枚举输入输出
- 替换后需执行连通性与输出有效性检查

### F-022 source 参数调整
**描述**：统一提供“源修改”能力，但内部实现区分两类：

#### 模式 A：输入波形注入
- 使用 `SetInputDataRaw` / `SetInputDataSampled`
- 适用于数据驱动输入、采样波形、重复播放波形

#### 模式 B：模板或 netlist 重生成
- 对于无法通过 Automation API 直接安全修改的 source 参数，转而通过模板参数表或 netlist 重生成后重新打开设计实现

**原因**：避免对首版承诺过度的 GUI/数据库级 source 编辑能力。

### F-023 设计快照
**描述**：在执行结构修改前自动保存快照。  
**快照内容**：
- 原文件副本路径
- 修改前 netlist
- 修改前电路截图

---

## 10.4 仿真与分析能力

### F-030 运行仿真
**描述**：支持启动、暂停、恢复、停止基础仿真。  
**状态机**：Stopped / Running / Paused

### F-031 AC Sweep
**描述**：执行 AC Sweep 分析，输出频响数据。  
**最小配置项**：
- start frequency
- stop frequency
- points / decade 或采样密度
- 输出节点列表

### F-032 DC 相关分析
**描述**：支持 DC 基础分析流程，至少覆盖：
- DC operating point 场景
- 依赖 DC 的基础分析准备

### F-033 Transient 分析
**描述**：执行时域瞬态分析。  
**最小配置项**：
- stop time
- time step / 插值策略
- initial condition policy
- 输出节点列表

### F-034 分步输出运行
**描述**：支持运行到下一块输出可用时暂停，供大模型进行逐步观察。  
**用途**：
- 较长时域仿真
- 在线闭环控制
- 数据流式读取

---

## 10.5 输出请求与结果读取

### F-040 设置输出请求
**描述**：指定需要采集的输出点及数据格式。

### F-041 读取输出数据
**描述**：拉取 AC/DC/Transient 输出数据。  
**输出标准化结构**：
- output_name
- analysis_type
- x_axis_label
- x_values
- y_values
- unit
- metadata

### F-042 判断输出是否就绪
**描述**：在长仿真或分步仿真中判断某输出数据是否可读。

### F-043 自动测量摘要
**描述**：对输出数据自动生成摘要指标，例如：
- 峰值
- 均值
- 稳态值
- 过冲
- 截止频率（推导）
- 增益（推导）

> 说明：这层摘要属于 MCP 结果归一化能力，而不是宣称 Multisim 原生单独提供所有高阶指标 API。

---

## 10.6 AI 设计迭代能力

### F-050 从需求到模板选择
**描述**：根据自然语言需求，将问题分类到受支持的模板。  
**首版模板范围建议**：
- RC 低通 / 高通
- 分压器
- 整流基础电路
- 共射 / 运放反相 / 同相放大器基础模板
- RLC 谐振基础模板

### F-051 从需求到参数表
**描述**：在选定模板后，根据目标指标生成一组初始参数。

### F-052 从需求到 netlist
**描述**：在模板不适用或文本定义更自然时，直接生成 netlist。

### F-053 结果驱动的迭代建议
**描述**：基于仿真结果给出下一轮动作建议：
- 增大/减小某 RLC
- 更换器件类型
- 修改输入源
- 建议改用另一模板

### F-054 自动化扫描实验
**描述**：对指定元件或器件集合执行多轮试验，并返回排序结果。  
**适用于**：
- 参数扫描
- 器件替换比较
- 灵敏度分析雏形

---

## 11. MCP 工具设计（V0.1）

以下为建议的 MCP tools 集合。

## 11.1 会话与文件类
- `open_design(path)`
- `open_netlist(path)`
- `save_design()`
- `save_design_as(path)`
- `get_session_state()`
- `export_circuit_image(path)`

## 11.2 枚举与报告类
- `list_components()`
- `list_inputs()`
- `list_outputs()`
- `list_sections(component_refdes)`
- `list_variants()`
- `export_netlist(path_or_inline)`
- `export_bom(path_or_inline)`

## 11.3 修改类
- `set_rlc_value(refdes, value)`
- `replace_component(refdes, section, db, group, family, name, model)`
- `set_input_data_raw(input_name, data, repeat)`
- `set_input_data_sampled(input_name, sample_rate, data, repeat)`
- `clear_input(input_name)`

## 11.4 仿真与分析类
- `run_simulation(timeout_sec)`
- `pause_simulation()`
- `resume_simulation()`
- `stop_simulation()`
- `run_until_next_output()`
- `run_ac_sweep(config)`
- `run_transient(config)`
- `run_dc_analysis(config)`

## 11.5 输出类
- `set_output_request(outputs, config)`
- `is_output_ready(output_name)`
- `get_output_data(output_name, format)`
- `summarize_output(output_name, metrics)`

## 11.6 AI 辅助类
- `generate_template_from_requirement(requirement_text)`
- `generate_params_from_requirement(requirement_text, template_id)`
- `generate_netlist_from_requirement(requirement_text, constraints)`
- `iterate_design(goal, allowed_actions, max_rounds)`

---

## 12. 关键工作流

## 12.1 工作流 1：已有设计调参
1. `open_design`
2. `list_components`
3. `set_rlc_value`
4. `set_output_request`
5. `run_ac_sweep`
6. `get_output_data`
7. `summarize_output`
8. `save_design_as`

## 12.2 工作流 2：文本需求生成并仿真
1. `generate_template_from_requirement`
2. `generate_params_from_requirement`
3. `generate_netlist_from_requirement`（可选）
4. `open_netlist`
5. `list_outputs`
6. `run_ac_sweep` / `run_transient`
7. `get_output_data`
8. `export_circuit_image`

## 12.3 工作流 3：兼容器件比较
1. `open_design`
2. `list_components`
3. `replace_component`
4. `list_inputs` / `list_outputs`（重新枚举）
5. `run_simulation`
6. `get_output_data`
7. `summarize_output`
8. 输出比较表

---

## 13. 数据结构设计

## 13.1 Component
```json
{
  "refdes": "R1",
  "section": "",
  "kind": "RLC|device|source|probe|unknown",
  "group": "Basic",
  "family": "RESISTOR",
  "name": "RESISTOR",
  "value": "1k",
  "editable": true,
  "replaceable": false
}
```

## 13.2 OutputSeries
```json
{
  "output_name": "V(out)",
  "analysis_type": "AC|DC|TRANSIENT",
  "x_axis_label": "frequency",
  "x_unit": "Hz",
  "y_axis_label": "magnitude",
  "y_unit": "V",
  "x_values": [100, 200, 500],
  "y_values": [0.98, 0.91, 0.70],
  "metadata": {
    "source_file": "demo.ms14",
    "timestamp": "..."
  }
}
```

## 13.3 IterationProposal
```json
{
  "goal": "截止频率接近 1kHz",
  "current_status": "实测约 1.34kHz",
  "proposed_actions": [
    {
      "action": "set_rlc_value",
      "target": "C1",
      "new_value": "120n"
    }
  ],
  "rationale": "增加 C 可降低截止频率"
}
```

---

## 14. 状态与错误模型

## 14.1 状态机

### 会话状态
- `idle`
- `design_opened`
- `netlist_opened`
- `modified`
- `simulation_running`
- `simulation_paused`
- `error`

### 仿真状态
- `stopped`
- `running`
- `paused`

## 14.2 错误分类

### E1 文件类错误
- 文件不存在
- 路径非法
- 扩展名不支持
- 打开失败

### E2 会话类错误
- 当前无打开电路
- 电路对象已失效
- Multisim 未连接

### E3 修改类错误
- 元件不存在
- section 不存在
- 仿真运行中禁止修改
- ReplaceComponent 目标非法
- RLCValue 不适用该元件
- 替换后 pin 不匹配导致 nets 丢失

### E4 仿真类错误
- 输出未请求
- 输出未就绪
- 输入未重新设置
- 分析配置不完整
- DC operating point 求解失败

### E5 AI 类错误
- 需求无法映射到支持模板
- 生成的 netlist 缺少必要节点
- 生成结果不满足可仿真最小条件

## 14.3 错误返回规范
每个 MCP tool 统一返回：
- `ok`
- `error_code`
- `error_message`
- `multisim_last_error`（如有）
- `suggested_recovery`

---

## 15. 安全与可控性要求

1. 默认不覆盖源文件
2. 默认在每次结构修改前生成快照
3. 对危险操作提供 dry-run 模式
4. 替换器件时默认只允许同类器件
5. 对 AI 自动生成 netlist 启用基本校验器
6. 所有工具调用都记录审计日志
7. 不允许远程自动执行任意本地脚本作为替代方案

---

## 16. 审计与日志

每次操作记录：
- 时间戳
- 工具名
- 输入参数摘要
- 目标文件
- 修改前后快照路径
- 仿真状态
- 错误信息
- 结果摘要

日志用途：
- 回放问题
- 复现实验
- 评估 AI 设计质量
- 教学审计

---

## 17. 成功指标

## 17.1 功能成功率
- `.ms14` 打开成功率 ≥ 95%
- `.cir` / `.txt` netlist 打开成功率 ≥ 90%
- 基础 RLC 改值成功率 ≥ 95%
- 同类器件替换成功率 ≥ 80%
- AC / Transient 分析执行成功率 ≥ 90%

## 17.2 用户价值指标
- 用户完成一次“打开 → 改参数 → 仿真 → 读结果”闭环时间下降 50%
- 模板驱动生成的基础电路一次可仿真率 ≥ 70%
- AI 迭代建议被用户采纳比例 ≥ 30%

## 17.3 稳定性指标
- 单会话崩溃率 < 5%
- 因状态不一致导致的调用失败率 < 10%

---

## 18. 首版模板库建议

### T001 RC 低通
输入：截止频率、输入幅值  
输出：R、C 初值、AC 验证流程

### T002 RC 高通

### T003 电压分压器

### T004 半波 / 全波整流基础模板

### T005 反相运放放大器
输入：目标增益、供电条件  
输出：Rf / Rin 初值

### T006 同相运放放大器

### T007 RLC 谐振基础模板

> 原则：首版模板必须少而稳，不求覆盖所有电路，只求闭环成功率。

---

## 19. 版本规划

## V0.1
- 打开设计 / netlist
- 枚举对象
- RLC 改值
- 同类器件替换
- AC/DC/Transient 基础分析
- 输出请求与结果读取
- 导出 netlist/BOM/截图
- 模板/参数表/netlist 生成
- 基础设计迭代

## V0.2
- 设计回滚
- 多轮自动扫描实验管理
- 模板库扩展
- 结果可视化前端
- 参数优化器
- 结构一致性检查器

## V0.3
- 更复杂子电路模板
- 批量项目运行器
- 与外部 LLM/Agent 平台深度集成
- 更强的 netlist 修复和约束求解能力

---

## 20. 技术选型建议

### 服务端语言
优先级建议：
1. Python
2. C#

### 原因
- 均适合 Windows 本地开发
- 容易封装 COM 调用
- 容易接入 MCP server runtime
- 便于做结构化 JSON 输出与日志系统

### 首版建议
- **MCP Server：Python**
- **COM Adapter：Python 封装层**
- **AI 规划层：同进程或独立 Agent 调用**

---

## 21. 开发里程碑

### M1：基础连接层
- 能连接 Multisim
- 能打开文件
- 能列出元件、输入、输出
- 能导出 netlist

### M2：基础修改层
- 能改 RLC 值
- 能替换兼容器件
- 能导出截图

### M3：分析层
- 能稳定执行 AC / Transient / DC 基础流程
- 能拉取输出并标准化

### M4：AI 生成层
- 完成模板库 v0.1
- 完成需求 → 参数表 / netlist
- 完成单轮设计迭代建议

### M5：首版验收
- 完成至少 5 个模板闭环 demo
- 完成日志、错误模型与回归测试

---

## 22. 验收标准

以下任一 demo 成功通过可计入验收：

1. 打开现有 `.ms14`，把 R1 从 1k 改到 2k，运行 AC，输出 V(out) 曲线。
2. 打开 netlist，自动生成可仿真 schematic，运行 transient 并导出结果。
3. 替换某个二极管为同类器件，重新枚举输出并比较波形。
4. 给源注入 sampled input，读取输出并生成摘要。
5. 从“做一个 1kHz RC 低通”这句需求出发，完成模板选择、参数生成、仿真、结果解释。

---

## 23. 一句话定义

> **Multisim MCP v0.1 是一个以 netlist 与结构化仿真编排为中心的本地 Agent 控制层，而不是一个试图完全接管 Multisim GUI 的自动画图机器人。**

