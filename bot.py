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

BOT_TOKEN = "8977870710:AAHnMFSiNu4Dfrz5Zlj5J4vKjCJ7DvVQusU"
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
        return {"users": {}, "seen_txs": []}
    with open(DB_FILE, "r") as f:
        return json.load(f)

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

def send_ton_to(to_address, amount_ton):
    addr, wallet, _, _ = get_wallet()
    seqno = get_seqno()
    query = wallet.create_transfer_message(
        to_addr=to_address,
        amount=to_nano(amount_ton, "ton"),
        seqno=seqno,
        send_mode=3
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

def execute_send(message, amount, to_address, deduct_from_user_id=None):
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
    status_msg = bot.reply_to(
        message,
        f"Sending {amount} TON to `{clean_address}`...",
        parse_mode="Markdown"
    )

    try:
        result = send_ton_to(clean_address, amount)

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
        tx_url = (
            f"https://tonviewer.com/transaction/{tx_hash}"
            if tx_hash else
            f"https://tonviewer.com/{addr}"
        )

        remaining = ""
        if deduct_from_user_id:
            remaining = f"\nRemaining Balance: `{get_user_balance(deduct_from_user_id):.4f} TON`"

        bot.edit_message_text(
            f"{amount} TON Sent Successfully!\n\n"
            f"Amount: `{amount} TON`\n"
            f"To: `{clean_address}`{remaining}\n\n"
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

            for tx in r.get("result", []):
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

                msg_data = in_msg.get("msg_data", {})
                comment = ""
                if msg_data.get("@type") == "msg.dataText":
                    comment = msg_data.get("text", "")
                    try:
                        comment = base64.b64decode(comment).decode("utf-8").strip()
                    except:
                        pass

                print(f"[DEPOSIT] {amount_ton} TON | Memo: {comment}")

                if comment.isdigit():
                    user_id = int(comment)
                    add_user_balance(user_id, amount_ton)
                    print(f"[DEPOSIT] Credited {amount_ton} TON to user {user_id}")
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
            "/withdraw <amount> <address> — Withdraw TON\n"
            "/send <amount> <address> — Send TON\n"
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

    # /withdraw
    if lower.startswith("/withdraw"):
        parts = text.split()
        if len(parts) != 3:
            bot.reply_to(message, "Format: /withdraw <amount> <address>\nExample: /withdraw 0.05 UQB9...")
            return
        try:
            amount = float(parts[1])
            to_address = parts[2]
        except ValueError:
            bot.reply_to(message, "Invalid amount.\nFormat: /withdraw 0.05 UQB9...")
            return
        execute_send(message, amount, to_address, deduct_from_user_id=user_id)
        return

    # /send
    if lower.startswith("/send"):
        parts = text.split()

        if len(parts) == 3:
            try:
                amount = float(parts[1])
                to_address = parts[2]
            except ValueError:
                bot.reply_to(message, "Format: /send <amount> <address>")
                return
            if user_id == ADMIN_ID:
                execute_send(message, amount, to_address)
            else:
                execute_send(message, amount, to_address, deduct_from_user_id=user_id)
            return

        if len(parts) == 2:
            if not message.reply_to_message or not message.reply_to_message.text:
                bot.reply_to(message, "Reply to the address message and send /send <amount>\nOr use: /send <amount> <address>")
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

        bot.reply_to(message, "Format: /send <amount> <address>")
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
