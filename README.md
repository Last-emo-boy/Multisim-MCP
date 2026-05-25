# Multisim MCP Server

NI Multisim Automation API 的 MCP（Model Context Protocol）服务端。它让支持 MCP 的 AI Agent 通过本地 stdio server 控制 Multisim，完成电路打开、枚举、修改、仿真、SPICE 分析、波形测量和报告生成。

当前版本是 `0.1.0`，定位为 alpha。核心能力可安装和测试；连接真实 Multisim 的工具需要 Windows + NI Multisim 环境。

## 功能概览

- 61 个 MCP tools，覆盖会话、文件、元件枚举、电路修改、仿真控制、输出采集、SPICE 分析、虚拟仪器、报告生成和设计规则检查。
- 7 个 MCP prompts，提供电路分析、SPICE 分析、参数扫描、故障排查、报告导出和实验报告工作流。
- 同时支持 `.ms14` / `.ms8+` 设计文件和直接从 SPICE netlist / 内置模板运行分析。
- 提供纯 Python 工具：netlist builder、template library、design rule checker、signal measurement，可在没有 Multisim 的环境下单元测试。

## 系统要求

- Windows 10/11。
- NI Multisim 14.x，已安装并激活 COM Automation API。
- Python 3.10 或更高版本。
- `pywin32`。如果你的 Multisim COM 组件是 32-bit，请使用 32-bit Python 环境运行 server。

报告、绘图和 schematic rendering 功能需要额外安装 `report` extras，见安装章节。

## 安装

从源码安装：

```powershell
python -m pip install .
```

开发安装：

```powershell
python -m pip install -e ".[dev]"
```

包含绘图和报告能力：

```powershell
python -m pip install -e ".[dev,report]"
```

启动 MCP server：

```powershell
multisim-mcp
```

也可以直接通过模块运行：

```powershell
python -m multisim_mcp.server
```

## MCP 客户端配置

Claude Desktop / 通用 MCP 配置：

```json
{
  "mcpServers": {
    "multisim": {
      "command": "multisim-mcp",
      "args": []
    }
  }
}
```

VS Code `.vscode/mcp.json`：

```json
{
  "servers": {
    "multisimMcp": {
      "type": "stdio",
      "command": "multisim-mcp",
      "dev": {
        "watch": "src/**/*.py"
      }
    }
  }
}
```

## 工具分类

| 分类 | 代表工具 | 用途 |
| --- | --- | --- |
| Session | `connect`、`disconnect`、`get_session_state` | 启动、关闭和检查 Multisim 会话 |
| File | `open_design`、`open_netlist`、`save_design_as`、`export_circuit_image` | 打开、保存和导出设计 |
| Enumerate | `list_components`、`list_inputs`、`list_outputs`、`list_variants`、`list_circuit_parameters` | 发现 RefDes、probe、input 和参数名 |
| Modify | `set_rlc_value`、`set_circuit_parameter_value`、`replace_component`、`set_input_data_sampled` | 修改电路或输入波形 |
| Simulate | `run_simulation`、`run_transient`、`run_ac_sweep`、`run_dc_operating_point` | 控制仿真和执行常见分析 |
| Output | `set_output_request`、`is_output_ready`、`get_output_data`、`summarize_output` | 采集和汇总仿真输出 |
| SPICE | `run_spice`、`parameter_sweep`、`run_command_line` | 以内联 netlist 和 nutmeg commands 运行 SPICE |
| Instruments | `function_generator`、`oscilloscope`、`plot_waveform` | 虚拟函数发生器、示波器和独立波形绘图 |
| Templates | `list_circuit_templates`、`get_circuit_template`、`materialize_design_template` | 生成常见电路的可运行 netlist |
| Builder / Catalog | `build_netlist`、`search_component_catalog`、`list_component_categories` | 程序化构建电路和搜索 Multisim 元件 |
| Verification | `check_design_rules`、`simulate_block`、`simulate_pipeline`、`measure_signals` | 设计规则检查、分块仿真和信号测量 |
| Reports | `simulation_report`、`render_netlist_schematic`、`generate_markdown_report` | 生成 HTML / Markdown 报告和 schematic 图片 |

