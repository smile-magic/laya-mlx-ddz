# 三人行 · Laya-MLX 斗地主

**中文** | [English](README.en.md)

在 Apple Silicon Mac 上，与两位本地 AI 玩经典三人斗地主。一个 Laya 模型实例轮流控制两个席位，每个 AI 只获取自己的手牌和公开信息。浏览器负责交互，Python 负责规则和策略，MLX 在本机 GPU 上进行真实推理。

**这不是经过斗地主专项训练的模型。** 本项目采用“完整合法动作 → 策略筛选与未知手牌采样 → Laya 选择 → 服务端校验”的组合方式。规则、采样和拆牌评分带来的能力不归因于模型；策略评分和模型选择概率都不等于真实胜率。

## 功能

- 你 + 两位 AI，三人 54 张牌；轮流叫 1/2/3 分、全不叫重发、地主底牌公开。
- 单张、对子、三张、三带一/二、顺子、连对、飞机及带牌、四带二、炸弹、王炸。
- 农民团队胜利、两次过牌恢复领出权、炸弹与春天/反春天结算、牌桌累计分数。
- 点选组合出牌、提示、取消选择、重新发牌、公开出牌记录、结束后亮出剩余牌。
- 共享一个真实 Laya 模型；手牌视角隔离；显示推理耗时和策略护栏介入。
- 响应式中文界面、键盘可操作的卡牌按钮；无前端构建步骤、CDN 或云端 API。
- 模型下载后离线运行。分数是本地娱乐记录，无金钱交易。

## 环境要求

| 项目 | 要求 |
| --- | --- |
| 电脑 | Apple Silicon Mac（M 系列），可访问 Metal GPU |
| 系统 | 上游声明 macOS 14+；实际取决于安装的 MLX wheel |
| Python | 3.11+，原生 arm64；建议独立虚拟环境 |
| 网络 | 首次安装依赖和下载模型时需要，之后离线 |
| 空间 | FP16 模型约 0.65 GB，另需 Python 依赖与缓存 |

本项目开发验证环境为 M4 / 32 GB、macOS 27.0、Python 3.14.7。Intel Mac、Windows 和 Linux 不支持此 Metal 启动路径。浏览器页面可适配手机尺寸，但服务只绑定本机，不开放局域网。

## 安装与启动

### 1. 克隆仓库

```bash
git clone git@github.com:smile-magic/laya-mlx-ddz.git
cd laya-mlx-ddz
```

也可以使用 HTTPS：

```bash
git clone https://github.com/smile-magic/laya-mlx-ddz.git
cd laya-mlx-ddz
```

### 2. 创建 Python 环境

```bash
uname -m
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

架构应为 `arm64`，Python 应为 3.11+。部分 Mac 系统 Python 仍为 3.9；请使用已安装的新版 Python 创建环境，例如 `python3.12 -m venv .venv`。不要使用 Rosetta 下的 x86_64 Python。

`requirements.txt` 固定 `laya-mlx==0.1.0`，其依赖包含 MLX、NumPy、Rust tokenizer 和 Hugging Face Hub。游戏无需 PyTorch、Node.js 或付费 API key。

### 3. 下载模型，只需一次

```bash
HF_HOME="$PWD/.hf-cache" .venv/bin/hf download \
  aac6fef/laya-multilingual-mlx \
  --local-dir models/laya
```

请保留整个模型目录，包括权重、配置和 tokenizer。模型与缓存已被 `.gitignore` 排除，不会提交 Git。若代理提示 SOCKS 依赖缺失，可安装 `.venv/bin/python -m pip install 'httpx[socks]'` 后重试。

### 4. 开始牌局

```bash
./run.sh
```

或在 Finder 双击 `启动斗地主.command`。首次加载会预热模型，终端显示“已就绪”后浏览器自动打开 **http://127.0.0.1:8770**。

保留启动终端。退出时按 **Ctrl+C**；仅关闭浏览器不会释放 Python 服务和 GPU。每次服务停止，内存中的牌局和分数都会消失。

常用参数：

```bash
# 使用已有权重，避免重复下载
./run.sh --model /absolute/path/to/laya-multilingual-mlx

# 指定端口，不自动打开浏览器
./run.sh --port 8771 --no-browser

# 增加未知手牌样本（1–32），会增加计算开销；不保证棋力提升
./run.sh --samples 12

