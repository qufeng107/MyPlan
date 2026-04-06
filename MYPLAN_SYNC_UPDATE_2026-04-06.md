# MyPlan 同步改造说明（2026-04-06）

## 这次改了什么

### 1. 循环事件改成滚动单事件

不再给 `Daily / Weekly / Monthly / Weekdays` 创建 Google recurrence。

现在统一改成：

- Google Calendar 中每个 Notion 循环任务最多只保留 **1 个下一次事件**
- 当本次时间过去后，下一轮同步再把它更新成下一次

### 2. Google 同步改成真正对比 Notion 与 Google

同步前会先读取 Google Calendar 中由 MyPlan 托管的事件（通过 `extendedProperties.private.source=MyPlan` 标记）。

然后会处理：

- 该创建的创建
- 该更新的更新
- 该删除的删除
- orphan / duplicate 托管事件自动清理

### 3. 新增完整流水线命令

```bash
python -m notion_module.sync_pipeline --commit
```

执行顺序：

1. 读取 Notion
2. 重算 `Next Date`
3. 写回 Notion
4. 读取 Google Calendar
5. 对比并同步

### 4. GitHub Actions 已加好

文件：

```text
.github/workflows/myplan_sync.yml
```

默认每 10 分钟执行一次。

## 新增 / 主要修改文件

- `notion_module/services/google_sync_service.py`
- `notion_module/cli/sync_pipeline.py`
- `notion_module/sync_pipeline.py`
- `notion_module/google_calendar_client.py`
- `notion_module/sync_to_google.py`
- `.github/workflows/myplan_sync.yml`
- `README_google_sync.md`

## 推荐你以后主要用的命令

### 本地 dry-run

```bash
python -m notion_module.sync_pipeline
```

### 本地正式同步

```bash
python -m notion_module.sync_pipeline --commit
```

### 只看 Google 同步层

```bash
python -m notion_module.sync_to_google
```

## GitHub Secrets

至少配置：

- `NOTION_TOKEN`
- `NOTION_VERSION`
- `NOTION_CONFIG_DATA_SOURCE_ID`
- `NOTION_TOPICS_DATA_SOURCE_ID`
- `NOTION_TASKS_DATA_SOURCE_ID`
- `NOTION_LEAVE_DATA_SOURCE_ID`
- `GOOGLE_CALENDAR_ID`
- `GOOGLE_TOKEN_JSON`

`GOOGLE_TOKEN_JSON` 直接放本地 `google_token.json` 的完整文本。
