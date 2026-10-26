"""Rebuild the three editable SVG diagrams (Python standard library only)."""
from pathlib import Path
from xml.sax.saxutils import escape
import json

OUT = Path(__file__).resolve().parent
BLUE, TEAL, PURPLE, ORANGE, RED = '#2563eb', '#0f766e', '#7c3aed', '#b45309', '#b91c1c'
PALETTE = {BLUE: '#eff6ff', TEAL: '#f0fdfa', PURPLE: '#faf5ff', ORANGE: '#fffbeb', RED: '#fef2f2'}

class Drawing:
    def __init__(self, title, subtitle, width=1920, height=1400):
        self.width, self.height = width, height
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" data-generator="mcm-team-diagrams" data-quality-profile="showcase">',
            '<title>'+escape(title)+'</title>',
            '<style>text{font-family:"Microsoft YaHei","Noto Sans CJK SC",Arial,sans-serif} .muted{fill:#475569}</style>',
            '<defs>'+''.join(f'<marker id="a{i}" markerWidth="9" markerHeight="7" refX="8" refY="3.5" orient="auto"><path d="M0 0 L9 3.5 L0 7 Z" fill="{c}"/></marker>' for i,c in enumerate([BLUE,TEAL,PURPLE,ORANGE,RED]))+'</defs>',
            f'<rect width="{width}" height="{height}" fill="#ffffff" data-graph-role="background"/>']
        self.nodes, self.edges = [], []
        self.text(60, 59, title, 37, bold=True)
        self.text(60, 103, subtitle, 22, color='#475569')
    def text(self,x,y,value,size=23,bold=False,color=None):
        attrs=f'font-size="{size}" fill="{color or "#172554"}"'+(' font-weight="700"' if bold else '')
        self.parts.append(f'<text x="{x}" y="{y}" {attrs}>{escape(value)}</text>')
    def card(self, ident, x,y,w,h,title,lines=(),color=BLUE,dark=False):
        fill = color if dark else PALETTE[color]
        self.parts.append(f'<rect id="n-{ident}" data-graph-role="node" data-node-id="{ident}" data-graph-bounds="{x} {y} {x+w} {y+h}" x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" stroke="{color}" stroke-width="2"/>')
        self.parts.append(f'<rect x="{x}" y="{y+15}" width="5" height="{h-30}" rx="2" fill="{color}" data-graph-role="decoration"/>')
        self.text(x+24,y+39,title,26,True,'#ffffff' if dark else color)
        for i,line in enumerate(lines):
            self.text(x+24,y+76+i*33,line,22,color='#ffffff' if dark else '#334155')
        self.nodes.append({'id':ident,'x':x,'y':y,'width':w,'height':h,'title':title,'lines':list(lines)})
    def edge(self,source,target,points,color=BLUE):
        ident=f'{source}-{target}'
        idx=[BLUE,TEAL,PURPLE,ORANGE,RED].index(color)
        d='M '+' L '.join(f'{x} {y}' for x,y in points)
        self.parts.append(f'<path id="e-{ident}" data-edge-id="{ident}" data-graph-role="edge" data-source="{source}" data-target="{target}" d="{d}" stroke="{color}" stroke-width="2.5" fill="none" marker-end="url(#a{idx})"/>')
        self.edges.append({'id':ident,'source':source,'target':target,'points':points,'color':color})
    def band(self,ident,y,title,lines,color=TEAL,h=110):
        self.card(ident,60,y,1800,h,title,lines,color)
    def save(self,name):
        self.text(60,self.height-25,'MCM A/B/C  |  PTC = Programmatic Tool Calling  |  v0.2.0  ·  2026-10-26',18,color='#64748b')
        (OUT/(name+'.svg')).write_text('\n'.join(self.parts+['</svg>']),encoding='utf-8')
        (OUT/(name+'.json')).write_text(json.dumps({'title':name,'width':self.width,'height':self.height,'nodes':self.nodes,'edges':self.edges},ensure_ascii=False,indent=2),encoding='utf-8')

