# MyPlan Google Calendar 滚动同步版

这版把 Google Calendar 同步改成了 **rolling single event** 策略：

- `Once`：同步成一个普通单次事件
- `Daily / Weekly / Monthly / Weekdays / Holidays`：**不再创建 Google recurrence**
- 对于循环任务，Google Calendar 中始终只保留 **一个“下一次待执行事件”**
- 当当前这次时间过去后，下一轮同步再把这个事件更新成下一次

## 为什么这样改

这样更符合你的真实使用方式：

- 不会一下子在 Google Calendar 里铺满未来一年或两年的事件
- 循环任务停止时更容易删除
- 逻辑上完全由 Notion 的 `Next Date` 控制
- GitHub Actions 每 10 分钟跑一次就够了

例如：

- 现在是 `05:00`
- 一个 `Daily` 任务今天 `09:00`
- 本轮同步只会保留 **今天 09:00**
- 要等到 `09:00` 之后，`Next Date` 更新为明天 `09:00`，下一轮同步才会把 Google 事件改成明天

## 当前同步规则

- 只同步 `SyncToGoogle = true`
- 只同步 `Status in (Pending, Ongoing)`
- 先依赖 `Next Date`
- 没有 `Next Date` 时回退到 `Start Date`
- `Finished / Cancelled / SyncToGoogle=false / archived / in_trash` 会删除对应的托管 Google 事件
- 会自动清理：
  - orphan event（Google 里有，但 Notion 里已不需要）
  - duplicate event（同一 Notion task 对应多个 Google 托管事件）

## 托管标记

同步写入的 Google event 会在 `extendedProperties.private` 中保存：

- `source = MyPlan`
- `sync_strategy = rolling_single_event`
- `notion_page_id`
- `sync_hash`
- `repeat_type`

## 命令

只做 Google 同步 dry-run：

```bash
python -m notion_module.sync_to_google
```

正式写入：

```bash
python -m notion_module.sync_to_google --commit
```

一条命令先重算 `Next Date` 再同步 Google：

```bash
python -m notion_module.sync_pipeline
```

正式执行完整流水线：

```bash
python -m notion_module.sync_pipeline --commit
```

## GitHub Actions

已新增：

```text
.github/workflows/myplan_sync.yml
```

默认每 10 分钟运行一次，并支持手动触发。

需要配置这些 secrets：

- `NOTION_TOKEN`
- `NOTION_VERSION`
- `NOTION_CONFIG_DATA_SOURCE_ID`
- `NOTION_TOPICS_DATA_SOURCE_ID`
- `NOTION_TASKS_DATA_SOURCE_ID`
- `NOTION_LEAVE_DATA_SOURCE_ID`
- `GOOGLE_CALENDAR_ID`
- `GOOGLE_TOKEN_JSON`

其中 `GOOGLE_TOKEN_JSON` 直接存你本地 `google_token.json` 的完整文本内容。

## 建议目录结构

```text
MyPlan/
├─ .github/
│  └─ workflows/
│     └─ myplan_sync.yml
├─ notion_debug_output/
├─ notion_module/
│  ├─ cli/
│  │  └─ sync_pipeline.py
│  ├─ services/
│  │  └─ google_sync_service.py
│  ├─ google_calendar_client.py
│  ├─ next_date.py
│  ├─ reader.py
│  ├─ writer.py
│  ├─ sync_to_google.py
│  └─ sync_pipeline.py
├─ README_google_sync.md
├─ requirements.txt
└─ google_token.json
```

## 说明

- 这版的核心不是靠 Google recurrence，而是靠 **Notion `Next Date` + 定时同步**
- 这也意味着：**Notion 才是唯一真源**，Google Calendar 只是提醒层
- 如果以后你要支持“保留历史执行记录”，建议把历史留在 Notion `Records`，而不是留在 Google Calendar
