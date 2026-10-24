# Telegram: a bot and a test channel for publishing

Takes about 10 minutes. You need Telegram (phone or desktop) and a terminal.

## 1. Create the bot

1. In Telegram open [@BotFather](https://t.me/BotFather) (the official one, with the blue check mark).
2. Send `/newbot`.
3. Enter the bot's **name**, which people see, e.g. `SportIntel Publisher`.
4. Enter a **username**: Latin letters, must end with `bot`, e.g. `sportintel_publisher_bot`.
5. BotFather sends a **token** like `1234567890:AAH...`. This is the bot's password:
   - do not post it in chats or commit it to git;
   - if the token leaks, go to @BotFather: `/revoke` → pick the bot → get a new one.

## 2. Create a test channel

1. Telegram → "New Channel" → a name, e.g. `SportIntel Test`.
2. Type: **Private** (for tests).
3. You do not need to add subscribers.

## 3. Make the bot a channel administrator

1. Open the channel → "Manage Channel" (pencil icon) → "Administrators" → "Add Admin".
2. Search for the bot's username (`@sportintel_publisher_bot`) and select it.
3. Leave only the **"Post Messages"** permission on; nothing else is needed.
4. Save.

## 4. Find the channel's chat_id

1. Post any message in the channel, e.g. `test`.
2. In a terminal (use your token):

   ```bash
   curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | python3 -m json.tool | grep -A3 '"chat"'
   ```

3. Find `"id": -100xxxxxxxxxx` next to `"type": "channel"`. That is the **chat_id** (negative, starts with `-100`).
   If the response is empty (`"result": []`), post one more message in the channel and repeat the request.

## 5. Check that the bot can post to the channel

```bash
curl -s "https://api.telegram.org/bot<TOKEN>/sendMessage" \
  -d chat_id=<CHAT_ID> -d parse_mode=HTML -d text="<b>SportIntel</b>: publishing test"
```

`"ok":true` and a message in the channel mean you are done. Errors:

| Response | What to do |
|---|---|
| `chat not found` | wrong chat_id, or the bot is not in the channel |
| `not enough rights to send text messages` | the bot lacks the "Post Messages" permission |
| `Unauthorized` | wrong token |

## 6. Connect it to SportIntel

1. In `.env` (the file is never committed):

   ```
   TELEGRAM_BOT_TOKEN=1234567890:AAH...
   FLAG_TELEGRAM_PUBLISH=true
   ```

   Until `FLAG_TELEGRAM_PUBLISH` is on, the system sends nothing, even if channels are configured.
2. Restart web and worker (`make api`, `make worker`, or `docker compose up -d` in production).
3. Admin → "Channels" → "New channel": name, the **chat_id** from step 4, post language, mode and schedule.
4. Click "Send test": a test message should appear in the channel.

The token is stored only in `.env` (in production, in the environment's secrets); the database stores only the chat_id.
