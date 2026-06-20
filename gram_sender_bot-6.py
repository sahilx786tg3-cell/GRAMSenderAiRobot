import telebot
import requests
import time
import base64
import json
import os
import threading
from tonsdk.crypto import mnemonic_to_wallet_key
from tonsdk.contract.wallet import WalletV4ContractR2
from tonsdk.utils import to_nano, bytes_to_b64str

BOT_TOKEN = "8977870710:AAEIzdGvOM5j8_9MSY_J6UEHKk1YF2y-8y4"
MNEMONIC = "endless woman interest senior inner arrive educate stage talk throw useful sphere ranch urban list above plate join glare peace borrow buyer armed shift".split()
ADMIN_ID = 6520878121
TONCENTER = "https://toncenter.com/api/v2"
TONCENTER_API_KEY = "73f3d7b1bf8117d8d2e2a9cf32b8c9f7d0cee9664908efbeaeee7d37c16f6fd4"
DB_FILE = "users.json"

bot = telebot.TeleBot(BOT_TOKEN)
processing = False


# ─────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────

def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}, "seen_txs": [], "tx_history": []}
    db = json.load(open(DB_FILE, "r"))
    if "tx_history" not in db:
        db["tx_history"] = []
    return db

def save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=2)

def get_user(user_id):
    db = load_db()
    uid = str(user_id)
    if uid not in db["users"]:
        db["users"][uid] = {"balance": 0.0, "banned": False}
        save_db(db)
    return db["users"][uid]

def get_user_balance(user_id):
    return get_user(user_id).get("balance", 0.0)

def is_banned(user_id):
    return get_user(user_id).get("banned", False)

def add_user_balance(user_id, amount):
    db = load_db()
    uid = str(user_id)
    if uid not in db["users"]:
        db["users"][uid] = {"balance": 0.0, "banned": False}
    db["users"][uid]["balance"] = round(db["users"][uid]["balance"] + amount, 6)
    save_db(db)

def set_user_balance(user_id, amount):
    db = load_db()
    uid = str(user_id)
    if uid not in db["users"]:
        db["users"][uid] = {"balance": 0.0, "banned": False}
    db["users"][uid]["balance"] = round(amount, 6)
    save_db(db)

def deduct_user_balance(user_id, amount):
    db = load_db()
    uid = str(user_id)
    if uid not in db["users"]:
        return False
    if db["users"][uid]["balance"] < amount:
        return False
    db["users"][uid]["balance"] = round(db["users"][uid]["balance"] - amount, 6)
    save_db(db)
    return True

def ban_user(user_id):
    db = load_db()
    uid = str(user_id)
    if uid not in db["users"]:
        db["users"][uid] = {"balance": 0.0, "banned": False}
    db["users"][uid]["banned"] = True
    save_db(db)

def unban_user(user_id):
    db = load_db()
    uid = str(user_id)
    if uid not in db["users"]:
        db["users"][uid] = {"balance": 0.0, "banned": False}
    db["users"][uid]["banned"] = False
    save_db(db)

def is_tx_seen(tx_hash):
    db = load_db()
    return tx_hash in db["seen_txs"]

def mark_tx_seen(tx_hash):
    db = load_db()
    if tx_hash not in db["seen_txs"]:
        db["seen_txs"].append(tx_hash)
    save_db(db)

def save_tx_history(entry):
    db = load_db()
    db["tx_history"].insert(0, entry)
    db["tx_history"] = db["tx_history"][:50]  # keep last 50 only
    save_db(db)

def get_tx_history():
    db = load_db()
    return db.get("tx_history", [])

def get_all_users_sorted():
    db = load_db()
    users = []
    for uid, data in db["users"].items():
        users.append({
            "user_id": uid,
            "balance": data.get("balance", 0.0),
            "banned": data.get("banned", False)
        })
    users.sort(key=lambda x: x["balance"], reverse=True)
    return users


# ─────────────────────────────────────────
# WALLET
# ─────────────────────────────────────────

def get_headers():
    return {"X-API-Key": TONCENTER_API_KEY}