def overview():
    d=Drawing('MCM 多 Agent：12 类角色与检查点协作','独立建模 · 两名编程默认分工 · 早期图表规划 · 专项 Skill 按需路由',height=1880)
    d.card('codex',60,150,350,110,'Codex 技术总监',['模型 / 结果 / 论文检查点'],ORANGE)
    d.card('user',510,150,510,110,'参赛队：H0–H3 决策',['确认科学路线、结论与最终稿'],BLUE)
    d.card('external',1140,150,660,110,'联合模式为可选增强',['编号工作包与真实回执；作者回避自审'],TEAL)
    d.edge('user','codex',[(510,205),(410,205)],ORANGE)
    d.card('captain',60,330,350,1260,'DSH 执行队长',[
        'mcm-captain · 深度 0','', '唯一内部派发与全局登记','分配子树配额与写入范围','跨分支转发短任务通知','组织修复与非作者复验','维护固定版本和上下文包','', '启动后核实真实角色','原生 spawn 指定 preset','不能用成员名代替绑定','', '容量 = 配置与 Host 核实','预留 1 个应急名额','等待主管仍占名额','', 'H0 题目与交付要求','H1 主模型与关键假设','H2 结果、模型与验证代次','H3 固定最终 PDF','', '用户暂停优先','旧会话不自动获得新预设'],BLUE,True)
    d.edge('codex','captain',[(235,260),(235,330)],ORANGE)
    roles=[('model',330,'建模总负责人',['统一假设、符号、公式与接口'],BLUE),
        ('evidence',510,'证据与数据负责人',['检索、全文、参数依据与引用核验'],TEAL),
        ('code',690,'编程分支 / 可选主管',['无主管时队长直接派两个编程实例','主管仅在持续集成任务需要时启用'],BLUE),
        ('verify',900,'独立验证与复现',['边界、收敛、复跑与同代证据'],TEAL),
        ('paper',1130,'论文负责人',['用户指定框架；题问—主张—图表'],PURPLE),
        ('review',1410,'AI 审阅老师',['科学、表达与实际 PDF 独立审查'],ORANGE)]
    for ident,y,title,lines,c in roles:
        d.card(ident,510,y,510,140 if ident=='code' else 120,title,lines,c)
        d.edge('captain',ident,[(410,y+60),(510,y+60)])
    groups=[('model',330,[(330,'建模手 1：基线方案','先独立思考，尽快覆盖主要题问'),(460,'建模手 2：替代方案','比较模型机制、可解性和适用范围'),(590,'建模手 3：反证与假设','检验边界、结构与解释是否成立')],BLUE),
        ('code',690,[(740,'P1：核心求解','模型接口、算法实现、基线与数值结果'),(870,'P2：实验与结果导出','对照、灵敏性、批量运行及机器可读结果'),(1000,'P3：工程支持（按需）','复现、构建与隔离设施；单一文件负责人')],BLUE),
        ('paper',1130,[(1160,'论文写作子 Agent','按分配章节交稿，正式结果绑定有效版本'),(1290,'科研图表子 Agent','nature-figure / 矢量示意；数据与视觉双检'),(1420,'LaTeX 与 PDF 排版','原生公式、统一图注、实际尺寸逐页检查')],PURPLE)]
    for parent,py,children,c in groups:
        for i,(y,title,sub) in enumerate(children):
            ident=f'{parent}-child-{i+1}'
            d.card(ident,1140,y,660,90,title,[sub],c)
            sy=py+30+i*30
            d.edge(parent,ident,[(1020,sy),(1140,y+45)],c)
    d.band('rulemodule',1640,'专项技能与论文视觉约定',['排除全流程总控自动接管；示意图默认 1–2 张；定量图按证据配置；最终文字 12pt。'],TEAL,100)
    d.text(60,1795,'蓝 / 紫 = DSH 内部分支；橙 = Codex 检查点。叶子不再派生，最大本地深度为 2。',21,color='#475569')
    d.save('01-role-architecture')

