import telebot
import requests
import time
import base64
from tonsdk.crypto import mnemonic_to_wallet_key
from tonsdk.contract.wallet import WalletV4ContractR2
from tonsdk.utils import to_nano, bytes_to_b64str

BOT_TOKEN = "8532448307:AAFrBbTkMTHQzXjQAxbGWa_in7rdr_F9hkI"
MNEMONIC = "endless woman interest senior inner arrive educate stage talk throw useful sphere ranch urban list above plate join glare peace borrow buyer armed shift".split()
ADMIN_ID = 6520878121
WALLET_ADDRESS = "EQBs2e9qbnIwREgnRtjg1zLiMv9tlCQGzYZ7Eq66ChGMz3M-"
TONCENTER = "https://toncenter.com/api/v2"

bot = telebot.TeleBot(BOT_TOKEN)
processing = False

def get_seqno(address):
    try:
        r = requests.get(
            f"{TONCENTER}/getWalletInformation",
            params={"address": address},
            timeout=10
        ).json()
        seqno = r["result"].get("seqno", 0)
        return int(seqno)
    except Exception as e:
        print(f"[SEQNO ERROR] {e}")
        return 0

def get_balance():
    try:
        r = requests.get(
            f"{TONCENTER}/getAddressInformation",
            params={"address": WALLET_ADDRESS},
            timeout=10
        ).json()
        return int(r["result"]["balance"]) / 1e9
    except:
        return None

def get_tx_hash():
    try:
        r = requests.get(
            f"{TONCENTER}/getTransactions",
            params={"address": WALLET_ADDRESS, "limit": 5},
            timeout=10
        ).json()
        for tx in r.get("result", []):
            if tx.get("out_msgs") and len(tx["out_msgs"]) > 0:
                raw_hash = tx["transaction_id"]["hash"]
                decoded = base64.b64decode(raw_hash)
                return decoded.hex().upper()
    except Exception as e:
        print(f"[HASH ERROR] {e}")
    return None

def get_transactions_list(limit=50):
    try:
        r = requests.get(
            f"{TONCENTER}/getTransactions",
            params={"address": WALLET_ADDRESS, "limit": limit},
            timeout=15
        ).json()
        return r.get("result", [])
    except Exception as e:
        print(f"[TX LIST ERROR] {e}")
        return []

def send_ton(to_address, amount_ton):
    pub_k, priv_k = mnemonic_to_wallet_key(MNEMONIC)
    wallet = WalletV4ContractR2(public_key=pub_k, private_key=priv_k)
    seqno = get_seqno(WALLET_ADDRESS)
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
        timeout=15
    ).json()
    print(f"[SENDBOC] {r}")
    return r