def get_wallet():
    pub_k, priv_k = mnemonic_to_wallet_key(MNEMONIC)
    wallet = WalletV4ContractR2(public_key=pub_k, private_key=priv_k)
    addr = wallet.address.to_string(True, True, False)
    return addr, wallet, pub_k, priv_k

def get_wallet_balance():
    addr, _, _, _ = get_wallet()
    try:
        r = requests.get(
            f"{TONCENTER}/getAddressInformation",
            params={"address": addr},
            headers=get_headers(),
            timeout=10
        ).json()
        return int(r["result"]["balance"]) / 1e9
    except Exception as e:
        print(f"[BALANCE ERROR] {e}")
        return None

def get_wallet_state():
    addr, _, _, _ = get_wallet()
    try:
        r = requests.get(
            f"{TONCENTER}/getAddressInformation",
            params={"address": addr},
            headers=get_headers(),
            timeout=10
        ).json()
        return r["result"].get("state", "uninitialized")
    except:
        return "unknown"

def get_seqno():
    addr, _, _, _ = get_wallet()
    try:
        r = requests.get(
            f"{TONCENTER}/getWalletInformation",
            params={"address": addr},
            headers=get_headers(),
            timeout=10
        ).json()
        seqno = r["result"].get("seqno") or 0
        return int(seqno)
    except Exception as e:
        print(f"[SEQNO ERROR] {e}")
        return 0

def deploy_wallet():
    addr, wallet, _, _ = get_wallet()
    try:
        query = wallet.create_init_external_message()
        boc = bytes_to_b64str(query["message"].to_boc(False))
        r = requests.post(
            f"{TONCENTER}/sendBoc",
            json={"boc": boc},
            headers=get_headers(),
            timeout=15
        ).json()
        print(f"[DEPLOY] {r}")
        return r
    except Exception as e:
        return {"ok": False, "error": str(e)}

def send_ton_to(to_address, amount_ton, memo=""):
    addr, wallet, _, _ = get_wallet()
    seqno = get_seqno()
    query = wallet.create_transfer_message(
        to_addr=to_address,
        amount=to_nano(amount_ton, "ton"),
        seqno=seqno,
        send_mode=3,
        payload=memo if memo else ""
    )
    boc = bytes_to_b64str(query["message"].to_boc(False))
    r = requests.post(
        f"{TONCENTER}/sendBoc",
        json={"boc": boc},
        headers=get_headers(),
        timeout=15
    ).json()
    print(f"[SENDBOC] {r}")
    return r

def get_tx_hash_after_send():
    addr, _, _, _ = get_wallet()
    time.sleep(15)
    try:
        r = requests.get(
            f"{TONCENTER}/getTransactions",
            params={"address": addr, "limit": 5},
            headers=get_headers(),
            timeout=10
        ).json()
        for tx in r.get("result", []):
            if tx.get("out_msgs") and len(tx["out_msgs"]) > 0:
                raw = tx["transaction_id"]["hash"]
                return base64.b64decode(raw).hex().upper()
    except Exception as e:
        print(f"[HASH ERROR] {e}")
    return None


# ─────────────────────────────────────────
# SEND HELPER
# ─────────────────────────────────────────

