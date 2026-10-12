# カブロボ (kaburobo)

株式の自動売買ロボット。いまはバックテストと紙上取引（ペーパートレード）まで。

## 構成

| ファイル | 役割 |
|---|---|
| `kaburobo/data.py` | 株価取得（CSV / Yahoo Finance / サンプル生成） |
| `kaburobo/indicators.py` | テクニカル指標（SMA, EMA, RSI） |
| `kaburobo/strategies.py` | 売買戦略（移動平均クロス, RSI 逆張り） |
| `kaburobo/backtest.py` | バックテスト（翌日始値約定・100 株単位・手数料/スリッページ） |
| `kaburobo/broker.py` | 発注先の抽象化と紙上取引ブローカー |
| `kaburobo/bot.py` | ロボット本体（1 回分の売買判断と発注） |

## 使い方

```bash
pip install -e '.[yahoo,dev]'

# サンプルデータでバックテスト
python -m kaburobo backtest --sample --strategy sma

# トヨタ (7203.T) で RSI 戦略をバックテスト
python -m kaburobo backtest --symbol 7203.T --strategy rsi --commission 0.001

# 紙上取引: 引け後に 1 日 1 回実行すると paper_state.json に損益が溜まっていく
python -m kaburobo run --symbol 7203.T --strategy sma

pytest
```

## 戦略の追加

`Strategy` を継承して `target_position()`（各日終値時点で 1=保有 / 0=ノーポジ）を実装し、
`STRATEGIES` に登録する。シグナルは当日終値で確定し翌営業日始値で約定する前提なので、
当日以降のデータを使わないこと（`test_no_lookahead` 参照）。

## 今後

- 複数銘柄・ポートフォリオ対応
- 損切り / 利確ルール
- 実ブローカー接続（`Broker` を継承して実装）
