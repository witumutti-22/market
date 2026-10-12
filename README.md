# カブロボ (kaburobo)

株式の自動売買ロボット。いまはバックテストと紙上取引（ペーパートレード）まで。

## 構成

| ファイル | 役割 |
|---|---|
| `kaburobo/data.py` | 株価取得（CSV / Yahoo Finance / サンプル生成） |
| `kaburobo/indicators.py` | テクニカル指標（SMA, EMA, RSI） |
| `kaburobo/strategies.py` | 売買戦略（移動平均クロス, RSI 逆張り） |
| `kaburobo/risk.py` | 損切り・利確・トレーリングストップ |
| `kaburobo/backtest.py` | バックテスト（複数銘柄・翌日始値約定・100 株単位・手数料/スリッページ） |
| `kaburobo/broker.py` | 発注先の抽象化と紙上取引ブローカー |
| `kaburobo/bot.py` | ロボット本体（全銘柄の売買判断と発注・状態保存） |

## 使い方

```bash
pip install -e '.[yahoo,dev]'

# サンプルデータ 5 銘柄でバックテスト（同時保有は最大 3 銘柄）
python -m kaburobo backtest --sample 5 --max-positions 3

# トヨタ・ソニー・ソフトバンクG に損切り -5% / 利確 +15% を付けて
python -m kaburobo backtest --symbol 7203.T 6758.T 9984.T \
    --stop-loss 0.05 --take-profit 0.15 --commission 0.001

# 紙上取引: 引け後に 1 日 1 回実行すると paper_state.json に損益が溜まっていく
python -m kaburobo run --symbol 7203.T 6758.T 9984.T --trailing-stop 0.08

pytest
```

### 複数銘柄の資金配分

資金を `max-positions`（既定は銘柄数）で均等に割った枠で 1 銘柄ずつ買う。
枠は前日の総資産から計算するので、増えた利益も次の買いに回る。
買いシグナルが同時に出て枠が足りないときは、指定した銘柄順に優先する。

### 損切り・利確

| オプション | 意味 |
|---|---|
| `--stop-loss 0.05` | 取得価格から -5% で損切り |
| `--take-profit 0.15` | 取得価格から +15% で利確 |
| `--trailing-stop 0.08` | 保有中の最高値から -8% で手仕舞い |

- バックテストでは日中の高値・安値で判定し、逆指値の価格で約定する（窓を開けて飛び越えたら始値）。
  同じ日に損切りと利確の両方に届いた場合は、損切りを優先する（保守的）。
- 紙上取引 (`run`) では終値で判定し、終値で約定したとみなす。
- ルールで手仕舞った銘柄は、戦略の買いシグナルが一度消えるまで買い直さない。

## 戦略の追加

`Strategy` を継承して `target_position()`（各日終値時点で 1=保有 / 0=ノーポジ）を実装し、
`STRATEGIES` に登録する。シグナルは当日終値で確定し翌営業日始値で約定する前提なので、
当日以降のデータを使わないこと（`test_no_lookahead` 参照）。

## 今後

- 買いシグナルが重なったときの優先順位付け（勢い・出来高など）
- 実ブローカー接続（`Broker` を継承して実装）