def execute_send(message, amount, to_address, memo="", deduct_from_user_id=None):
    global processing

    clean_address = to_address.strip()
    if len(clean_address) != 48:
        bot.reply_to(
            message,
            f"Invalid TON address!\n"
            f"Got {len(clean_address)} characters, need 48.\n\n"
            f"Address received:\n`{clean_address}`",
            parse_mode="Markdown"
        )
        return

    if amount <= 0:
        bot.reply_to(message, "Amount must be greater than 0.")
        return

    if processing:
        bot.reply_to(message, "One transaction is already running. Please wait!")
        return

    fee = 0.01

    if deduct_from_user_id is not None:
        user_bal = get_user_balance(deduct_from_user_id)
        total_needed = round(amount + fee, 6)

        # Check 1: Does the user's tracked balance have enough?
        if user_bal < total_needed:
            bot.reply_to(
                message,
                f"Insufficient Balance!\n\n"
                f"Your Balance: `{user_bal:.4f} TON`\n"
                f"Required: `{total_needed:.4f} TON` (including {fee} TON fee)\n\n"
                f"Deposit more using /deposit",
                parse_mode="Markdown"
            )
            return

        # Check 2: CRITICAL - Does the real wallet actually have enough TON?
        # Without this, a corrupted/tampered tracked balance could trigger
        # a send attempt the wallet can never fulfill.
        wallet_bal = get_wallet_balance()
        if wallet_bal is None:
            bot.reply_to(message, "Could not verify wallet balance. Try again later.")
            return
        if wallet_bal < amount + fee:
            bot.reply_to(
                message,
                f"Transaction Unavailable!\n\n"
                f"The bot wallet does not currently have enough TON to process this withdrawal.\n"
                f"Wallet Balance: `{wallet_bal:.4f} TON`\n"
                f"Requested: `{amount + fee:.4f} TON`\n\n"
                f"Please try again later or contact admin.",
                parse_mode="Markdown"
            )
            return

        if not deduct_user_balance(deduct_from_user_id, total_needed):
            bot.reply_to(message, "Balance deduction failed. Try again.")
            return
    else:
        wallet_bal = get_wallet_balance()
        if wallet_bal is None or wallet_bal < amount + fee:
            bot.reply_to(
                message,
                f"Insufficient Wallet Balance!\n\n"
                f"Available: `{wallet_bal:.4f} TON`\n"
                f"Required: `{amount + fee:.4f} TON`",
                parse_mode="Markdown"
            )
            return

    state = get_wallet_state()
    if state == "uninitialized":
        if deduct_from_user_id:
            add_user_balance(deduct_from_user_id, amount + fee)
        bot.reply_to(message, "Wallet not deployed yet. Contact admin.")
        return

    processing = True
    memo_text = f"\nMemo: `{memo}`" if memo else ""
    status_msg = bot.reply_to(
        message,
        f"Sending {amount} TON to `{clean_address}`...{memo_text}",
        parse_mode="Markdown"
    )

    try:
        result = send_ton_to(clean_address, amount, memo)

        if not result.get("ok"):
            error = result.get("error", "Unknown error")
            if deduct_from_user_id:
                add_user_balance(deduct_from_user_id, amount + fee)
            bot.edit_message_text(
                f"Transaction Failed!\nReason: {error}"
                + ("\n\nYour balance has been refunded." if deduct_from_user_id else ""),
                chat_id=status_msg.chat.id,
                message_id=status_msg.message_id
            )
            processing = False
            return

        tx_hash = get_tx_hash_after_send()
        addr, _, _, _ = get_wallet()

        # CRITICAL: sendBoc returning "ok": true only means the message was
        # broadcast — it does NOT guarantee the transaction succeeded on-chain
        # (e.g. wallet had insufficient real balance). We must verify the
        # transaction actually landed before telling the user it succeeded.
        if not tx_hash:
            if deduct_from_user_id:
                add_user_balance(deduct_from_user_id, amount + fee)
            bot.edit_message_text(
                f"Transaction Could Not Be Confirmed!\n\n"
                f"The transaction was broadcast but could not be verified on-chain. "
                f"This usually means it failed (e.g. insufficient real wallet balance).\n\n"
                + ("Your balance has been refunded." if deduct_from_user_id else "Please check the wallet manually."),
                chat_id=status_msg.chat.id,
                message_id=status_msg.message_id
            )
            processing = False
            return

        tx_url = f"https://tonviewer.com/transaction/{tx_hash}"

        remaining = ""
        if deduct_from_user_id:
            remaining = f"\nRemaining Balance: `{get_user_balance(deduct_from_user_id):.4f} TON`"

        # Save to history
        save_tx_history({
            "type": "withdraw" if deduct_from_user_id else "send",
            "user_id": str(deduct_from_user_id) if deduct_from_user_id else "admin",
            "amount": amount,
            "to": clean_address,
            "memo": memo,
            "tx_hash": tx_hash or "",
            "tx_url": tx_url,
            "time": time.strftime("%Y-%m-%d %H:%M:%S")
        })

        memo_line = f"\nMemo: `{memo}`" if memo else ""
        bot.edit_message_text(
            f"{amount} TON Sent Successfully!\n\n"
            f"Amount: `{amount} TON`\n"
            f"To: `{clean_address}`"
            f"{memo_line}"
            f"{remaining}\n\n"
            f"[View Transaction]({tx_url})",
            chat_id=status_msg.chat.id,
            message_id=status_msg.message_id,
            parse_mode="Markdown"
        )

    except Exception as e:
        if deduct_from_user_id:
            add_user_balance(deduct_from_user_id, amount + fee)
        print(f"[SEND ERROR] {e}")
        bot.edit_message_text(
            f"Error: {str(e)}"
            + ("\n\nYour balance has been refunded." if deduct_from_user_id else ""),
            chat_id=status_msg.chat.id,
            message_id=status_msg.message_id
        )
    finally:
        processing = False


