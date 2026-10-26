# 隔离真实 DSH 运行时验收

当前两份最终报告绑定 `C:/Users/zy/.dsh/plugins/dsh-mcm-team` 的安装字节：`native-runtime-smoke.json` 的主运行机制9项和 `guard-native-runtime.json` 的原生门禁10项均通过。测试将这些源码挂载到独立Host，不修改用户正在运行的profile，不读取用户凭据，也不调用外部模型。模型回答由进程内确定性适配器提供。

## 重跑顺序

在交付目录所在工作区执行，先重跑门禁，再重跑依赖该证据的主检查：

```powershell
$runner = (Resolve-Path '.\outputs\mcm-dsh-team-v0.2.0\audit\run-native-smoke.mjs').Path
$installedBundle = 'C:/Users/zy/.dsh/plugins/dsh-mcm-team'
$guardReport = Join-Path (Split-Path -Parent $runner) 'guard-native-runtime.json'
$mainReport = Join-Path (Split-Path -Parent $runner) 'native-runtime-smoke.json'

node $runner '--desktop-root=E:/dsh desktop' "--bundle-root=$installedBundle" '--fixture=guard-native-fixture.mjs' "--report=$guardReport"
node $runner '--desktop-root=E:/dsh desktop' "--bundle-root=$installedBundle" '--fixture=native-fixture.mjs' "--report=$mainReport"
```

路径应按实际机器调整。省略 `--bundle-root` 会使用交付包内候选bundle，不能把这种结果称为当前安装目录的验收。主fixture读取同目录的 `guard-native-runtime.json` 并核对来源与SHA，因此顺序不可倒置。重跑会更新相应报告；需要保留历史时先另存当前报告，不追改既有证据。

脚本使用桌面版附带的 Electron/Node、Cordis 与 DSH 0.2.1-rc.2 模块，在 `work/mcm-host-smoke/<时间>/` 创建独立 `DSH_HOME`、项目和profile；按 `--bundle-root` 把指定源码链接到隔离profile。它不负责把插件安装到用户桌面，不关闭应用，也不更改权限或安全设置。

## 主运行机制9项

主报告覆盖12角色注册、12棵插件树及PTC SDK挂载、队长默认执行态、深度2和相邻父子消息、真实 `run_code → mcm_archive_audit` 三会话归档、隔离容量与回收、可选编程主管下两名编程手、论文主管下图表角色实际读取技能并生成四图、检索角色实际技能读取与公开元数据核验。

其中受控的原生派发与消息API相容性检查直接调用工具的execute方法；它们不单独证明门禁生效。归档测试经过真实模型流、工具调度器、PTC子进程、嵌套工具和公开会话/文件服务。门禁的强制执行另由下述10项真实管线检查证明，主报告绑定其当前SHA。

容量测试独占另一棵隔离会话树，验证该测试Host默认的7个常规位加1个应急位、等待主管仍占位、第9次以 `ACTIVATION_LIMIT_REACHED` 拒绝及确认回收后继续一个待办。待办由fixture管理，Host不会自动排队被拒绝的任务。该证据不证明用户活跃Host的总容量、全局剩余名额或Team成员上限。

公开文献探针保留OpenAlex主题搜索429；Crossref检索及DOI六字段、OpenAlex独立DOI标题/年份核验成功，没有取得全文。检索结果不证明方法结论，也不等于人工核验或选模依据。

## 原生门禁10项

门禁fixture实际经过 `模型流 → agent loop → run_code → 嵌套工具 → tools/pre-execute → 单调guard → 原生dispatch`，覆盖：

1. 容量未知与未获许可的直接原生派发被拒绝，未创建孩子。
2. 过期快照、常态名额耗尽、显式admit=false和暂停拒绝准入。
3. 许可签发后再暂停，原生派发仍被拒绝。
4. 实际等待许可自然到期后拒绝，不用测试时钟替代该检查。
5. 新鲜证据、登记任务和完全相同参数允许原生派发。
6. 一个许可的并发尝试最多成功一次。
7. 真实预设、父级、深度读回及非直属孩子访问拒绝。
8. 已测试的全局替代委派入口在正常工具管线被拒绝，监测用工具正文未执行。
9. 已结束孩子使用历史记录读回，不加载或恢复该孩子。
10. 真实PTC嵌套派发事件实际落地。

这些检查的容量变化输入明确是隔离环境的合成正负例；替代委派工具使用检测正文是否运行的测试定义。它们验证门禁执行机制，不宣称核实用户当前占槽，也不认证任意shell、外部进程或OS隔离。

## 当前字节与提示词绑定

两个报告各记录12份当前bundle来源指纹，包括两份runtime-guard源码、生成配置和provenance；fixture及launcher也分别记录SHA。主报告另显式记录13份归一化提示词指纹。门禁报告没有独立的 `prompt_sha256` 字段，通过相同当前cordis.patch/provenance、只读构建核对和主报告的13份提示词及guard报告SHA互链，提供间接提示词覆盖；不把缺失字段补造为实测。

开始、结束和外层启动器均检查来源字节。修改bundle或fixture后先构建并重新执行相应检查；不能沿用旧报告。测试期间变化会判失败或stale。失败现场留在对应work目录，不能把成功摘要套到失败记录上。

## 与桌面模型及视觉验收的边界

早先独立桌面会话实际生成了四类图并调用nature-figure，见 [真实模型演练复核](live-model-verification.json)。它保留DEV-01“容量准入失败仍派发”及部分自述不符，不是完整通过。当前硬门禁已经通过上述真实机制检查；修订后的[桌面外部模型负向复验](guard-live-verification.json)另有7项独立检查通过，确认实际预检拒绝、直接原生派发拒绝和零子会话。负向验证与确定性机制检查分别留证，不冒称完整自主建模通过。

这些运行检查不验证建模科学质量、获奖概率或最终论文审美。完整图件与实际入稿PDF须另行视觉审阅，用户H0–H3均不能由技术测试代签。原暂停演练不参与测试、不恢复、不迁移。Windows运行时提示的部分文件沙箱强制范围也不构成OS隔离认证。

各角色使用实际支持的 `skill-filesystem.watch: false`，避免重复监视同一技能目录。外部更改技能或预设后，须按安全更新流程重新加载并在新会话验证，不假设运行中的角色自动采用新提示词。
