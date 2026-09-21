# Three at the Table · Laya-MLX Dou Dizhu

[中文](README.md) | **English**

Play classic three-player Dou Dizhu against two local AI players on an Apple Silicon Mac. One Laya instance serves both AI seats in turn. Each decision receives only that player's own cards and public information. Python owns the rules and game state; MLX performs real local inference; the browser provides the interface.

**The model has not been trained specifically for Dou Dizhu.** The pipeline is legal action enumeration → strategic filtering and hidden-hand sampling → Laya selection → authoritative validation. Model probabilities and heuristic scores are not calibrated winning probabilities. Rule and simulation capabilities must not be attributed to the model itself.

## Features

- One human and two AI seats; 54-card deals, 1/2/3-point bidding, redeals when everyone passes, public landlord bottom cards.
- All supported classic combinations, two-pass trick reset, cooperative farmer victory, bombs, spring and reverse-spring scoring.
- Select cards, request a hint, pass, restart, review public plays, and reveal remaining hands after the round.
- Shared Laya weights with separate player observations; inference timing and explicit strategy-guard intervention.
- Responsive Chinese interface and keyboard-operable card buttons. No frontend build, CDN, paid API, or cloud inference.
- Local recreational scores only. No financial transactions.

## Requirements

| Component | Requirement |
| --- | --- |
| Hardware | Apple Silicon Mac with an accessible Metal GPU |
| macOS | Upstream declares macOS 14+; actual compatibility depends on the MLX wheel |
| Python | Native arm64 Python 3.11+ in a virtual environment |
| Network | Required for dependency/model installation; offline afterward |
| Disk | About 0.65 GB of FP16 weights, plus dependencies and caches |

Tested during development on M4 / 32 GB, macOS 27.0, Python 3.14.7. This launch path does not support Intel Mac, Windows, or Linux. The server binds only to localhost, not the LAN.

## Install

### 1. Clone

```bash
git clone git@github.com:smile-magic/laya-mlx-ddz.git
cd laya-mlx-ddz
```

HTTPS also works:

```bash
git clone https://github.com/smile-magic/laya-mlx-ddz.git
cd laya-mlx-ddz
```

### 2. Create an environment

```bash
uname -m
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

Expect `arm64` and Python 3.11 or newer. If the system Python is older, use an installed recent version, for example `python3.12 -m venv .venv`. Avoid an x86_64 Python running under Rosetta.

Dependencies pin `laya-mlx==0.1.0`, which installs MLX, NumPy, the tokenizer, and Hugging Face Hub. PyTorch and Node.js are not required to play.

### 3. Download the model once

```bash
HF_HOME="$PWD/.hf-cache" .venv/bin/hf download \
  aac6fef/laya-multilingual-mlx \
  --local-dir models/laya
```

Keep the complete directory, including model configuration and tokenizer files. Weights and caches are excluded from Git. If a SOCKS proxy dependency is missing, run `.venv/bin/python -m pip install 'httpx[socks]'` and retry.

### 4. Launch

```bash
./run.sh
```

Alternatively, double-click `启动斗地主.command` in Finder. After GPU warm-up, the browser opens the game. The default first tries **http://127.0.0.1:8770**; if occupied, it automatically binds an available port and prints and opens the actual address. Keep the terminal open; press **Ctrl+C** to stop the server and release the model. Closing the browser alone does not stop Python. In-memory rounds and scores disappear when the server stops.

Options:

```bash
# Reuse existing model weights
./run.sh --model /absolute/path/to/laya-multilingual-mlx

# Custom port, no automatic browser opening
./run.sh --port 8771 --no-browser

# More hidden-hand samples (1–32): more work, not a guarantee of better play
./run.sh --samples 12

