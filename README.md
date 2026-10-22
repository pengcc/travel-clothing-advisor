# Travel Clothing Advisor

面向赴德国旅行、对当地气候不熟悉的用户，把气温信息转化为**需要带多厚的外套、哪些内搭/保暖层要带、早晚和冷热变化如何增减衣物**等简明备衣建议。不是实时天气 App，也不承诺精确个人体感。

**项目方向、功能规则、当前架构、已完成状态和分阶段交付，以 [MVP Functional & Technical Specification](docs/mvp-functional-technical-spec.md) 为统一依据。** 进一步的目标用户和问题验证见 [Product Blueprint](docs/product-blueprint.md)；协作阶段及权限见 [Collaboration Workflow](docs/collaboration.md)。

## 功能范围

- **第一批精选 10 个德国城市**，优先展示德国当地今天起有效的 14 天真实逐小时气温所推导的备衣建议、主要温差提醒及数据来源。在当前 Git 只读 Preview 中，若精选城市预报缺失或过期，卡片和详情仅在该城市对应行程的五年 ERA5 历史完整时回退为明确标注的历史参考，否则显示不可用；城市卡片与个人行程查询互相独立。20 城是后续候选，100 城并未批准。
- **按行程查询**：城市、起止日期和怕冷/正常/怕热（默认正常）。当前 Web MVP 允许德国今天起 30 天内的旅行日期。整趟位于今天至 +13 天的行程**优先使用有效的 14 天预报**；当前 Git 只读 Preview 若无有效预报，仅在整趟所需的五年 ERA5 历史资料完整时回退为**历史气温参考**，否则明确不可用。行程超过 +13 天、但仍在 +29 天以内时，**整趟**使用完整的过去五年同期历史参考；两种历史情形均明确标记模式和数据来源，绝不把历史写成未来预报。
- **五年历史须完整**才能生成历史建议；缺失时如实显示不可用。只使用气温与日间/早晚温差，不提供雨雪风提醒、逐日时尚穿搭或 AI 图像。
- 不需要用户账户，也不收集个人行程持久记录。支持手机优先的中文界面和复制/分享建议。

## 当前交付状态（2026-10-22）

| 能力 | 实际状态 |
| --- | --- |
| Python Web/CLI、14 天预报下载与校验、手动本地启动 | **已有代码**，本地运行可使用 `.forecast-local/` |
| 五年 ERA5 历史按城市/月分批下载、校验并复用 | **已有本地实现**；不等于十城全年历史均已齐 |
| Vercel Preview Git 只读显示预报/历史/缺失状态 | **已有代码及 Preview 路径**；网页只读取已部署包里的 `weather-data/` |
| 第一批十城真实预报的 Git 数据 | **已合并 [PR #67](https://github.com/pengcc/travel-clothing-advisor/pull/67)**：十城 2026-10-22 快照（德国午夜后不再是当日有效预报）；合并本身**不等于 Preview 已更新或验收** |
| Git 中的五年历史资料 | 目前已验证柏林、慕尼黑 2021–2025 年 10/11 月共 **20 个月度对象**；其他城市待分批补齐 |
| 无人值守天气获取 → Git 更新 → Preview 更新 | **未完成**；旧 PostgreSQL/Blob P1 worker 代码虽存在，但默认关闭，未作为 Git Preview 自动更新运行 |
| 公共 Production 上线、20/100 城实际支持 | **未完成／未批准**；当前只考虑受保护 Preview 和免费资源 |

## 现在的数据架构

```text
本地 Python（Open-Meteo 预报 / ERA5 历史）
  ├─ .forecast-local/      当天有效预报
  └─ .history-local/       长期保留的已验证历史月份
            ↓ 手动校验、导出并增量合并
Git weather-data/         只提交公开真实资料，不提交缓存账本/密钥
            ↓ 当前必须手动重新部署
受保护 Vercel Preview      api/index.py 只读数据 → 手机网页
```

- **本地有数据不等于线上有数据**：`make dev` 使用本地目录；Preview 只读当前部署所含 Git 数据。两者尚不会自动同步。
- **预报每日过期**：新德国日期必须取新 14 天快照并更新 Preview；历史月份已经完整验证后长期复用，按近期需求逐批积累，不每天重下。
- **保留历史数据**：`web.bundle_data` 只导出当前窗口匹配的有效月份；并入 `weather-data/` 时必须采用**增量合并**，保留以前有效的历史月份，不得整体删除或用新目录覆盖旧历史。
- `vercel.json` 现在有 `git.deploymentEnabled=false`，因此 Git 合并**不会触发自动部署**。Preview 使用默认 Git 只读数据路径；旧 `TRAVEL_PREVIEW_NAMESPACE` Blob 路径或 `TRAVEL_P1_READER` P1 SQL/Blob 路径是独立可选开关，并非当前路径的必要配置。
- **费用边界**：全部免费、不买 VPS、不升级套餐；动态存储、自动化和公开发布均需要另外验证实际账户能力、费用和授权。**不为第一批十城人工发布先引入数据库或 Blob。**

## 渐进交付顺序

1. **十城真实 14 天预报**：本地准备 → 校验 → Git 更新 → 受保护 Preview 实测十城页面和详情；可先人工维护。PR #67 已完成 Git 部分，Preview 对应新版本的实际验收仍须进行。
2. **十城历史分批覆盖**：先近期旅行所需的五年同期月份，再按城市与月份扩大覆盖；完整有效的月文件持续保留并发布，不等全部全年数据齐备才支持已有覆盖的行程。
3. **自动更新**：仅在人工链路真正跑通后，自动执行相同的预报日更、历史增量补齐和 Git/Preview 发布，记录失败与用量。
4. **扩展到 20 城**：依据十城真实使用体验、免费额度和发布成本再决定；100 城只是可能的更远期扩展。

## 本地运行与数据准备

Web 开发服务为 Python 标准库项目（建议用仓库的 Python 3.12）：

```sh
make dev         # 使用 .forecast-local/ + .history-local/，有清单时尝试补当日精选预报
make check-dev   # 只读检查本地数据准备情况
make test        # Python 单元测试；不应触发真实天气下载
make demo        # 明确使用 UI 模拟资料，不是 Open-Meteo 实况
```

浏览器打开 `http://127.0.0.1:8000`。单独运行 `python3 -m web.server` **不会自动挂载**两套本地持久缓存；请使用 `make dev`。

需要准备/检查真实数据、分批获取历史月份或导出到 Git 时，按 [Web 操作说明 — Git weather bundle](web/README.md#git-weather-bundle) 使用现有 `web.prefetch_forecasts`、`web.prefetch_history`、`web.bundle_data`；这些命令不会自动更新远端 Git 或 Vercel。数据目录的来源与过期规则见 [weather-data/README.md](weather-data/README.md)。

历史的独立 CLI 实验 `experiments/clothing-rules/trip_advisor.py` 仍使用八年参考等较早实验规则，**不是当前网页五年历史功能契约**。

**当前安全边界：** 文档、PR、数据提交、合并、实际云端部署和启用定时任务是不同操作，均遵守 [Collaboration Workflow](docs/collaboration.md) 中的授权要求。已能构建网页不等于已完成真实数据可用性、连续日更或公开上线验收。
