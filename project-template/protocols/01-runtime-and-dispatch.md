# 01 运行能力、角色树与派发

PTC指Programmatic Tool Calling，不是业务循环缩写。所有工具参数以当前DSH schema为准，不编造preset、cwd或peer字段。优先原生spawn并显式选择真实角色预设，创建后读回effective preset与有效工具集合；Team入口若不支持preset，不把它当专业角色派发。

队长直接管理建模负责人、证据数据、编程、独立验证、论文负责人和审阅老师。建模负责人可派三位独立建模手；论文负责人可派写作、图表、排版。编程默认两实例：solver负责核心模型求解，pipeline_and_experiments负责数据/实验管线；依文件范围和任务依赖调整，不强制常驻。存在多模块集成任务时可增加mcm-code-lead；其programmer在深度2，主管只整合自己获权的文件。无主管时programmer直接归队长。独立verifier不隶属代码作者。叶子角色不继续委派。

## 容量为独立验收项

config/runtime.json的7常态+1应急是新项目规划默认值，不是运行时事实。配置改成15+1不能证明运行时支持16。已审计SDK的maxActiveSubagents是每个共享根激活池的限额，不是整个Desktop的全局上限，也不是Team成员限制。同根下的主管和后代共享该池，等待、闲置、closing仍驻留的孩子均占槽。按项目预算和该实际池的已核限额取较小者，保留应急位；例如项目15+1而实际池限额8时按7+1使用。

v0.2.2候选管理者通过 `mcm_root_pool_capture({})` 只读实际注入运行时，获得 `allocation_scope:"root-activation-pool"` 的快照或明确unknown。捕获绑定实际调用Agent、根、服务、管理器、池和固定来源，不创建／恢复／中断孩子，不预留槽，不写文件。工具缺失、来源不支持、预留尚未发布或对账不全时保持queued，不能猜测active=0。持久会话状态或completed标签不等于实际预留已释放。

每位管理者须捕获自己的证据，不能复用队长捕获。若任务已分配独占allowed_write_paths，管理者可将snapshot原样保存到其授权目录，例如 `tasks/PAPER-01/runtime-pool.json`，随后通过 `mcm_dispatch_preflight` 的 `snapshot_path` 引用；无需往返队长代写这一分区文件。全局config及.mcm登记仍由队长单写。没有自有可写目录时才由父级转交队长保存；不能为图方便扩大权限。默认捕获和一次许可均最多60秒，转交后过期就重新捕获。`config/runtime.json.runtime_snapshot` 仍可作为队长维护的默认路径，不能由主管擅改。

`mcm.py runtime --snapshot runtime-snapshot.json` 对新格式只做有界结构、时间和数量对账，给出advisory_*预算估算。CLI不持有原生进程内捕获账本，因此始终返回native_validation_required=true、capacity_known=false、admit_one_task=false，不能签发许可。旧host格式只保留历史离线兼容，新版原生预检不接受它作为实际准入。真正派发须由同一管理者在已加载候选的进程调用mcm_dispatch_preflight，验证捕获当前性并立即以相同参数调用subagent；重启、实例／池／来源变化、过期、暂停或满额均须重新核对或排队。首次实际创建形成池后，下一次派发也必须重新捕获。

队长分配主管的是整树预算；等待主管也占位。正常不动应急槽；容量不足维持queued。中断一轮不等于已释放，确认真实终态后再复用槽位。

## 消息与上下文

原生父子消息、同一Team内消息和跨Team是不同能力。只按实际schema及身份关系使用；跨分支由共同父层转发简短编号、路径、版本和问题，技术正文落盘，不搬完整历史。不在共享文件无限轮询模拟聊天室。Codex仅在检查点做技术总监，原队长唯一调度并维护全局登记。

派发前生成 `python scripts/mcm.py context-pack TASK_ID`，父层读该包的ok、ready_to_start、pause和omitted_counts；错误、暂停、过期输入不能放行。收到交接后实际读回产物及SHA，不能因“工具返回成功”直接登记通过。长任务按输入/验收拆分，阶段交接后可新建短上下文实例，不在长会话里持续累积所有日志。

普通执行依赖必须 approved；独立复验用协议02的显式 review 关系核作者已交付的固定 refs 和交接 SHA。preflight、原生执行前及工具体阶段都会重核作者状态、交付、上游字节和记录指纹；中途变化须重新检查。相对任务 project_root 从已知原始项目根解析，原生 subagent.cwd 仍须是该根的绝对路径。review 就绪不替代容量核验：无同一实际管理者的新鲜进程内捕获仍 queued，禁止以合成测试快照、配置限额或一次 spawn 充当探针。

本协议属于v0.2.2候选的新项目模板，不证明当前稳定安装v0.2.1已加载新工具或通过原生验收。rehearsal-v2内协议是冻结历史夹具，保留原意，不以其旧Host格式证明新运行时通过；新项目使用当前project-template。源码同步不改变已有演练、暂停状态或人工关口。

用户暂停优先：停止新派发和主动整改，保留已有成果与真实状态；仅做仍被授权的只读核查。用户真实恢复后重新核容量、所有权和输入，旧grant不能延续至已回收窗口。