# ─────────────────────────────────────────
# DEPOSIT MONITOR
# ─────────────────────────────────────────

def monitor_deposits():
    addr, _, _, _ = get_wallet()
    print("[MONITOR] Deposit monitor started...")
    while True:
        try:
            r = requests.get(
                f"{TONCENTER}/getTransactions",
                params={"address": addr, "limit": 20},
                headers=get_headers(),
                timeout=10
            ).json()

            for tx in reversed(r.get("result", [])):
                in_msg = tx.get("in_msg", {})
                out_msgs = tx.get("out_msgs", [])
                if not in_msg or out_msgs:
                    continue

                tx_hash = tx["transaction_id"]["hash"]
                if is_tx_seen(tx_hash):
                    continue
                mark_tx_seen(tx_hash)

                value = int(in_msg.get("value", 0))
                if value <= 0:
                    continue
                amount_ton = value / 1e9

                from_addr = in_msg.get("source", "Unknown")

                msg_data = in_msg.get("msg_data", {})
                comment = ""
                if msg_data.get("@type") == "msg.dataText":
                    comment = msg_data.get("text", "")
                    try:
                        comment = base64.b64decode(comment).decode("utf-8").strip()
                    except:
                        pass

                print(f"[DEPOSIT] {amount_ton} TON | From: {from_addr} | Memo: {comment}")

                tx_hash_hex = base64.b64decode(tx_hash).hex().upper() if tx_hash else ""

                if comment.isdigit():
                    user_id = int(comment)
                    add_user_balance(user_id, amount_ton)
                    print(f"[DEPOSIT] Credited {amount_ton} TON to user {user_id}")

                    # Save deposit to history
                    save_tx_history({
                        "type": "deposit",
                        "user_id": str(user_id),
                        "amount": amount_ton,
                        "from": from_addr,
                        "to": addr,
                        "memo": comment,
                        "tx_hash": tx_hash_hex,
                        "tx_url": f"https://tonviewer.com/transaction/{tx_hash_hex}" if tx_hash_hex else "",
                        "time": time.strftime("%Y-%m-%d %H:%M:%S")
                    })

                    try:
                        bot.send_message(
                            user_id,
                            f"Deposit Confirmed!\n\n"
                            f"Amount: `{amount_ton:.4f} TON`\n"
                            f"Your Balance: `{get_user_balance(user_id):.4f} TON`\n\n"
                            f"Use /mybalance to check anytime.",
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        print(f"[NOTIFY ERROR] {e}")
                else:
                    print(f"[DEPOSIT] No valid memo — skipped")

        except Exception as e:
            print(f"[MONITOR ERROR] {e}")

        time.sleep(30)


# ─────────────────────────────────────────
# TRANSACTION REPORT HELPER
# ─────────────────────────────────────────

def format_tx_line(i, tx):
    tx_type = tx.get("type", "unknown")
    type_icons = {
        "deposit": "➕ DEPOSIT",
        "withdraw": "➖ WITHDRAWAL",
        "send": "➖ SEND (Admin)",
        "add_balance": "🔧 ADD BALANCE",
        "remove_balance": "🔧 REMOVE BALANCE",
        "set_balance": "🔧 SET BALANCE"
    }
    label = type_icons.get(tx_type, tx_type.upper())

    user = tx.get("user_id", "unknown")
    amount = tx.get("amount", 0)
    from_addr = tx.get("from", "")
    to_addr = tx.get("to", "")
    memo = tx.get("memo", "")
    tx_url = tx.get("tx_url", "")
    tx_time = tx.get("time", "")

    line = f"{i}. {label} | {tx_time}\n"
    line += f"   User ID: `{user}`\n"
    line += f"   Amount: `{amount:.4f} TON`\n"
    if from_addr:
        line += f"   From: `{from_addr[:20]}...`\n"
    if to_addr:
        line += f"   To: `{to_addr[:20]}...`\n"
    if memo:
        line += f"   Memo: `{memo}`\n"
    if tx_url:
        line += f"   [View TX]({tx_url})\n"
    return line

def send_tx_report(message, tx_list, title):
    lines = [f"{title}:\n"]
    for i, tx in enumerate(tx_list, 1):
        lines.append(format_tx_line(i, tx))

    full_text = "\n".join(lines)
    if len(full_text) <= 4000:
        bot.reply_to(message, full_text, parse_mode="Markdown")
    else:
        chunks = []
        chunk = ""
        for line in lines:
            if len(chunk) + len(line) > 4000:
                chunks.append(chunk)
                chunk = line
            else:
                chunk += line
        if chunk:
            chunks.append(chunk)
        for c in chunks:
            bot.send_message(message.chat.id, c, parse_mode="Markdown")


# ─────────────────────────────────────────
# BOT HANDLERS
# ─────────────────────────────────────────

@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_all(message):
    global processing
    user_id = message.from_user.id
    text = message.text.strip()
    lower = text.lower()
    print(f"[MSG] From: {user_id} | Text: {text}")

    # /start
    if lower == "/start":
        bot.reply_to(
            message,
            "Welcome to GRAM Sender Bot!\n\n"
            "Commands:\n"
            "/deposit — Get deposit address + memo\n"
            "/mybalance — Check your balance\n"
            "/deposithistory — Your deposit history\n"
            "/withdrawalhistory — Your withdrawal history\n"
            "/withdraw <amount> <address> — Withdraw TON\n"
            "/withdraw <amount> <address> <memo> — Withdraw with memo\n"
            "/send <amount> <address> — Send TON\n"
            "/send <amount> <address> <memo> — Send with memo\n"
            "/myid — Get your Telegram ID"
        )
        return

    # Ban check
    if user_id != ADMIN_ID and is_banned(user_id):
        bot.reply_to(message, "You are banned from using this bot.")
        return

    # /myid
    if lower == "/myid":
        bot.reply_to(message, f"Your Telegram ID: `{user_id}`", parse_mode="Markdown")
        return

    # /deposit
    if lower == "/deposit":
        addr, _, _, _ = get_wallet()
        bot.reply_to(
            message,
            f"Deposit TON\n\n"
            f"Wallet Address:\n`{addr}`\n\n"
            f"Your Memo (REQUIRED):\n`{user_id}`\n\n"
            f"You MUST enter your Telegram ID as comment/memo when sending.\n"
            f"Without memo, deposit will NOT be credited!\n\n"
            f"Minimum deposit: 0.01 TON",
            parse_mode="Markdown"
        )
        return

    # /mybalance
    if lower == "/mybalance":
        balance = get_user_balance(user_id)
        bot.reply_to(
            message,
            f"Your Balance: `{balance:.4f} TON`",
            parse_mode="Markdown"
        )
        return

    # /deposithistory — user's own deposit history (last 20)
    if lower == "/deposithistory":
        history = get_tx_history()
        my_deposits = [
            tx for tx in history
            if tx.get("type") == "deposit" and tx.get("user_id") == str(user_id)
        ][:20]
        if not my_deposits:
            bot.reply_to(message, "No deposits found for you yet.")
            return
        lines = [f"Your Deposit History (last {len(my_deposits)}):\n"]
        for i, tx in enumerate(my_deposits, 1):
            amount = tx.get("amount", 0)
            tx_time = tx.get("time", "")
            tx_url = tx.get("tx_url", "")
            line = f"{i}. ➕ `{amount:.4f} TON` | {tx_time}"
            if tx_url:
                line += f"\n   [View TX]({tx_url})"
            lines.append(line)
        full_text = "\n\n".join(lines)
        if len(full_text) <= 4000:
            bot.reply_to(message, full_text, parse_mode="Markdown")
        else:
            for i in range(0, len(full_text), 4000):
                bot.send_message(message.chat.id, full_text[i:i+4000], parse_mode="Markdown")
        return

    # /withdrawalhistory — user's own withdrawal history (last 20)
    if lower == "/withdrawalhistory":
        history = get_tx_history()
        my_withdrawals = [
            tx for tx in history
            if tx.get("type") == "withdraw" and tx.get("user_id") == str(user_id)
        ][:20]
        if not my_withdrawals:
            bot.reply_to(message, "No withdrawals found for you yet.")
            return
        lines = [f"Your Withdrawal History (last {len(my_withdrawals)}):\n"]
        for i, tx in enumerate(my_withdrawals, 1):
            amount = tx.get("amount", 0)
            to_addr = tx.get("to", "")
            tx_time = tx.get("time", "")
            tx_url = tx.get("tx_url", "")
            line = f"{i}. ➖ `{amount:.4f} TON` | {tx_time}"
            if to_addr:
                line += f"\n   To: `{to_addr[:20]}...`"
            if tx_url:
                line += f"\n   [View TX]({tx_url})"
            lines.append(line)
        full_text = "\n\n".join(lines)
        if len(full_text) <= 4000:
            bot.reply_to(message, full_text, parse_mode="Markdown")
        else:
            for i in range(0, len(full_text), 4000):
                bot.send_message(message.chat.id, full_text[i:i+4000], parse_mode="Markdown")
        return

    # /withdraw <amount> <address> [memo]
    if lower.startswith("/withdraw"):
        parts = text.split()
        if len(parts) < 3 or len(parts) > 4:
            bot.reply_to(
                message,
                "Format:\n"
                "/withdraw <amount> <address>\n"
                "/withdraw <amount> <address> <memo>\n\n"
                "Example:\n"
                "/withdraw 0.05 UQB9...\n"
                "/withdraw 0.05 UQB9... mymemo123"
            )
            return
        try:
            amount = float(parts[1])
            to_address = parts[2]
            memo = parts[3] if len(parts) == 4 else ""
        except ValueError:
            bot.reply_to(message, "Invalid amount.")
            return
        execute_send(message, amount, to_address, memo=memo, deduct_from_user_id=user_id)
        return

    # /send <amount> <address> [memo]
    if lower.startswith("/send"):
        parts = text.split()

        # /send <amount> <address> [memo]
        if len(parts) >= 3:
            try:
                amount = float(parts[1])
                to_address = parts[2]
                memo = parts[3] if len(parts) >= 4 else ""
            except ValueError:
                bot.reply_to(message, "Format: /send <amount> <address> [memo]")
                return
            if user_id == ADMIN_ID:
                execute_send(message, amount, to_address, memo=memo)
            else:
                execute_send(message, amount, to_address, memo=memo, deduct_from_user_id=user_id)
            return

        # /send <amount> — reply to address message
        if len(parts) == 2:
            if not message.reply_to_message or not message.reply_to_message.text:
                bot.reply_to(
                    message,
                    "Reply to the address message and send /send <amount>\n"
                    "Or use: /send <amount> <address>"
                )
                return
            try:
                amount = float(parts[1])
                to_address = message.reply_to_message.text.strip()
            except ValueError:
                bot.reply_to(message, "Invalid amount.")
                return
            if user_id == ADMIN_ID:
                execute_send(message, amount, to_address)
            else:
                execute_send(message, amount, to_address, deduct_from_user_id=user_id)
            return

        bot.reply_to(message, "Format: /send <amount> <address> [memo]")
        return

    # ── ADMIN ONLY ──
    if user_id != ADMIN_ID:
        return

    # /balance
    if lower == "/balance":
        balance = get_wallet_balance()
        addr, _, _, _ = get_wallet()
        state = get_wallet_state()
        bot.reply_to(
            message,
            f"Wallet Balance: `{balance:.4f} TON`\n"
            f"Wallet State: `{state}`\n\n"
            f"Address:\n`{addr}`",
            parse_mode="Markdown"
        )
        return

    # /deploy
    if lower == "/deploy":
        state = get_wallet_state()
        if state == "active":
            bot.reply_to(message, "Wallet is already active!")
            return
        bot.reply_to(message, "Deploying wallet...")
        result = deploy_wallet()
        if result.get("ok"):
            bot.reply_to(message, "Wallet deployed successfully!\nWait 30 seconds then try /send.")
        else:
            bot.reply_to(message, f"Deploy failed!\nReason: {result.get('error', 'Unknown')}")
        return

    # /myaddress
    if lower == "/myaddress":
        addr, _, _, _ = get_wallet()
        bot.reply_to(message, f"Wallet Address:\n`{addr}`", parse_mode="Markdown")
        return

    # /help — show all admin commands including new ones
    if lower == "/help":
        bot.reply_to(
            message,
            "Admin Commands:\n\n"
            "/balance — Wallet balance\n"
            "/myaddress — Wallet address\n"
            "/deploy — Deploy wallet\n"
            "/addbalance <id> <amt>\n"
            "/removebalance <id> <amt>\n"
            "/setbalance <id> <amt>\n"
            "/checkbalance <id>\n"
            "/allusers — List all users\n"
            "/transactions — Last 50 transactions (all types)\n"
            "/alldeposits — Last 20 deposits\n"
            "/allwithdrawals — Last 20 withdrawals\n"
            "/ban <id>\n"
            "/unban <id>",
            parse_mode="Markdown"
        )
        return

    # /addbalance <user_id> <amount>
    if lower.startswith("/addbalance"):
        parts = text.split()
        if len(parts) != 3:
            bot.reply_to(message, "Format: /addbalance <user_id> <amount>")
            return
        try:
            target_id = int(parts[1])
            amount = float(parts[2])
        except ValueError:
            bot.reply_to(message, "Invalid user_id or amount.")
            return
        add_user_balance(target_id, amount)
        save_tx_history({
            "type": "add_balance",
            "user_id": str(target_id),
            "amount": amount,
            "from": "admin",
            "to": "",
            "memo": f"Admin added balance",
            "tx_hash": "",
            "tx_url": "",
            "time": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        bot.reply_to(
            message,
            f"Added `{amount} TON` to user `{target_id}`\n"
            f"New Balance: `{get_user_balance(target_id):.4f} TON`",
            parse_mode="Markdown"
        )
        return

    # /removebalance <user_id> <amount>
    if lower.startswith("/removebalance"):
        parts = text.split()
        if len(parts) != 3:
            bot.reply_to(message, "Format: /removebalance <user_id> <amount>")
            return
        try:
            target_id = int(parts[1])
            amount = float(parts[2])
        except ValueError:
            bot.reply_to(message, "Invalid user_id or amount.")
            return
        if deduct_user_balance(target_id, amount):
            bot.reply_to(
                message,
                f"Removed `{amount} TON` from user `{target_id}`\n"
                f"New Balance: `{get_user_balance(target_id):.4f} TON`",
                parse_mode="Markdown"
            )
        else:
            bot.reply_to(
                message,
                f"Failed! User `{target_id}` only has `{get_user_balance(target_id):.4f} TON`",
                parse_mode="Markdown"
            )
        return

    # /setbalance <user_id> <amount>
    if lower.startswith("/setbalance"):
        parts = text.split()
        if len(parts) != 3:
            bot.reply_to(message, "Format: /setbalance <user_id> <amount>")
            return
        try:
            target_id = int(parts[1])
            amount = float(parts[2])
        except ValueError:
            bot.reply_to(message, "Invalid user_id or amount.")
            return
        set_user_balance(target_id, amount)
        bot.reply_to(
            message,
            f"Balance set for user `{target_id}`\n"
            f"New Balance: `{get_user_balance(target_id):.4f} TON`",
            parse_mode="Markdown"
        )
        return

    # /checkbalance <user_id>
    if lower.startswith("/checkbalance"):
        parts = text.split()
        if len(parts) != 2:
            bot.reply_to(message, "Format: /checkbalance <user_id>")
            return
        try:
            target_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "Invalid user_id.")
            return
        bal = get_user_balance(target_id)
        banned = is_banned(target_id)
        bot.reply_to(
            message,
            f"User: `{target_id}`\n"
            f"Balance: `{bal:.4f} TON`\n"
            f"Status: `{'Banned' if banned else 'Active'}`",
            parse_mode="Markdown"
        )
        return

    # /allusers — all users sorted by balance
    if lower == "/allusers":
        users = get_all_users_sorted()
        if not users:
            bot.reply_to(message, "No users found.")
            return
        lines = ["All Users (sorted by balance):\n"]
        for i, u in enumerate(users, 1):
            status = "BANNED" if u["banned"] else "Active"
            lines.append(
                f"{i}. ID: `{u['user_id']}`\n"
                f"   Balance: `{u['balance']:.4f} TON`\n"
                f"   Status: {status}\n"
            )
        # Split into chunks if too long
        full_text = "\n".join(lines)
        if len(full_text) <= 4000:
            bot.reply_to(message, full_text, parse_mode="Markdown")
        else:
            chunks = []
            chunk = ""
            for line in lines:
                if len(chunk) + len(line) > 4000:
                    chunks.append(chunk)
                    chunk = line
                else:
                    chunk += line
            if chunk:
                chunks.append(chunk)
            for c in chunks:
                bot.send_message(message.chat.id, c, parse_mode="Markdown")
        return

    # /transactions — recent transaction history (deposit, withdraw, send, add, remove, set — last 50)
    if lower == "/transactions":
        history = get_tx_history()
        if not history:
            bot.reply_to(message, "No transactions found.")
            return
        send_tx_report(message, history[:50], f"All Transactions (last {len(history[:50])})")
        return

    # /alldeposits — recent deposits only (last 20)
    if lower == "/alldeposits":
        history = get_tx_history()
        deposits = [tx for tx in history if tx.get("type") == "deposit"][:20]
        if not deposits:
            bot.reply_to(message, "No deposits found.")
            return
        send_tx_report(message, deposits, f"Deposits (last {len(deposits)})")
        return

    # /allwithdrawals — recent withdrawals only (last 20)
    if lower == "/allwithdrawals":
        history = get_tx_history()
        withdrawals = [tx for tx in history if tx.get("type") in ("withdraw", "send")][:20]
        if not withdrawals:
            bot.reply_to(message, "No withdrawals found.")
            return
        send_tx_report(message, withdrawals, f"Withdrawals (last {len(withdrawals)})")
        return

    # /ban <user_id>
    if lower.startswith("/ban"):
        parts = text.split()
        if len(parts) != 2:
            bot.reply_to(message, "Format: /ban <user_id>")
            return
        try:
            target_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "Invalid user_id.")
            return
        if target_id == ADMIN_ID:
            bot.reply_to(message, "Cannot ban admin!")
            return
        ban_user(target_id)
        bot.reply_to(message, f"User `{target_id}` has been banned.", parse_mode="Markdown")
        try:
            bot.send_message(target_id, "You have been banned from this bot.")
        except:
            pass
        return

    # /unban <user_id>
    if lower.startswith("/unban"):
        parts = text.split()
        if len(parts) != 2:
            bot.reply_to(message, "Format: /unban <user_id>")
            return
        try:
            target_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "Invalid user_id.")
            return
        unban_user(target_id)
        bot.reply_to(message, f"User `{target_id}` has been unbanned.", parse_mode="Markdown")
        try:
            bot.send_message(target_id, "You have been unbanned. You can use the bot again.")
        except:
            pass
        return


# ─────────────────────────────────────────
# START
# ─────────────────────────────────────────

print("Bot is running...")
monitor_thread = threading.Thread(target=monitor_deposits, daemon=True)
monitor_thread.start()
bot.polling(none_stop=True, interval=0)