## 推荐工作流

打开现有 Multisim 设计并做瞬态分析：

```text
connect
open_design("C:/path/to/design.ms14")
list_outputs
run_transient(output_names=["V(out)"], stop_time=0.01, sample_rate=10000)
get_output_data("V(out)")
summarize_output("V(out)")
```

使用内置模板直接跑 SPICE：

```text
connect
get_circuit_template("inverting_amp", analysis="tran", overrides={"R1": 10000, "Rf": 100000})
run_spice(netlist=<returned netlist>, commands=<returned commands>)
measure_signals(signals=[...], gain_pairs=[{"input": "$in", "output": "$out"}])
```

程序化构建 netlist：

```text
build_netlist(
  title="Voltage divider",
  components=[
    {"type": "V", "refdes": "V1", "nplus": "in", "nminus": "0", "value": "DC 5"},
    {"type": "R", "refdes": "R1", "n1": "in", "n2": "out", "value": 10000},
    {"type": "R", "refdes": "R2", "n1": "out", "n2": "0", "value": 10000}
  ],
  output_nodes=["out"]
)
check_design_rules(netlist=<returned netlist>)
run_spice(netlist=<returned netlist>, commands=<returned commands>)
```

## 使用规则

- 先调用 `connect`，再调用其他依赖 Multisim 的工具。
- 操作 `.ms14` 设计前先调用 `open_design`；操作 netlist 文件前先调用 `open_netlist` 或使用 `run_spice`。
- 修改元件前确保仿真已停止，必要时先调用 `stop_simulation`。
- 引用 probe、input、RefDes 或 circuit parameter 前，先调用对应的 `list_*` 工具枚举真实名称。
- R/L/C 值使用 SI 基本单位：`1kΩ = 1000`，`10nF = 1e-8`，`4.7uH = 4.7e-6`。
- `run_spice` 中 node voltage 使用 `$` 前缀，例如 `print $out $in`。

## 项目结构

```text
src/multisim_mcp/
  server.py              MCP tool 和 prompt 注册入口
  com_adapter.py         Multisim COM Automation API wrapper
  session.py             会话状态、snapshot 和 audit log
  models.py              Pydantic response model
  tools/
    file_tools.py        会话和文件操作
    enum_tools.py        元件、输入、输出、参数枚举
    modify_tools.py      电路修改
    simulation_tools.py  仿真控制和常见分析
    output_tools.py      输出采集和摘要
    spice_tools.py       run_spice 和 parameter_sweep
    instrument_tools.py  function generator、oscilloscope、plot_waveform
    report_tools.py      HTML 报告
    circuit_templates.py 内置电路模板
    netlist_builder.py   程序化 netlist 构建
    design_checks.py     netlist 设计规则检查
    signal_measure.py    波形测量
```

## 开发与验证

运行单元测试：

```powershell
python -m pytest
```

构建发布包：

```powershell
python -m build
```

检查发布包元数据：

```powershell
python -m twine check dist/*
```

当前测试覆盖不依赖 Multisim 的核心纯 Python 工具。COM 自动化路径需要在安装了 NI Multisim 的 Windows 环境中做集成验证。

## 发布清单

发布前建议确认：

- `python -m pytest` 通过。
- `python -m build` 通过。
- `python -m twine check dist/*` 通过。
- 在目标 Windows 环境中运行 `multisim-mcp`，并用 MCP client 调用 `connect`。
- 使用一个真实 `.ms14` 文件验证 `open_design`、`list_outputs`、`run_transient` 和 `get_output_data`。

## 安全和数据

- 结构修改前会通过 session manager 创建 snapshot。
- 操作会写入 audit log，默认位置是 `~/.multisim_mcp/audit_log.json`。
- 推荐优先使用 `save_design_as`，避免覆盖原始设计文件。

## 许可证

ISC。详见 [LICENSE](LICENSE)。