# Reuse an existing Python environment
LAYA_PYTHON=/absolute/path/to/.venv/bin/python ./run.sh --model /absolute/path/to/model
```

## Play

The first bidder is random; subsequent rounds rotate the first bidder. Bid zero (pass), or 1/2/3 above the current bid. A bid of 3 immediately determines the landlord. All-pass rounds are redealt without scoring. The landlord receives the three public bottom cards and leads.

Click cards to select a combination, then press `出牌` (Play). Use `不出` (Pass) when following; a new trick cannot start with a pass. `提示` (Hint) selects a suggested action without playing it. Hints use rules and sampling, not a Laya call. `取消选择` clears the selection.

Either farmer going out wins for both farmers. Scores are cumulative within the current table. `再来一局` starts the next round; restarting an unfinished round asks for confirmation and discards that round's settlement.

A refresh resumes the same tab's in-memory table via a random table identifier in session storage. No opponent hands are stored in the browser. Tables idle for two hours may be cleared when another table is created. A stopped/restarted server cannot recover old games. A failed or busy model preserves the turn and offers retry; there is no silent rule-only replacement for failed inference.

## Exact rule variant

Regional variants differ. This implementation explicitly uses:

- Straights of at least five cards, consecutive pairs of at least three ranks, and airplanes of at least two consecutive triples. Sequence bodies allow 3 through A only, never 2 or jokers.
- Airplane single wings may split pairs, triples, or quads of non-body ranks. Body ranks cannot also be wings. Pair wings must use distinct non-body ranks.
- Four-with-two singles may carry a pair. Four-with-two pairs requires two distinct pair ranks. These are ordinary combinations, not bombs.
- Airplane single wings and four-with-two singles cannot carry both jokers together. The two jokers form the rocket.
- Ambiguous hands prefer a bare airplane; other airplane ambiguities use the highest legal body.
- Ordinary responses must match combination type and length, with a higher body rank. Bombs beat ordinary combinations; the rocket beats everything. Suits do not affect comparison.
- Two consecutive passes return the lead to the last player who played cards.
- The final bid is the base score. Each played bomb/rocket doubles it. A landlord win with neither farmer ever playing is a spring. A farmer win after only one landlord play is a reverse spring. Either doubles the multiplier once more.
- The landlord gains/loses twice each farmer's amount. Total score change is zero. There is no extra bottom-card bonus or doubling phase.

See [rule research and primary sources](docs/RULES_RESEARCH.md). This is a recreational implementation of an explicit variant, not a certified tournament platform.

## AI architecture and limits

1. Enumerate every legal rank-multiset action; add pass only when responding.
2. Score remaining combinations, splitting costs, high-card/bomb retention, teammate control, and opponents with one or two cards left.
3. Shortlist at most six actions, preserving distinct combination families and representative high responses, bombs, and passing. Shortlisting can still miss a better move.
4. Sample six hidden-hand assignments by default, using only own cards, public history, remaining counts, and unplayed public bottom-card constraints.
5. Simulate each candidate in the same sampled worlds for up to 54 plies using a simple heuristic opponent policy. Include immediate finishing risk. For ten or fewer remaining cards, compute the exact minimum self-only partition count—not a game-tree solution.
6. Always finish immediately when legal. Next prioritize an unbeatable bomb/rocket followed by a remaining hand that forms one legal final lead. Otherwise allow actions within 0.20 of the best combined score, with no higher immediate risk and no more than half a sample's weight of lower simulated return. Laya selects its highest-probability allowed candidate.
7. Validate the executed action again. Report a strategy intervention when the original model choice is replaced. Private prompts, sampled hands, and unplayed candidate details are never returned to the human opponent.

The simulation does not learn an opponent behavior model from voluntary passes. There is no minimax, MCTS, DouZero checkpoint, or game-specific training. Bidding uses a hand-strength ceiling and a real model choice. Shared weights do not mean shared private cards. The rocket counts as one combination. Splitting jokers or quads and spending bombs while already on lead incur control costs, reduced when an opponent has one or two cards left. On the landlord’s opening lead, preserve bombs when an ordinary move retains those controls; proven finishes are exceptions, and all-bomb hands are not forced to split. This does not mean always leading the smallest single.

Dealing uses the system random source and a 17/17/17/3 split, without strength screening or hidden balancing. Fair randomness permits uneven individual deals; bottom cards and strength-dependent bidding also affect the eventual landlord’s hand. See the [dealing audit](docs/DEAL_AUDIT.md), [strategy research](docs/STRATEGY_PRINCIPLES.md), [latest fix validation](docs/STRATEGY_FIX.md), and [original validation results](docs/VALIDATION.md) for evidence and limitations.

## Tests and reproducible evaluation

```bash
# Rules, game state, HTTP behavior, information isolation, tactical fixtures
python3 -B -m unittest discover -s tests -v

# Include real GPU decisions and actual tokenizer completeness
LAYA_TEST_MODEL="$PWD/models/laya" .venv/bin/python -B -m unittest discover -s tests -v

# Evaluate each seat on the same fixed deals against a heuristic baseline
.venv/bin/python -B tools/benchmark.py --model models/laya --seeds 20 --start-seed 2000

# Product configuration: two shared-model AI farmers vs a heuristic landlord
.venv/bin/python -B tools/benchmark.py --model models/laya --mode table --seeds 12 --start-seed 3000
```

HTTP tests start a temporary localhost server and shut it down on completion. Tests and benchmarks print results without saving games. Without `--model`, the benchmark selects the highest-scored strategy candidate and is **not** a Laya evaluation. The benchmark fixes the landlord and does not measure bidding skill.

## Layout

```text
ddz/rules.py       Card combinations, complete generation and comparisons
ddz/game.py        Deals, bidding, turns, settlement and player observations
ddz/strategy.py    Partitioning, sampling, guardrails and Laya integration
server.py          Local HTTP, sessions, version checks and serialized GPU calls
web/               Plain HTML/CSS/JavaScript UI
tests/             Rule, state, strategy, HTTP and optional GPU tests
tools/benchmark.py Reproducible evaluation without saved game data
docs/              Rule references and validation report
```

## Troubleshooting

- **No Metal device available:** run in a normal local macOS terminal, not a GPU-less container or remote Linux environment.
- **Port occupied:** the default launch automatically selects an available port; there is no need to terminate a system process. An explicit `--port` remains fixed and produces a clear error if occupied. Choose another port or omit the option. The server binds before loading the model; use the actual ready URL printed in the terminal.
- **Model not found:** download the entire checkpoint or pass `--model`. The runtime forces offline mode and never downloads weights automatically.
- **Disconnected/expired game:** ensure the server is running. Restarting the server clears all in-memory rounds.
- **Another table is using the model:** GPU calls are serialized; retry after that decision completes.

## Credits and license

- [mizorewww/laya-mlx](https://github.com/mizorewww/laya-mlx): MLX inference runtime and constrained-action design, Apache-2.0.
- [Laya multilingual MLX](https://huggingface.co/aac6fef/laya-multilingual-mlx): downloaded separately under the model publisher's license; weights are not distributed here.
- [DouZero](https://github.com/kwai/DouZero) and [RLCard](https://github.com/datamllab/rlcard): rule/research references. Their trained policies are not integrated, and equivalent playing strength is not claimed.

Repository source is licensed under [Apache-2.0](LICENSE).
