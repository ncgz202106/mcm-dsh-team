# 01 运行能力、角色树与派发

PTC指Programmatic Tool Calling，不是业务循环缩写。所有工具参数以当前DSH schema为准，不编造preset、cwd或peer字段。优先原生spawn并显式选择真实角色预设，创建后读回effective preset与有效工具集合；Team入口若不支持preset，不把它当专业角色派发。

队长直接管理建模负责人、证据数据、编程、独立验证、论文负责人和审阅老师。建模负责人可派三位独立建模手；论文负责人可派写作、图表、排版。编程默认两实例：solver负责核心模型求解，pipeline_and_experiments负责数据/实验管线；依文件范围和任务依赖调整，不强制常驻。存在多模块集成任务时可增加mcm-code-lead；其programmer在深度2，主管只整合自己获权的文件。无主管时programmer直接归队长。独立verifier不隶属代码作者。叶子角色不继续委派。

## 容量为独立验收项

config/runtime.json的7常态+1应急是新项目规划默认值，不是Host事实。配置改成15+1不能证明Host支持16。运行时分别记录Host总名额、Team成员限制、活跃后代及等待主管；不把Team的8成员限制当Host限制。按项目预算和已验证Host容量的较小者派发，并在有效总量内保留应急位，例如项目15+1而Host仅8时按7+1使用；未核Host时本地CLI不准入新任务。

`mcm.py runtime --snapshot runtime-snapshot.json` 接收规范化记录，另需 `host_capacity:{verified:true,max_active_descendants:8或16,evidence_ref:实际证据}`、`allocation_scope:"host"`以及工具实取的带时区`captured_at`。默认快照最多60秒，可通过capacity_snapshot_max_age_seconds调整；缺时间、过期或明显未来的旧快照仍可显示计数，但不准入新任务。evidence_ref是协作证据索引，不是权限认证；必须来自真实Host检查。records中的running/waiting/starting/paused均占用，completed/cancelled/failed才释放。root是否排除必须与规范化Host证据的计数定义相同；本工具采用后代口径。派发前重新核对。

队长分配主管的是整树预算；等待主管也占位。正常不动应急槽；容量不足维持queued。中断一轮不等于已释放，确认真实终态后再复用槽位。

## 消息与上下文

原生父子消息、同一Team内消息和跨Team是不同能力。只按实际schema及身份关系使用；跨分支由共同父层转发简短编号、路径、版本和问题，技术正文落盘，不搬完整历史。不在共享文件无限轮询模拟聊天室。Codex仅在检查点做技术总监，原队长唯一调度并维护全局登记。

派发前生成 `python scripts/mcm.py context-pack TASK_ID`，父层读该包的ok、ready_to_start、pause和omitted_counts；错误、暂停、过期输入不能放行。收到交接后实际读回产物及SHA，不能因“工具返回成功”直接登记通过。长任务按输入/验收拆分，阶段交接后可新建短上下文实例，不在长会话里持续累积所有日志。

普通执行依赖必须 approved；独立复验用协议02的显式 review 关系核作者已交付的固定 refs 和交接 SHA。preflight、原生执行前及工具体阶段都会重核作者状态、交付、上游字节和记录指纹；中途变化须重新检查。相对任务 project_root 从已知原始项目根解析，原生 subagent.cwd 仍须是该根的绝对路径。review 就绪不替代容量核验：无真实新鲜 Host 快照仍 queued，禁止以合成测试快照、配置限额或一次 spawn 充当探针。

用户暂停优先：停止新派发和主动整改，保留已有成果与真实状态；仅做仍被授权的只读核查。用户真实恢复后重新核容量、所有权和输入，旧grant不能延续至已回收窗口。