# 复用已有的 Python 环境
LAYA_PYTHON=/absolute/path/to/.venv/bin/python ./run.sh --model /absolute/path/to/model
```

## 怎么玩

1. 进入页面自动发牌。首局随机决定首叫席位，以后每局轮换。
2. 轮到你时选择“不叫”或高于当前叫分的 1/2/3 分；叫 3 分立即成为地主，全不叫重新发牌。
3. 地主取得三张公开底牌并先出。点击手牌选中组合，再点“出牌”；跟牌时可“不出”，领出时不能过牌。
4. “提示”依据同一可见信息策略选中建议牌，**不会自动替你出牌**。若建议过牌，页面会提示“不出”。它不调用 Laya，是规则与采样建议。
5. 任一农民出完，两位农民共同获胜；不是三人各自为战。牌局结束后显示计分与其他玩家剩余手牌。
6. “再来一局”保留本牌桌累计分数；进行中“重新发牌”需要确认并放弃该局结算。

页面刷新会恢复同一标签页的内存牌局；浏览器仅保存随机牌桌标识，不存储其他玩家手牌。关闭标签页后不保证恢复。牌局闲置超过两小时后，可能在创建新桌时清理。模型忙或失败时保留回合，点击“重试 / 同步牌局”即可继续；不会悄悄切换为规则 AI。

## 冻结的牌型与计分细节

斗地主有地区变体，本项目固定以下约定，界面“玩法说明”也有说明：

- 顺子至少 5 张、连对至少 3 对、飞机至少 2 组三张；连续主体只允许 3 到 A，不包含 2 或王。
- 飞机带单允许将非主体的对子、三张或四张拆成单翼；主体点数不能再次充当翅膀。飞机带对必须是不同点数的对子。
- 四带二单允许带一对；四带两对必须是两个不同点数的对子。四带二不是炸弹。
- 飞机单翼和四带二单都禁止同时带小王与大王；双王组成王炸。
- 有歧义的牌优先识别不带翼飞机；其他飞机按更大的合法主体确定比较点数。
- 同型同长度比较主体，纯炸弹压普通牌，王炸最大。花色不参与大小比较。
- 底分为最终叫分，每个实际打出的炸弹/王炸翻倍。地主赢且两名农民从未有效出牌为春天；农民赢且地主仅有效出牌一次为反春天，各再翻倍一次。
- 地主得失是每位农民的两倍，三家得失相加为零。不设额外底牌奖励或加倍阶段。

参见 [规则调研及一手来源](docs/RULES_RESEARCH.md)。本项目是明确规则变体的娱乐实现，不声明获得任何竞赛认证。

## AI 策略及其边界

1. 从当前手牌生成**全部合法点数组合**，严格按当前牌型过滤，跟牌时加入过牌。
2. 评估拆散对子/三张、剩余组合数、高牌和炸弹消耗、队友是否掌握牌权、对手最后 1/2 张等因素。
3. 保留最多 6 个候选，包含不同牌型、必要的高牌应手、过牌及炸弹代表。候选截取仍可能遗漏更好的动作。
4. 根据自己的手牌、已出牌、各家剩余数和公开底牌，采样默认 6 组未知手牌。不会读取真实对手手牌。
5. 在相同样本上对候选做最多 54 次行动的启发式模拟，结合对手短程出完风险评分。剩余不超过 10 张时精确计算**自行拆牌的最少手数**；这不是对抗搜索。
6. 直接出完是硬优先；其他局面只允许距最佳综合分不超过 0.20、即时风险不高于最佳候选、模拟收益差不超过半个样本权重的候选。Laya 接收紧凑的局面与候选描述，执行允许候选中模型概率最高的一项。
7. 服务端再次校验实际出牌。模型首选被策略层替换时显示“策略护栏介入”。候选详情属于玩家私有信息，不传给对手的浏览器。

采样未根据对手历次“主动不出”学习行为模型；模拟对手是简单启发式，未实现 minimax、MCTS、专项训练或 DouZero 模型。农民协作不等于共享手牌。叫分也只是手牌强度门槛约束下的模型选择。不要把少量回归胜率理解为专业牌力。

架构和验证记录见 [验证说明](docs/VALIDATION.md)。

## 测试与复现

```bash
# 规则、接口、信息隔离和策略固定局面；不需要模型
python3 -B -m unittest discover -s tests -v

# 加上真实 GPU 模型、叫分和输入完整性测试
LAYA_TEST_MODEL="$PWD/models/laya" .venv/bin/python -B -m unittest discover -s tests -v

# 固定牌局、三个角色分别与启发式基线对照
.venv/bin/python -B tools/benchmark.py --model models/laya --seeds 20 --start-seed 2000

# 实際产品组合：席位 1、2 共享 Laya，对阵席位 0 启发式
.venv/bin/python -B tools/benchmark.py --model models/laya --mode table --seeds 12 --start-seed 3000
```

HTTP 测试在随机本机端口启动临时服务，并在完成后停止。测试和 benchmark 只输出结果，不保存对局文件；固定局面属于回归源码。无模型时 benchmark 使用策略层最高分候选，**不代表 Laya 实测**。固定地主的 benchmark 不评估叫分能力。

## 文件结构

```text
ddz/rules.py       牌型、完整候选和比较规则
ddz/game.py        发牌、叫分、轮次、结算与独立玩家视图
ddz/strategy.py    拆牌、采样模拟、策略约束与 Laya 接口
server.py          本机 HTTP、牌桌会话、版本校验与串行 GPU 调用
web/               原生 HTML/CSS/JavaScript 界面
tests/             规则、牌局、策略、HTTP 与真实模型测试
tools/benchmark.py 不保存对局的固定牌局评测
docs/              规则来源和验证记录
```

## 常见问题

- **No Metal device available**：在正常 macOS 本机终端运行，不要在无 GPU 的沙箱、容器或远程 Linux 上启动。
- **端口被占用**：停止旧服务，或用 `--port 8771`。服务会先绑定端口再加载模型，避免重复占用 GPU。
- **找不到模型**：检查完整模型目录，或用 `--model` 指定。服务强制离线，不会自动下载。
- **连接中断 / 牌局过期**：确认终端服务仍在运行。服务重启后旧内存牌局无法恢复，重新开桌即可。
- **另一桌占用模型**：同一模型串行处理推理，页面会提供重试；不允许并发调用同一 GPU 实例。

## 来源与许可

- [mizorewww/laya-mlx](https://github.com/mizorewww/laya-mlx)：MLX 推理运行时及候选约束思路，Apache-2.0。
- [Laya multilingual MLX 权重](https://huggingface.co/aac6fef/laya-multilingual-mlx)：由用户单独下载，遵循模型发布页许可，不随本仓库分发。
- [DouZero](https://github.com/kwai/DouZero)、[RLCard](https://github.com/datamllab/rlcard)：规则与研究参考。本仓库没有集成其训练模型，不宣称达到其性能。

本仓库源代码采用 [Apache-2.0](LICENSE)。
