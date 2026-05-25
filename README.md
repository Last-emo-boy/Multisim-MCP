# Multisim MCP Server

NI Multisim 自动化 API 的 MCP (Model Context Protocol) 服务端，允许 AI Agent 和大模型直接操控本地 Multisim 进行电路仿真与设计迭代。

## 系统要求

- Windows 10/11
- NI Multisim 14.x 已安装并激活
- Python ≥ 3.10
- pywin32 (COM 支持)

## 安装

```bash
cd "Multisim MCP"
pip install -e .
```

## 使用

### 作为 MCP Server 运行 (stdio)

```bash
multisim-mcp
```

### VS Code / Claude Desktop 配置

在 `claude_desktop_config.json` 或 `.vscode/mcp.json` 中添加：

```json
{
  "mcpServers": {
    "multisim": {
      "command": "multisim-mcp",
      "args": [],
      "env": {}
    }
  }
}
```

或使用 Python 直接运行：

```json
{
  "mcpServers": {
    "multisim": {
      "command": "python",
      "args": ["-m", "multisim_mcp.server"],
      "env": {}
    }
  }
}
```

## 工具列表 (30 Tools)

### 会话与文件 (8)
| 工具 | 描述 |
|------|------|
| `connect` | 连接到本地 Multisim 实例 |
| `disconnect` | 断开并终止 Multisim |
| `open_design` | 打开 .ms14 设计文件 |
| `open_netlist` | 打开 SPICE netlist 文件 |
| `save_design` | 保存当前电路 |
| `save_design_as` | 另存为新文件 |
| `export_circuit_image` | 导出电路截图 (PNG/JPG/BMP) |
| `get_session_state` | 获取当前会话状态 |

### 枚举与报告 (7)
| 工具 | 描述 |
|------|------|
| `list_components` | 列出所有元件及其值 |
| `list_inputs` | 列出可用输入源 |
| `list_outputs` | 列出可用输出探针 |
| `list_sections` | 列出多 section 元件的子部分 |
| `list_variants` | 列出设计变体 |
| `export_netlist` | 导出 netlist |
| `export_bom` | 导出 BOM |

### 电路修改 (5)
| 工具 | 描述 |
|------|------|
| `set_rlc_value` | 修改 R/L/C 元件值 |
| `replace_component` | 替换兼容器件 |
| `set_input_data_raw` | 注入任意波形数据 |
| `set_input_data_sampled` | 注入等间隔采样数据 |
| `clear_input` | 清除输入数据 |

### 仿真与分析 (7)
| 工具 | 描述 |
|------|------|
| `run_simulation` | 启动仿真 |
| `pause_simulation` | 暂停仿真 |
| `resume_simulation` | 恢复仿真 |
| `stop_simulation` | 停止仿真 |
| `run_ac_sweep` | AC 频扫分析 |
| `run_dc_operating_point` | DC 工作点分析 |
| `run_transient` | 瞬态分析 |

### 输出读取 (5+)
| 工具 | 描述 |
|------|------|
| `set_output_request` | 配置输出采集请求 |
| `clear_output_request` | 清除输出请求 |
| `is_output_ready` | 检查输出数据是否就绪 |
| `get_output_data` | 获取仿真输出数据 |
| `summarize_output` | 自动计算输出摘要指标 |
| `run_until_next_output` | 运行到下一个输出块就绪 |
| `run_command_line` | 直接执行 SPICE 命令 (专家模式) |

## 典型工作流

### 1. 打开已有设计并调参

```
connect → open_design("amp.ms14") → list_components → set_rlc_value("R1", 2000)
→ list_outputs → run_ac_sweep(outputs, ...) → get_output_data → summarize_output
```

### 2. 器件替换比较

```
connect → open_design → replace_component("D1", group="Diodes", family="DIODE", name="1N5712")
→ list_outputs → run_transient → get_output_data → summarize_output
```

### 3. 注入自定义波形

```
connect → open_design → list_inputs → set_input_data_sampled("V1", 10000, [...])
→ set_output_request("V(out)", ...) → run_simulation → get_output_data
```

## 架构

```
AI Agent / MCP Client
       ↓
Multisim MCP Server (stdio)
  ├─ server.py          ← MCP tool registration
  ├─ session.py         ← Session state & audit log
  ├─ com_adapter.py     ← COM API wrapper
  ├─ models.py          ← Pydantic schemas
  └─ tools/
      ├─ file_tools.py       ← 文件/会话操作
      ├─ enum_tools.py       ← 枚举/报告
      ├─ modify_tools.py     ← 电路修改
      ├─ simulation_tools.py ← 仿真控制
      └─ output_tools.py     ← 输出读取
       ↓
NI Multisim (COM Automation API)
```

## 安全设计

1. **自动快照**：每次结构修改前自动备份原文件
2. **审计日志**：所有操作记录到 `~/.multisim_mcp/audit_log.json`
3. **默认 SaveAs**：避免覆盖原始设计文件
4. **仿真状态检查**：修改前自动确认仿真已停止
5. **同类替换约束**：首版仅允许同类器件替换

## 许可

ISC