def do_send(message, amount, to_address):
    global processing
    if processing:
        bot.reply_to(message, "⏳ Ek transaction chal rahi hai, wait karo!")
        return

    balance = get_balance()
    if balance is None:
        bot.reply_to(message, "❌ Balance check failed! Try again.")
        return

    if balance < amount + 0.01:
        bot.reply_to(message,
            f"❌ Insufficient Balance!\n\n"
            f"💰 Available: `{balance:.4f} TON`\n"
            f"💸 Required: `{amount + 0.01:.4f} TON` (including fees)\n\n"
            f"Please add more TON to wallet!",
            parse_mode="Markdown"
        )
        return

    processing = True
    status_msg = bot.reply_to(message, f"⏳ Sending {amount} TON...")
    try:
        result = send_ton(to_address, amount)
        if not result.get("ok"):
            bot.edit_message_text(
                f"❌ Transaction Failed!\nReason: {result.get('error', 'Unknown')}",
                chat_id=status_msg.chat.id,
                message_id=status_msg.message_id
            )
            processing = False
            return

        time.sleep(15)
        tx_hash = get_tx_hash()
        if tx_hash:
            tx_url = f"https://tonviewer.com/transaction/{tx_hash}"
        else:
            tx_url = f"https://tonviewer.com/{WALLET_ADDRESS}"

        bot.edit_message_text(
            f"✅ {amount} TON Sent Successfully!\n\n"
            f"💰 Amount: {amount} TON\n"
            f"📬 To: `{to_address}`\n"
            f"🧾 Status: Success\n\n"
            f"[🔍 View on Explorer]({tx_url})\n\n"
            f"🤖 Bot: @GramSenderAiBot",
            chat_id=status_msg.chat.id,
            message_id=status_msg.message_id,
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.edit_message_text(
            f"❌ Error: {str(e)}",
            chat_id=status_msg.chat.id,
            message_id=status_msg.message_id
        )
    finally:
        processing = False

def parse_tx(tx):
    """Ek transaction ko parse karke type, amount, address, time return karta hai"""
    utime = tx.get("utime", 0)
    time_str = time.strftime("%d-%m-%Y %H:%M", time.localtime(utime))
    in_msg = tx.get("in_msg", {})
    out_msgs = tx.get("out_msgs", [])

    in_value = int(in_msg.get("value", 0)) / 1e9 if in_msg else 0
    in_source = in_msg.get("source", "") if in_msg else ""

    results = []
    if in_value > 0 and in_source:
        results.append({"type": "deposit", "amount": in_value, "address": in_source, "time": time_str})
    if out_msgs:
        for out_msg in out_msgs:
            out_value = int(out_msg.get("value", 0)) / 1e9
            out_dest = out_msg.get("destination", "")
            if out_value > 0:
                results.append({"type": "withdrawal", "amount": out_value, "address": out_dest, "time": time_str})
    return results

def format_mixed(txs, limit=50):
    all_items = []
    for tx in txs:
        all_items.extend(parse_tx(tx))
    all_items = all_items[:limit]

    if not all_items:
        return "📭 Koi transaction nahi mila!"

    lines = [f"📜 Last {len(all_items)} Transactions\n"]
    for i, item in enumerate(all_items, 1):
        icon = "➕" if item["type"] == "deposit" else "➖"
        label = "Deposit" if item["type"] == "deposit" else "Withdrawal"
        addr_short = item["address"][:10] + "..." if item["address"] else "N/A"
        lines.append(f"{i}. {icon} {label}: `{item['amount']:.4f} TON`\n   Address: `{addr_short}`\n   🕒 {item['time']}")

    return "\n\n".join(lines)

def format_filtered(txs, tx_type, limit=20):
    all_items = []
    for tx in txs:
        all_items.extend(parse_tx(tx))
    filtered = [item for item in all_items if item["type"] == tx_type][:limit]

    if not filtered:
        label = "Deposits" if tx_type == "deposit" else "Withdrawals"
        return f"📭 Koi {label} nahi mila!"

    icon = "➕" if tx_type == "deposit" else "➖"
    label = "Deposits" if tx_type == "deposit" else "Withdrawals"
    lines = [f"📜 Last {len(filtered)} {label}\n"]
    for i, item in enumerate(filtered, 1):
        addr_short = item["address"][:10] + "..." if item["address"] else "N/A"
        lines.append(f"{i}. {icon} `{item['amount']:.4f} TON`\n   Address: `{addr_short}`\n   🕒 {item['time']}")

    return "\n\n".join(lines)

def send_long_message(chat_id, text, wait_msg=None):
    if len(text) > 4000:
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
        if wait_msg:
            bot.delete_message(wait_msg.chat.id, wait_msg.message_id)
        for chunk in chunks:
            bot.send_message(chat_id, chunk, parse_mode="Markdown")
    else:
        if wait_msg:
            bot.edit_message_text(text, chat_id=wait_msg.chat.id, message_id=wait_msg.message_id, parse_mode="Markdown")
        else:
            bot.send_message(chat_id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_all(message):
    user_id = message.from_user.id
    text = message.text.strip()
    lower = text.lower()

    if lower == "/balance":
        if user_id != ADMIN_ID:
            bot.reply_to(message, "Only Admin can use this.")
            return
        balance = get_balance()
        if balance is not None:
            bot.reply_to(message,
                f"💰 Balance: `{balance:.4f} TON`\n\nAddress:\n`{WALLET_ADDRESS}`",
                parse_mode="Markdown")
        else:
            bot.reply_to(message, f"Check:\nhttps://tonviewer.com/{WALLET_ADDRESS}")
        return

    if lower == "/transactions":
        if user_id != ADMIN_ID:
            bot.reply_to(message, "Only Admin can use this.")
            return
        wait_msg = bot.reply_to(message, "⏳ Fetching last 50 transactions...")
        txs = get_transactions_list(50)
        report = format_mixed(txs, 50)
        send_long_message(message.chat.id, report, wait_msg)
        return

    if lower == "/alldeposits":
        if user_id != ADMIN_ID:
            bot.reply_to(message, "Only Admin can use this.")
            return
        wait_msg = bot.reply_to(message, "⏳ Fetching recent deposits...")
        txs = get_transactions_list(50)
        report = format_filtered(txs, "deposit", 20)
        send_long_message(message.chat.id, report, wait_msg)
        return

    if lower == "/allwithdrawals":
        if user_id != ADMIN_ID:
            bot.reply_to(message, "Only Admin can use this.")
            return
        wait_msg = bot.reply_to(message, "⏳ Fetching recent withdrawals...")
        txs = get_transactions_list(50)
        report = format_filtered(txs, "withdrawal", 20)
        send_long_message(message.chat.id, report, wait_msg)
        return

    if lower.startswith("/send"):
        if user_id != ADMIN_ID:
            bot.reply_to(message, "Only Admin can send.")
            return
        parts = text.split()

        if len(parts) == 3:
            try:
                amount = float(parts[1])
                to_address = parts[2]
                do_send(message, amount, to_address)
            except:
                bot.reply_to(message, "Format: /send 0.1 <ton_address>")
            return

        if len(parts) == 2:
            if not message.reply_to_message or not message.reply_to_message.text:
                bot.reply_to(message, "⚠️ Address wale message pe reply karke /send 0.1 likho!")
                return
            try:
                amount = float(parts[1])
                to_address = message.reply_to_message.text.strip()
                do_send(message, amount, to_address)
            except:
                bot.reply_to(message, "Format: /send 0.1")
            return

        bot.reply_to(message, "Format:\n/send 0.1 <address>\nYa address pe reply karke /send 0.1")
        return

print("Bot is running...")
bot.polling(none_stop=True, interval=0)