def communication():
    d=Drawing('DSH 实际执行：消息路由与成果依赖','默认原生 spawn 指定专业预设；跨分支经队长转发版本化成果',height=1280)
    d.text(60,171,'01  控制与通知：只传任务号、成果位置、版本、状态和问题摘要',27,True)
    xs=[60,540,1020,1500]
    labels=[('worker','建模手','子 Agent → 直接父级'),('lead','建模负责人','父级汇总问题'),('captain','队长 / 共同父级','跨分支路由'),('programmer','编程手','读取指定版本并响应')]
    for x,(ident,title,sub) in zip(xs,labels):d.card(ident,x,220,360,130,title,[sub],BLUE)
    for i in range(3):d.edge(labels[i][0],labels[i+1][0],[(xs[i]+360,285),(xs[i+1],285)])
    d.band('routingrule',400,'任务交接与检查点',['原生子树使用父子消息；Codex 交编号工作包给队长。收到、读取、执行、验收分别留证。'],ORANGE,105)
    d.text(60,575,'02  文件依赖：读取共享成果，每项成果由唯一负责人写入',27,True)
    items=[('source','来源与数据',['出处、单位、清洗']),('contract','模型契约',['假设、公式、接口']),('run','运行与结果',['配置、种子、摘要']),('figure','正式图表',['数据核对、图注']),('manuscript','英文论文',['核心数字统一引用'])]
    for i,(ident,title,lines) in enumerate(items):
        x=60+i*370;d.card(ident,x,625,320,140,title,lines,TEAL)
        if i:d.edge(items[i-1][0],ident,[(x-50,695),(x,695)],TEAL)
    d.band('invalidate',820,'上游变化 → 递归失效 → 重跑、复核、重新批准',['数据或公式变化后，旧结果、图表、摘要数字不能继续作为最终证据；主文件只由论文负责人整合。'],RED,105)
    d.card('budget',60,980,560,160,'容量与原生派发门禁',['新鲜容量与任务证据 → 一次许可','原生 spawn 受检；暂停或未知即拒绝'],BLUE)
    d.card('archive',680,980,560,160,'AI 可见证据归档',['根会话 + 全部本地子会话','模型、可见输入输出、用途与核验'],PURPLE)
    d.card('check',1300,980,560,160,'固定版本审阅',['作者修复 → 原审阅者复验','缺失记录和未核验内容显式保留'],ORANGE)
    d.text(60,1200,'图例：蓝线 = 父子控制消息；绿线 = 版本化成果依赖。下排为执行约束。',21,color='#475569')
    d.save('02-runtime-communication')

def workflow():
    d=Drawing('竞赛工作循环：从选题到可提交论文','检索、验证与写作滚动推进；审阅反馈返回有明确责任人的任务',height=1430)
    stages=[('start','01  启动与选题',['拆解每问与输出','检查数据条件','建立英文论文骨架','H0：确认题目与题意'],BLUE),('model','02  候选与证据',['三个建模任务先独立','比较数据、计算与解释性','小实验检验可行性','H1：确认路线与假设'],BLUE),('solve','03  求解与验证',['先跑通完整基线','对照、敏感性与改进','验证者独立复现','保存真实结果与配置'],TEAL),('write','04  论文与整合',['方法提前、结果滚动写','图表只消费核验结果','摘要最后定稿','H2：确认结论与边界'],PURPLE),('deliver','05  冻结与交付',['整改、复验、PDF 逐页检查','核对页数、匿名与披露','归档源码和完整快照','H3：确认最终稿'],ORANGE)]
    for i,(ident,title,lines,c) in enumerate(stages):
        x=60+i*370;d.card(ident,x,210,320,270,title,lines,c)
        if i:d.edge(stages[i-1][0],ident,[(x-50,345),(x,345)])
    d.band('early',550,'贯穿全程：用户论文框架、图表证据清单、专项技能与独立审阅',['方法可提前写；核心结果用真实运行；定量图核数据与视觉；模型、结果、论文三个 Codex 检查点。'],TEAL,110)
    d.band('reviewcycle',710,'整改闭环：冻结版本 → 有证据的问题 → 队长派发 → 作者修复 → 原审阅者复验',['阻断 / 重要 / 建议三级；每个检查点默认最多三轮集中整改；争议可提交反证并由队长组织裁决。'],ORANGE,110)
    d.card('model-freeze',60,890,560,160,'停止修改前 18 小时',['冻结模型结构','重大路线变更需人工决策'],BLUE)
    d.card('result-freeze',680,890,560,160,'停止修改前 10 小时',['冻结核心结果','修复必须同步结果、图表与论文'],TEAL)
    d.card('paper-freeze',1300,890,560,160,'停止修改前 2 小时',['冻结论文与最终 PDF','官方停止时间后不再修改解答'],PURPLE)
    d.band('fallback',1100,'持续保留最近完整版本；失败时恢复已验证快照',['正式提交：按当届规则生成单个 PDF。内部另存代码、数据、图表源、LaTeX 源码、复现与审阅记录。'],BLUE,110)
    d.text(60,1290,'内部质量评分用于定位问题；O 奖属于竞赛评审结果，不以分数阈值或获奖概率承诺。',23,color='#475569')
    d.save('03-workflow-review')

if __name__=='__main__':
    overview();communication();workflow()
    print('Generated three editable SVGs and coordinate JSON sources.')
