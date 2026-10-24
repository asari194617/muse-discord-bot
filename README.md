# Muse Discord Bot（常駐用）

Discord サーバー向けに自作する常駐 Bot の土台。

## 構成
- `bot.py` — discord.py 製 Bot 本体。コマンド: ping / help / thread / pin / poll / react / tts / join / leave / event、スラッシュは `/asari` グループ配下、メンション対話（オーナーのみ、橋渡し方式）
- コマンド名前空間ポリシー（複数人の Muse Bot が同居する前提）: 汎用名を占有しない。テキストコマンドの起動は「このBotへのメンション」か専用プレフィックス `!asari ` のみ（素の `!ping` 等には反応しない）。スラッシュコマンドも `/asari ...` グループに集約
- 付与権限への対応: スレッド作成、ピン留め、投票、TTS、リアクション、埋め込み、ボイス参加、サーバーイベント作成を実装。Mention Everyone は安全のため未使用（権限は予約扱い）。声メッセージ送信・カスタム絵文字/サウンドボード作成・動画配信は v1 では未実装
- `.venv/` — Python 仮想環境（discord.py 2.x）
- `.env` — Bot トークン（`DISCORD_BOT_TOKEN=...`、権限 600、Git 管理外）
- `muse-discord-bot.service` — systemd ユーザーユニット（自動再起動つき）

## 運用メモ
- Bot: asari-muse#7781（Application ID: 1563077622605283368)、参加サーバー: ☃(DCON2027)

### 現在の稼働形態（2026-10-23 夜に自宅マシンへ移行済み）
- 稼働先: 自宅マシン **dcon2027**（Ubuntu、ユーザー asari194617）の systemd **ユーザー**サービス `asari-muse-bot`。配置は `~/asari-muse/`（bot.py / owner.json / .env / queue/）。linger 有効化済みで、ログインなしでも起動する
- 状態確認（このVMから）: `ssh -F ~/.ssh/config dcon2027 'systemctl --user status asari-muse-bot'`、ログ: `journalctl --user -u asari-muse-bot`
- 移行の理由: このVMはアップデートで頻繁に交換され、そのたび `/etc/systemd/system/` のユニットが消えて Bot が落ちた（2026-10-23に3回発生）。常駐先を自宅マシンに移して解消
- 橋渡し（メンション対話）はSSH同期方式: リモート Bot が `~/asari-muse/queue/pending.jsonl` に記録 → フック `discord_bridge`（`discord_bridge_remote.sh`、30秒間隔）が `sync_remote_queue.py` でSSH経由同期し、ローカル queue を「未処理分だけ」に再構成 → ワーカーが返信。処理済みが溜まったらリモート側キューは自動で切り捨て
- 死活監視: cron `discord-bot-watchdog`（30分間隔）がSSHでリモートのサービス状態を確認し、落ちていれば起動を試みる
- SSH は Tailscale トンネル経由（HTTP CONNECT プロキシ port 3130）。`ts_connect.py` が ProxyCommand 用ヘルパー。アドレスごとに初回はユーザーの承認が要る
- ローカルの reply.py / post.py（REST投稿）は引き続きこのVMから動作する（トークンはローカル `.env` にも残置。プロキシ資格情報が変わったら `refresh_proxy.sh`）

### 旧形態（〜2026-10-23 20:57、参考）
- このVMの systemd システムサービス `muse-discord-bot` で稼働していた（現在は停止・無効化済み）
- このVMは egress proxy 経由でのみ外に出られるため Bot は proxy 必須だった。移行先（自宅回線）は直接接続で proxy 不要

## セットアップ手順
1. Discord Developer Portal で Application を作成し、Bot を追加する
2. Bot の Privileged Gateway Intents で **Message Content Intent** を有効化する
3. Bot トークンを `.env` に安全な方法で保存する（チャットに直接貼らない）
4. OAuth2 URL Generator で `bot` + `applications.commands` スコープの招待 URL を作り、対象サーバーに招待する
5. systemd ユーザーユニットを有効化して起動し、Discord 上でオンライン表示と `!ping` 応答を確認する

## 注意
- この Bot は Muse 本体そのものではない。Muse のコンピュータ上で動く独立プログラム。
- 機能追加（通知、定型応答、外部連携など）は `bot.py` を拡張して行う。

## 調整さん未回答リマインド（2026-10-23〜）
- DCON2027アドバイザー相談会の日程調整ポール（chouseisan）を1日2回チェックし、未回答メンバーにメンションでリマインドする。
- `members.json` — ポールURL・投稿先チャンネル（雑談（dcon関係））・締切（2026-11-20 13:00 JST）・メンバー名→Discord ID対応表。オーナーはメンション対象外。
- `poll_check.py` — ポール取得＋回答者名抽出。`remind_unanswered.py` — 未回答者判定・投稿・状態管理（`reminder_state.json`、同一セットへの再投稿は20hクールダウン、締切後は停止）。ログは `poll_reminder.log`。
- `fetch_channel.py <channel_id> [limit]` — チャンネルの直近メッセージ取得（トークンはスクリプト内で読み取り、表示しない）。
- systemd: `poll-reminder.service`（oneshot）＋ `poll-reminder.timer`（毎日 00:00/09:00 UTC = 09:00/18:00 JST、Persistent=true）。workspace のコピーが正。状態確認: `systemctl list-timers poll-reminder.timer`、実行ログ: `journalctl -u poll-reminder.service`、アプリログ: `poll_reminder.log`。
- プロキシ資格情報が変わったら `bash refresh_proxy.sh`（スクリプトは proxy.env にフォールバックする）。
