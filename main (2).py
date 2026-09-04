#!/usr/bin/env python3

import asyncio
import html
import json
import logging
import os
import re
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# =========================================================
# YOUR DETAILS
# =========================================================

# IMPORTANT:
# The old token was exposed in chat. Revoke it in BotFather
# and paste the NEW token here.
BOT_TOKEN = "8852393910:AAHPbWJgIjRNFPToCMQP0mOzJ7NAcEljsOs"

OWNER_ID = 8662263918

# =========================================================

CONFIG_FILE = "bot_config.json"

MAX_START_MEDIA = 30
MAX_PRODUCT_MEDIA = 30
BUTTON_COUNT = 12

# ONLY /start output is auto-deleted.
AUTO_DELETE_SECONDS = 600  # 10 minutes


logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
)


# =========================================================
# CONFIG
# =========================================================

def make_button_data(i: int):
    return {
        "title": f"Product {i}",
        "media": [],
        "caption": f"Details for Product {i} have not been set yet.",
        "delivery_type": "text",
        "delivery_file_id": None,
        "delivery_text": (
            "🎉 Your payment has been approved!\n"
            "Thank you for your purchase."
        ),
        "qr_file_id": None,
        "upi_id": "",
    }


def default_config():
    return {
        "start_message": (
            "👋 Welcome!\n\n"
            "Choose a product from the buttons below "
            "to see details and buy."
        ),
        "start_media": [],
        "payment_text": (
            "💳 Payment Instructions\n\n"
            "1️⃣ Scan the QR code above and complete the payment.\n"
            "2️⃣ Take a screenshot of the successful payment.\n"
            "3️⃣ Send that screenshot here in this chat.\n\n"
            "✅ As soon as an admin verifies your payment, "
            "your product will be delivered automatically."
        ),
        "qr_file_id": None,
        "admins": [],
        "users": [],
        "buttons": {
            str(i): make_button_data(i)
            for i in range(1, BUTTON_COUNT + 1)
        },
        "custom_cmds": {},
        "pending": {},
        "online_post": {
            "file_id": None,
            "caption": "🔥 New Update",
        },
        "copy_forward_restricted": True,
    }


def normalize_buttons(buttons):
    normalized = {}

    for i in range(1, BUTTON_COUNT + 1):
        key = str(i)
        base = make_button_data(i)

        old = buttons.get(key, {}) if isinstance(buttons, dict) else {}
        base.update(old)

        media_list = old.get("media") if isinstance(old, dict) else None

        if not isinstance(media_list, list):
            media_list = []

        # Old format migration.
        if not media_list and old.get("media_file_id"):
            media_list = [{
                "type": old.get("media_type") or "photo",
                "file_id": old.get("media_file_id"),
            }]

        base["media"] = media_list[:MAX_PRODUCT_MEDIA]
        base.pop("media_type", None)
        base.pop("media_file_id", None)

        normalized[key] = base

    return normalized


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return default_config()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        base = default_config()
        base.update(cfg)

        # Old start media migration.
        if not base.get("start_media") and cfg.get("start_media_file_id"):
            base["start_media"] = [{
                "type": cfg.get("start_media_type") or "photo",
                "file_id": cfg["start_media_file_id"],
            }]

        base["buttons"] = normalize_buttons(cfg.get("buttons", {}))

        if not isinstance(base.get("users"), list):
            base["users"] = []

        if not isinstance(base.get("admins"), list):
            base["admins"] = []

        if not isinstance(base.get("pending"), dict):
            base["pending"] = {}

        if not isinstance(base.get("custom_cmds"), dict):
            base["custom_cmds"] = {}

        if not isinstance(base.get("online_post"), dict):
            base["online_post"] = {
                "file_id": None,
                "caption": "🔥 New Update",
            }

        if not base["online_post"].get("caption"):
            base["online_post"]["caption"] = "🔥 New Update"

        if not isinstance(base.get("copy_forward_restricted"), bool):
            base["copy_forward_restricted"] = True

        return base

    except Exception as e:
        logging.warning(f"Config load failed: {e}")
        return default_config()


CFG = load_config()


def save_config():
    try:
        temp_file = CONFIG_FILE + ".tmp"

        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(
                CFG,
                f,
                ensure_ascii=False,
                indent=2,
            )

        os.replace(temp_file, CONFIG_FILE)

    except Exception as e:
        logging.error(f"Config save failed: {e}")


# =========================================================
# HELPERS
# =========================================================

def B(text: str) -> str:
    return f"<b>{html.escape(str(text))}</b>"


def is_admin(uid: int) -> bool:
    return uid == OWNER_ID or uid in CFG["admins"]


def all_admins():
    ids = [OWNER_ID]

    for admin_id in CFG["admins"]:
        if admin_id != OWNER_ID:
            ids.append(admin_id)

    return ids


def get_button(n: int | str):
    return CFG["buttons"][str(n)]


def build_button_label(i: int, title: str) -> str:
    return title


def get_button_style(i: int):
    if i % 3 == 1:
        return "success"
    elif i % 3 == 2:
        return "primary"
    return "danger"


def main_keyboard():
    rows = []

    for i in range(1, BUTTON_COUNT + 1):
        rows.append([
            InlineKeyboardButton(
                build_button_label(i, get_button(i)["title"]),
                callback_data=f"prod_{i}",
                style=get_button_style(i),
            )
        ])

    return InlineKeyboardMarkup(rows)


def online_keyboard():
    rows = [[
        InlineKeyboardButton(
            "🟢 Online",
            url="https://t.me/",
            style="success",
        )
    ]]

    for i in range(1, BUTTON_COUNT + 1):
        rows.append([
            InlineKeyboardButton(
                get_button(i)["title"],
                callback_data=f"prod_{i}",
                style=get_button_style(i),
            )
        ])

    return InlineKeyboardMarkup(rows)


def valid_slot(args):
    if not args:
        return None

    try:
        n = int(args[0])
        return n if 1 <= n <= BUTTON_COUNT else None
    except ValueError:
        return None


def text_after_command(message):
    if not message.text:
        return ""

    parts = message.text.split(None, 1)
    return parts[1] if len(parts) > 1 else ""


def text_after_slot(message):
    if not message.text:
        return ""

    parts = message.text.split(None, 2)
    return parts[2] if len(parts) > 2 else ""


# =========================================================
# SECURITY / PROTECTED CONTENT
# =========================================================
# All bot-generated messages/media are sent with
# protect_content=True.
#
# This prevents forwarding/saving through Telegram's
# protected-content mechanism.
#
# IMPORTANT:
# A screenshot originally sent by a user cannot be made
# protected retroactively. The copy sent by this bot to
# admins is protected.


def is_protected_content() -> bool:
    """Current Telegram copy/forward protection setting."""
    return bool(CFG.get("copy_forward_restricted", True))


# =========================================================
# USER TRACKING
# =========================================================

async def track_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        chat = update.effective_chat

        if not user or not chat:
            return

        if chat.type != "private":
            return

        uid = user.id

        if uid not in CFG["users"]:
            CFG["users"].append(uid)
            save_config()
            logging.info(f"Registered user for broadcast: {uid}")

    except Exception as e:
        logging.warning(f"User tracking error: {e}")


# =========================================================
# ONLY /START AUTO DELETE
# =========================================================

async def delete_start_message_later(bot, chat_id: int, message_id: int):
    try:
        await asyncio.sleep(AUTO_DELETE_SECONDS)

        try:
            await bot.delete_message(
                chat_id=chat_id,
                message_id=message_id,
            )
            logging.info(
                f"Deleted /start message {chat_id}/{message_id}"
            )
        except Exception as e:
            logging.info(
                f"/start auto-delete skipped "
                f"{chat_id}/{message_id}: {e}"
            )

    except asyncio.CancelledError:
        pass


def schedule_start_delete(message):
    if not message:
        return

    try:
        bot = message.get_bot()

        asyncio.create_task(
            delete_start_message_later(
                bot,
                message.chat_id,
                message.message_id,
            )
        )

    except Exception as e:
        logging.warning(
            f"Could not schedule /start delete: {e}"
        )


# =========================================================
# START
# =========================================================

async def send_start(bot, chat_id):
    text = B(CFG["start_message"])
    keyboard = main_keyboard()
    media = CFG.get("start_media", [])

    # -----------------------------------------------------
    # ONE MEDIA
    # -----------------------------------------------------

    if len(media) == 1:
        m = media[0]

        try:
            if m["type"] == "photo":
                msg = await bot.send_photo(
                    chat_id=chat_id,
                    photo=m["file_id"],
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    has_spoiler=True,
                    protect_content=is_protected_content(),
                )
            else:
                msg = await bot.send_video(
                    chat_id=chat_id,
                    video=m["file_id"],
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    has_spoiler=True,
                    protect_content=is_protected_content(),
                )

            schedule_start_delete(msg)
            return

        except Exception as e:
            logging.warning(f"Start media failed: {e}")

    # -----------------------------------------------------
    # MULTIPLE MEDIA
    # -----------------------------------------------------

    if len(media) > 1:
        for i in range(0, len(media), 10):
            chunk = media[i:i + 10]
            group = []

            for m in chunk:
                if m["type"] == "photo":
                    group.append(
                        InputMediaPhoto(
                            media=m["file_id"],
                            has_spoiler=True,
                        )
                    )
                else:
                    group.append(
                        InputMediaVideo(
                            media=m["file_id"],
                            has_spoiler=True,
                        )
                    )

            try:
                messages = await bot.send_media_group(
                    chat_id=chat_id,
                    media=group,
                    protect_content=is_protected_content(),
                )

                for msg in messages:
                    schedule_start_delete(msg)

            except Exception as e:
                logging.warning(f"Start album failed: {e}")

    # -----------------------------------------------------
    # START TEXT + BUTTONS
    # -----------------------------------------------------

    msg = await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=keyboard,
        protect_content=is_protected_content(),
    )

    schedule_start_delete(msg)


# =========================================================
# PRODUCT
# =========================================================

async def send_product_media(
    bot,
    chat_id: int,
    product: dict,
    reply_markup=None,
):
    media = product.get("media", [])
    caption = B(product["caption"])

    if len(media) == 1:
        m = media[0]

        if m["type"] == "photo":
            await bot.send_photo(
                chat_id=chat_id,
                photo=m["file_id"],
                caption=caption,
                parse_mode="HTML",
                reply_markup=reply_markup,
                protect_content=is_protected_content(),
            )
        else:
            await bot.send_video(
                chat_id=chat_id,
                video=m["file_id"],
                caption=caption,
                parse_mode="HTML",
                reply_markup=reply_markup,
                protect_content=is_protected_content(),
            )

        return

    if len(media) > 1:
        for i in range(0, len(media), 10):
            chunk = media[i:i + 10]
            group = []

            for idx, m in enumerate(chunk):
                cap = caption if i == 0 and idx == 0 else None
                parse_mode = "HTML" if cap else None

                if m["type"] == "photo":
                    group.append(
                        InputMediaPhoto(
                            media=m["file_id"],
                            caption=cap,
                            parse_mode=parse_mode,
                        )
                    )
                else:
                    group.append(
                        InputMediaVideo(
                            media=m["file_id"],
                            caption=cap,
                            parse_mode=parse_mode,
                        )
                    )

            await bot.send_media_group(
                chat_id=chat_id,
                media=group,
                protect_content=is_protected_content(),
            )

        if reply_markup:
            await bot.send_message(
                chat_id=chat_id,
                text=B("🛒 Tap below to continue."),
                parse_mode="HTML",
                reply_markup=reply_markup,
                protect_content=is_protected_content(),
            )

        return

    await bot.send_message(
        chat_id=chat_id,
        text=caption,
        parse_mode="HTML",
        reply_markup=reply_markup,
        protect_content=is_protected_content(),
    )


# =========================================================
# DELIVERY
# =========================================================

async def send_delivery(bot, uid: int, product: dict):
    header = (
        f"✅ Payment Approved!\n"
        f"📦 Product: {product['title']}\n\n"
        "Here is your order:"
    )

    await bot.send_message(
        chat_id=uid,
        text=B(header),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )

    delivery_caption = (
        B(product["delivery_text"])
        if product["delivery_text"]
        else None
    )

    if (
        product["delivery_type"] == "photo"
        and product["delivery_file_id"]
    ):
        await bot.send_photo(
            chat_id=uid,
            photo=product["delivery_file_id"],
            caption=delivery_caption,
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )

    elif (
        product["delivery_type"] == "video"
        and product["delivery_file_id"]
    ):
        await bot.send_video(
            chat_id=uid,
            video=product["delivery_file_id"],
            caption=delivery_caption,
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )

    elif (
        product["delivery_type"] == "document"
        and product["delivery_file_id"]
    ):
        await bot.send_document(
            chat_id=uid,
            document=product["delivery_file_id"],
            caption=delivery_caption,
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )

    else:
        await bot.send_message(
            chat_id=uid,
            text=delivery_caption or B("Done!"),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )


# =========================================================
# USER SIDE
# =========================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_start(
        context.bot,
        update.effective_chat.id,
    )


async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        B(f"🆔 Your Telegram ID: {update.effective_user.id}"),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


async def on_product_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    n = query.data.split("_")[1]
    product = CFG["buttons"][n]

    buy_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🟢 Buy Now",
                callback_data=f"buy_{n}",
                style="success",
            )
        ],
        [
            InlineKeyboardButton(
                "🔵 Back to Menu",
                callback_data="back_home",
                style="primary",
            )
        ],
    ])

    await send_product_media(
        context.bot,
        query.message.chat_id,
        product,
        reply_markup=buy_keyboard,
    )


async def on_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await send_start(
        context.bot,
        query.message.chat_id,
    )


async def on_buy_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    n = query.data.split("_")[1]
    uid = query.from_user.id
    chat_id = query.message.chat_id
    product = CFG["buttons"][n]

    CFG["pending"][str(uid)] = n
    save_config()

    order_note = f"🧾 Order placed: {product['title']}\n\n"
    full_text = B(order_note + CFG["payment_text"])

    upi_id = product.get("upi_id") or ""

    if upi_id:
        full_text += (
            "\n\n<b>💳 UPI ID:</b> "
            f"<code>{html.escape(upi_id)}</code>"
        )

    qr = product.get("qr_file_id") or CFG.get("qr_file_id")

    if qr:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=qr,
            caption=full_text,
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=full_text,
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )

    await context.bot.send_message(
        chat_id=chat_id,
        text=B(
            "📸 Please send your payment screenshot here "
            "once you have paid."
        ),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


# =========================================================
# SCREENSHOT
# =========================================================

async def on_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if str(uid) not in CFG["pending"]:
        if not is_admin(uid):
            await update.message.reply_text(
                B(
                    "ℹ️ You don't have any pending order.\n"
                    "Please choose a product first and tap Buy Now, "
                    "then send your payment screenshot."
                ),
                parse_mode="HTML",
                protect_content=is_protected_content(),
            )
        return

    n = CFG["pending"][str(uid)]
    product = CFG["buttons"][n]
    user = update.effective_user

    username = (
        f"@{user.username}"
        if user.username
        else user.full_name
    )

    when = datetime.now().strftime("%d %b %Y, %I:%M %p")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🟢  Approve",
                callback_data=f"ap_{uid}_{n}",
                style="success",
            ),
            InlineKeyboardButton(
                "🔴  Reject",
                callback_data=f"rj_{uid}_{n}",
                style="danger",
            ),
        ]
    ])

    # Clean, spaced admin UI.
    info = (
        "🧾 <b>NEW PAYMENT SCREENSHOT</b>\n"
        "\n"
        "👤 <b>User</b>\n"
        f'<a href="tg://user?id={uid}">{html.escape(username)}</a>\n'
        "\n"
        "🆔 <b>User ID</b>\n"
        f"<code>{uid}</code>\n"
        "\n"
        "📦 <b>Product</b>\n"
        f"{html.escape(product['title'])}\n"
        "\n"
        "🕒 <b>Payment Time</b>\n"
        f"{html.escape(when)}\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>ACTION REQUIRED</b>\n"
        "Tap a button below to approve or reject."
    )

    sent = False

    # Use Bot.copy_message instead of Message.copy so the
    # HTML caption is actually parsed and the copied media
    # can be protected from forwarding/saving.
    for admin_id in all_admins():
        try:
            await context.bot.copy_message(
                chat_id=admin_id,
                from_chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
                caption=info,
                parse_mode="HTML",
                reply_markup=keyboard,
                protect_content=is_protected_content(),
            )
            sent = True

        except Exception as e:
            logging.warning(
                f"Admin notification failed {admin_id}: {e}"
            )

    if sent:
        await update.message.reply_text(
            B(
                "✅ Screenshot received!\n\n"
                "⏳ An admin is verifying your payment."
            ),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
    else:
        await update.message.reply_text(
            B("⚠️ Could not reach an admin right now."),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )


# =========================================================
# APPROVED SCREENSHOT BROADCAST
# =========================================================

async def broadcast_approved_ss(bot):
    post = CFG.get("online_post", {})
    file_id = post.get("file_id")
    caption = post.get("caption", "")

    if not file_id:
        return 0, 0

    ok = 0
    fail = 0

    users = list(CFG.get("users", []))

    for uid in users:
        try:
            await bot.send_photo(
                chat_id=uid,
                photo=file_id,
                caption=caption,
                reply_markup=online_keyboard(),
                protect_content=is_protected_content(),
            )
            ok += 1

        except Exception as e:
            fail += 1
            logging.warning(
                f"Approved SS broadcast failed for {uid}: {e}"
            )

        await asyncio.sleep(0.05)

    return ok, fail


# =========================================================
# APPROVE / REJECT
# =========================================================

async def on_approve_reject(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not is_admin(query.from_user.id):
        await query.answer(
            "This action is for admins only!",
            show_alert=True,
        )
        return

    await query.answer()

    action, uid, n = query.data.split("_")
    uid = int(uid)
    product = CFG["buttons"][n]

    if action == "ap":
        try:
            await send_delivery(
                context.bot,
                uid,
                product,
            )

            done_note = (
                f"✅ APPROVED\n\n"
                f"📦 Product: {product['title']}\n"
                f"👤 User ID: {uid}\n\n"
                "🚀 Product delivered successfully."
            )

            # Save the approved screenshot for the broadcast.
            if query.message.photo:
                CFG["online_post"]["file_id"] = (
                    query.message.photo[-1].file_id
                )

                if not CFG["online_post"].get("caption"):
                    CFG["online_post"]["caption"] = (
                        "✅ Payment Approved"
                    )

                save_config()

            await query.message.reply_text(
                "📢 <b>READY TO BROADCAST</b>\n\n"
                "The approved screenshot is ready.\n"
                "Tap below to send it to all registered users.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "📢  Broadcast SS",
                            callback_data=f"broadcast_ss_{uid}_{n}",
                            style="primary",
                        )
                    ]
                ]),
                protect_content=is_protected_content(),
            )

        except Exception as e:
            done_note = (
                "⚠️ <b>Approved, but delivery failed.</b>\n\n"
                f"👤 User: {uid}\n"
                f"❌ Error: {html.escape(str(e))}"
            )

    else:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=B(
                    "❌ Your payment was rejected.\n\n"
                    "If you sent a wrong or unclear screenshot, "
                    "please send the correct one.\n"
                    "If you think this is a mistake, contact the admin."
                ),
                parse_mode="HTML",
                protect_content=is_protected_content(),
            )
        except Exception:
            pass

        done_note = (
            "❌ <b>REJECTED</b>\n\n"
            f"👤 User ID: {uid}\n"
            "The user has been informed."
        )

    try:
        if (
            query.message.photo
            or query.message.video
            or query.message.document
        ):
            await query.edit_message_caption(
                caption=done_note,
                parse_mode="HTML",
            )
        else:
            await query.edit_message_text(
                done_note,
                parse_mode="HTML",
            )
    except Exception:
        pass

    CFG["pending"].pop(str(uid), None)
    save_config()


# =========================================================
# BROADCAST BUTTON
# =========================================================

async def on_broadcast_ss(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not is_admin(query.from_user.id):
        await query.answer(
            "Admin only",
            show_alert=True,
        )
        return

    await query.answer()

    ok, fail = await broadcast_approved_ss(context.bot)

    await query.message.reply_text(
        "📢 <b>BROADCAST COMPLETE</b>\n\n"
        f"👥 Total users: {ok + fail}\n"
        f"✅ Sent: {ok}\n"
        f"❌ Failed: {fail}\n\n"
        f"📝 <b>Caption used:</b>\n"
        f"{html.escape(CFG['online_post'].get('caption', ''))}",
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


# =========================================================
# ADMIN CHECK
# =========================================================

async def admin_only(update: Update) -> bool:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(
            B("⛔ This command is for admins only."),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return False

    return True



# =========================================================
# COPY / FORWARD PROTECTION
# =========================================================

async def cmd_protect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return

    args = [x.lower().strip() for x in (context.args or [])]

    if not args or args[0] in ("status", "check"):
        status = "🟢 ON — Copy/Forward Restricted" if is_protected_content() else "🔴 OFF — Copy/Forward Allowed"
        await update.message.reply_text(
            B(
                "🔐 COPY / FORWARD PROTECTION\n\n"
                f"📌 Status: {status}\n\n"
                "Use:\n"
                "• /protect on\n"
                "• /protect off\n"
                "• /protect status"
            ),
            parse_mode="HTML",
        )
        return

    if args[0] in ("on", "enable", "enabled"):
        CFG["copy_forward_restricted"] = True
        save_config()
        await update.message.reply_text(
            B(
                "🔐 PROTECTION ENABLED\n\n"
                "🟢 New bot messages are now copy/forward restricted.\n"
                "💾 Setting saved."
            ),
            parse_mode="HTML",
            protect_content=True,
        )
        return

    if args[0] in ("off", "disable", "disabled"):
        CFG["copy_forward_restricted"] = False
        save_config()
        await update.message.reply_text(
            B(
                "🔓 PROTECTION DISABLED\n\n"
                "🔴 New bot messages can now be copied/forwarded.\n"
                "💾 Setting saved."
            ),
            parse_mode="HTML",
            protect_content=False,
        )
        return

    await update.message.reply_text(
        B(
            "⚠️ Invalid option.\n\n"
            "Use /protect on, /protect off or /protect status"
        ),
        parse_mode="HTML",
    )


# =========================================================
# PANEL
# =========================================================

async def cmd_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return

    text = (
        "🛠 <b>ADMIN PANEL</b>\n\n"
        "━━━ <b>START</b> ━━━\n"
        "/setstart &lt;text&gt;\n"
        "/addstartmedia\n"
        "/startmedialist\n"
        "/delstartmedia\n"
        "🗑 /start output deletes after 10 minutes\n\n"
        "━━━ <b>PRODUCTS</b> ━━━\n"
        "/setbtn &lt;n&gt; &lt;title&gt;\n"
        "/setproduct &lt;n&gt;\n"
        "/addproductmedia &lt;n&gt;\n"
        "/productmedialist &lt;n&gt;\n"
        "/delproductmedia &lt;n&gt;\n"
        "/setcaption &lt;n&gt; &lt;text&gt;\n"
        "/setdelivery &lt;n&gt;\n\n"
        "━━━ <b>PAYMENT</b> ━━━\n"
        "/setqr\n"
        "/setpqr &lt;n&gt;\n"
        "/setupi &lt;n&gt; &lt;upi_id&gt;\n"
        "/setpaytext &lt;text&gt;\n\n"
        "━━━ <b>BROADCAST</b> ━━━\n"
        "/broadcast &lt;text&gt;\n"
        "Reply to media with /broadcast\n"
        "/broadcaststats\n"
        "/setbsscaption &lt;text&gt;\n"
        "📢 Broadcast messages are NOT auto-deleted.\n\n"
        "━━━ <b>CUSTOM COMMANDS</b> ━━━\n"
        "/addcmd &lt;name&gt; &lt;text&gt;\n"
        "/delcmd &lt;name&gt;\n"
        "/cmdlist\n\n"
        "━━━ <b>ADMINS</b> ━━━\n"
        "/addadmin &lt;user_id&gt;\n"
        "/deladmin &lt;user_id&gt;\n"
        "/adminlist\n\n"
        "━━━ <b>SECURITY</b> ━━━\n"
        "/protect on\n"
        "/protect off\n"
        "/protect status\n\n"
        "━━━ <b>OTHER</b> ━━━\n"
        "/myid"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


# =========================================================
# BROADCAST
# =========================================================

async def cmd_broadcast(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    reply = update.message.reply_to_message
    text = text_after_command(update.message)

    if not reply and not text:
        await update.message.reply_text(
            B(
                "📢 BROADCAST\n\n"
                "Text:\n"
                "/broadcast Hello everyone!\n\n"
                "Media:\n"
                "Send photo/video/document and reply to it with /broadcast"
            ),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    users = list(CFG.get("users", []))

    if not users:
        await update.message.reply_text(
            B("⚠️ No registered users found."),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    status = await update.message.reply_text(
        B(
            "📢 Broadcast started...\n\n"
            f"👥 Users: {len(users)}\n"
            "⏳ Please wait..."
        ),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )

    success = 0
    failed = 0

    for uid in users:
        try:
            if reply:
                await context.bot.copy_message(
                    chat_id=uid,
                    from_chat_id=update.effective_chat.id,
                    message_id=reply.message_id,
                    protect_content=is_protected_content(),
                )
            else:
                await context.bot.send_message(
                    chat_id=uid,
                    text=B(text),
                    parse_mode="HTML",
                    protect_content=is_protected_content(),
                )

            success += 1

        except Exception as e:
            failed += 1
            logging.warning(
                f"Broadcast failed for {uid}: {e}"
            )

        await asyncio.sleep(0.05)

    try:
        await status.edit_text(
            B(
                "📢 BROADCAST COMPLETE\n\n"
                f"👥 Total users: {len(users)}\n"
                f"✅ Sent: {success}\n"
                f"❌ Failed: {failed}\n\n"
                "📌 Broadcast messages are protected."
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass


async def cmd_broadcaststats(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    count = len(CFG.get("users", []))

    await update.message.reply_text(
        B(
            "📊 BROADCAST STATS\n\n"
            f"👥 Registered users: {count}\n\n"
            "Users are automatically registered when "
            "they interact with the bot."
        ),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


# =========================================================
# APPROVED SS CAPTION
# =========================================================

async def cmd_setbsscaption(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    reply = update.message.reply_to_message

    if reply and reply.text:
        caption = reply.text
    else:
        caption = text_after_command(update.message)

    if not caption:
        await update.message.reply_text(
            B(
                "📸 Approved Screenshot Caption\n\n"
                "Use:\n"
                "/setbsscaption ✅ Payment Verified!\n"
                "🎉 Order Successfully Completed!"
            ),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    CFG["online_post"]["caption"] = caption
    save_config()

    await update.message.reply_text(
        B(
            "✅ Approved screenshot caption saved!\n\n"
            f"📝 Current caption:\n{caption}"
        ),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


# =========================================================
# START ADMIN
# =========================================================

async def cmd_setstart(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    reply = update.message.reply_to_message
    text = text_after_command(update.message)

    if reply and reply.photo:
        CFG["start_media"] = [{
            "type": "photo",
            "file_id": reply.photo[-1].file_id,
        }]

        if reply.caption:
            CFG["start_message"] = reply.caption
        elif text:
            CFG["start_message"] = text

        save_config()

        await update.message.reply_text(
            B(
                "✅ Start PHOTO set!\n"
                "Add more using /addstartmedia."
            ),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    if reply and reply.video:
        CFG["start_media"] = [{
            "type": "video",
            "file_id": reply.video.file_id,
        }]

        if reply.caption:
            CFG["start_message"] = reply.caption
        elif text:
            CFG["start_message"] = text

        save_config()

        await update.message.reply_text(
            B(
                "✅ Start VIDEO set!\n"
                "Add more using /addstartmedia."
            ),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    if reply and reply.text:
        CFG["start_message"] = reply.text
        save_config()

        await update.message.reply_text(
            B("✅ Start text set!"),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    if text:
        CFG["start_message"] = text
        save_config()

        await update.message.reply_text(
            B("✅ Start text set!"),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    await update.message.reply_text(
        B(
            "/setstart &lt;welcome text&gt;\n"
            "Or reply to photo/video/text."
        ),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


async def cmd_addstartmedia(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    reply = update.message.reply_to_message

    if not reply or not (reply.photo or reply.video):
        await update.message.reply_text(
            B("Reply to a photo/video with /addstartmedia"),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    if len(CFG["start_media"]) >= MAX_START_MEDIA:
        await update.message.reply_text(
            B(f"⚠️ Limit reached: {MAX_START_MEDIA}"),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    if reply.photo:
        CFG["start_media"].append({
            "type": "photo",
            "file_id": reply.photo[-1].file_id,
        })
    else:
        CFG["start_media"].append({
            "type": "video",
            "file_id": reply.video.file_id,
        })

    save_config()

    await update.message.reply_text(
        B(
            f"✅ Added!\n"
            f"Start media: {len(CFG['start_media'])}"
        ),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


async def cmd_startmedialist(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    photos = sum(
        1 for m in CFG["start_media"] if m["type"] == "photo"
    )
    videos = sum(
        1 for m in CFG["start_media"] if m["type"] == "video"
    )

    await update.message.reply_text(
        B(
            f"🖼 Start media: {len(CFG['start_media'])}\n"
            f"• Photos: {photos}\n"
            f"• Videos: {videos}\n\n"
            "🗑 /start output deletes after 10 minutes."
        ),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


async def cmd_delstartmedia(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    CFG["start_media"] = []
    save_config()

    await update.message.reply_text(
        B("✅ All start media removed."),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


# =========================================================
# PRODUCT ADMIN
# =========================================================

async def cmd_setbtn(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    n = valid_slot(context.args)

    if n is None or len(context.args) < 2:
        await update.message.reply_text(
            B(
                f"/setbtn 1 Netflix Premium\n"
                f"Number: 1-{BUTTON_COUNT}"
            ),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    CFG["buttons"][str(n)]["title"] = " ".join(context.args[1:])
    save_config()

    await update.message.reply_text(
        B(
            f"✅ Button {n}: "
            f"{CFG['buttons'][str(n)]['title']}"
        ),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


async def cmd_setproduct(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    n = valid_slot(context.args)
    reply = update.message.reply_to_message

    if n is None or reply is None:
        await update.message.reply_text(
            B(
                "Send product media/text first, "
                "then reply with /setproduct 1"
            ),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    product = CFG["buttons"][str(n)]

    if reply.photo:
        product["media"] = [{
            "type": "photo",
            "file_id": reply.photo[-1].file_id,
        }]
        if reply.caption:
            product["caption"] = reply.caption

    elif reply.video:
        product["media"] = [{
            "type": "video",
            "file_id": reply.video.file_id,
        }]
        if reply.caption:
            product["caption"] = reply.caption

    elif reply.text:
        product["media"] = []
        product["caption"] = reply.text

    else:
        await update.message.reply_text(
            B("⚠️ Reply to photo, video or text."),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    save_config()

    await update.message.reply_text(
        B(f"✅ Product {n} set!"),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


async def cmd_addproductmedia(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    n = valid_slot(context.args)
    reply = update.message.reply_to_message

    if (
        n is None
        or not reply
        or not (reply.photo or reply.video)
    ):
        await update.message.reply_text(
            B(
                "/addproductmedia 1\n"
                "Reply to photo/video."
            ),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    product = get_button(n)

    if len(product["media"]) >= MAX_PRODUCT_MEDIA:
        await update.message.reply_text(
            B(f"⚠️ Limit: {MAX_PRODUCT_MEDIA}"),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    if reply.photo:
        product["media"].append({
            "type": "photo",
            "file_id": reply.photo[-1].file_id,
        })
    else:
        product["media"].append({
            "type": "video",
            "file_id": reply.video.file_id,
        })

    if reply.caption:
        if (
            not product.get("caption")
            or product["caption"].startswith("Details for Product")
        ):
            product["caption"] = reply.caption

    save_config()

    await update.message.reply_text(
        B(
            f"✅ Added to Product {n}\n"
            f"Total media: {len(product['media'])}"
        ),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


async def cmd_productmedialist(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    n = valid_slot(context.args)

    if n is None:
        await update.message.reply_text(
            B("/productmedialist 1"),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    product = get_button(n)

    photos = sum(
        1 for m in product["media"] if m["type"] == "photo"
    )
    videos = sum(
        1 for m in product["media"] if m["type"] == "video"
    )

    await update.message.reply_text(
        B(
            f"📦 Product {n}\n"
            f"Total: {len(product['media'])}\n"
            f"• Photos: {photos}\n"
            f"• Videos: {videos}"
        ),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


async def cmd_delproductmedia(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    n = valid_slot(context.args)

    if n is None:
        return

    get_button(n)["media"] = []
    save_config()

    await update.message.reply_text(
        B(f"✅ Product {n} media cleared."),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


async def cmd_setcaption(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    n = valid_slot(context.args)
    reply = update.message.reply_to_message

    if n is not None and reply and reply.text:
        CFG["buttons"][str(n)]["caption"] = reply.text
        save_config()

        await update.message.reply_text(
            B(f"✅ Product {n} description set!"),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    text = text_after_slot(update.message)

    if n is None or not text:
        await update.message.reply_text(
            B("/setcaption 1 Description"),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    CFG["buttons"][str(n)]["caption"] = text
    save_config()

    await update.message.reply_text(
        B(f"✅ Product {n} description set!"),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


# =========================================================
# DELIVERY ADMIN
# =========================================================

async def cmd_setdelivery(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    n = valid_slot(context.args)

    if n is None:
        await update.message.reply_text(
            B(
                "/setdelivery 1 &lt;text&gt;\n"
                "Or reply to photo/video/document/text."
            ),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    product = CFG["buttons"][str(n)]
    reply = update.message.reply_to_message

    if reply:
        if reply.photo:
            product["delivery_type"] = "photo"
            product["delivery_file_id"] = reply.photo[-1].file_id

        elif reply.video:
            product["delivery_type"] = "video"
            product["delivery_file_id"] = reply.video.file_id

        elif reply.document:
            product["delivery_type"] = "document"
            product["delivery_file_id"] = reply.document.file_id

        elif reply.text:
            product["delivery_type"] = "text"
            product["delivery_file_id"] = None
            product["delivery_text"] = reply.text

        else:
            return

        if reply.caption:
            product["delivery_text"] = reply.caption

    else:
        text = text_after_slot(update.message)

        if not text:
            await update.message.reply_text(
                B("⚠️ Provide text or reply to a message."),
                parse_mode="HTML",
                protect_content=is_protected_content(),
            )
            return

        product["delivery_type"] = "text"
        product["delivery_file_id"] = None
        product["delivery_text"] = text

    save_config()

    await update.message.reply_text(
        B(f"✅ Delivery for Product {n} set!"),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


# =========================================================
# PAYMENT ADMIN
# =========================================================

async def cmd_setqr(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    reply = update.message.reply_to_message

    if not reply or not reply.photo:
        await update.message.reply_text(
            B("Reply to QR photo with /setqr"),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    CFG["qr_file_id"] = reply.photo[-1].file_id
    save_config()

    await update.message.reply_text(
        B("✅ Payment QR set!"),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


async def cmd_setpqr(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    n = valid_slot(context.args)
    reply = update.message.reply_to_message

    if n is None or not reply or not reply.photo:
        await update.message.reply_text(
            B(
                "/setpqr 1\n"
                "Reply to QR photo."
            ),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    CFG["buttons"][str(n)]["qr_file_id"] = reply.photo[-1].file_id
    save_config()

    await update.message.reply_text(
        B(f"✅ Separate QR set for Product {n}"),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


async def cmd_setupi(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    n = valid_slot(context.args)
    upi = text_after_slot(update.message)

    if n is None or not upi:
        await update.message.reply_text(
            B("/setupi 1 yourupi@bank"),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    CFG["buttons"][str(n)]["upi_id"] = upi.strip()
    save_config()

    await update.message.reply_text(
        B(f"✅ UPI ID set for Product {n}"),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


async def cmd_setpaytext(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    reply = update.message.reply_to_message

    if reply and reply.text:
        CFG["payment_text"] = reply.text
        save_config()

        await update.message.reply_text(
            B("✅ Payment instructions set!"),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    text = text_after_command(update.message)

    if not text:
        await update.message.reply_text(
            B("/setpaytext Payment instructions..."),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    CFG["payment_text"] = text
    save_config()

    await update.message.reply_text(
        B("✅ Payment instructions set!"),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


# =========================================================
# CUSTOM COMMANDS
# =========================================================

RESERVED_CMDS = {
    "start", "myid", "panel",
    "setstart", "addstartmedia", "startmedialist", "delstartmedia",
    "setbtn", "setproduct", "addproductmedia",
    "productmedialist", "delproductmedia",
    "setcaption", "setdelivery",
    "setqr", "setpqr", "setupi", "setpaytext",
    "setbsscaption",
    "addadmin", "deladmin", "adminlist",
    "addcmd", "delcmd", "cmdlist",
    "broadcast", "broadcaststats",
}


async def cmd_addcmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            B("/addcmd help Contact @YourAdmin"),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    name = context.args[0].lstrip("/").lower()

    if not re.fullmatch(r"[a-z0-9_]{1,32}", name):
        await update.message.reply_text(
            B("⚠️ Command name invalid."),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    if name in RESERVED_CMDS:
        await update.message.reply_text(
            B(f"⚠️ /{name} is reserved."),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    reply = update.message.reply_to_message

    entry = {
        "type": "text",
        "file_id": None,
        "text": "",
    }

    if reply:
        if reply.photo:
            entry = {
                "type": "photo",
                "file_id": reply.photo[-1].file_id,
                "text": reply.caption or "",
            }
        elif reply.video:
            entry = {
                "type": "video",
                "file_id": reply.video.file_id,
                "text": reply.caption or "",
            }
        elif reply.document:
            entry = {
                "type": "document",
                "file_id": reply.document.file_id,
                "text": reply.caption or "",
            }
        elif reply.text:
            entry["text"] = reply.text
        else:
            return
    else:
        text = text_after_slot(update.message)
        if not text:
            return
        entry["text"] = text

    CFG["custom_cmds"][name] = entry
    save_config()

    await update.message.reply_text(
        B(f"✅ /{name} created!"),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


async def cmd_delcmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    if not context.args:
        return

    name = context.args[0].lstrip("/").lower()

    if name in CFG["custom_cmds"]:
        del CFG["custom_cmds"][name]
        save_config()

        await update.message.reply_text(
            B(f"✅ /{name} deleted."),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
    else:
        await update.message.reply_text(
            B(f"⚠️ /{name} does not exist."),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )


async def cmd_cmdlist(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    if not CFG["custom_cmds"]:
        await update.message.reply_text(
            B("No custom commands yet."),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    lines = [
        f"📋 Custom commands ({len(CFG['custom_cmds'])}):"
    ]

    for name, command in CFG["custom_cmds"].items():
        lines.append(f"/{name} - {command['type']}")

    await update.message.reply_text(
        B("\n".join(lines)),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


async def on_custom_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message

    if (
        not message
        or not message.text
        or not message.text.startswith("/")
    ):
        return

    name = (
        message.text.split()[0][1:]
        .split("@")[0]
        .lower()
    )

    command = CFG["custom_cmds"].get(name)

    if not command:
        return

    caption = (
        B(command["text"])
        if command["text"]
        else None
    )

    if (
        command["type"] == "photo"
        and command["file_id"]
    ):
        await message.reply_photo(
            command["file_id"],
            caption=caption,
            parse_mode="HTML",
            has_spoiler=True,
            protect_content=is_protected_content(),
        )

    elif (
        command["type"] == "video"
        and command["file_id"]
    ):
        await message.reply_video(
            command["file_id"],
            caption=caption,
            parse_mode="HTML",
            has_spoiler=True,
            protect_content=is_protected_content(),
        )

    elif (
        command["type"] == "document"
        and command["file_id"]
    ):
        await message.reply_document(
            command["file_id"],
            caption=caption,
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )

    else:
        await message.reply_text(
            caption or B("..."),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )


# =========================================================
# ADMINS
# =========================================================

async def cmd_addadmin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    if (
        not context.args
        or not context.args[0].lstrip("-").isdigit()
    ):
        await update.message.reply_text(
            B("/addadmin &lt;user_id&gt;"),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    uid = int(context.args[0])

    if uid in CFG["admins"] or uid == OWNER_ID:
        await update.message.reply_text(
            B("This user is already an admin."),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
        return

    CFG["admins"].append(uid)
    save_config()

    await update.message.reply_text(
        B(f"✅ {uid} is now an admin."),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


async def cmd_deladmin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    if (
        not context.args
        or not context.args[0].lstrip("-").isdigit()
    ):
        return

    uid = int(context.args[0])

    if uid in CFG["admins"]:
        CFG["admins"].remove(uid)
        save_config()

        await update.message.reply_text(
            B(f"✅ {uid} removed from admins."),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )
    else:
        await update.message.reply_text(
            B("This user is not an admin."),
            parse_mode="HTML",
            protect_content=is_protected_content(),
        )


async def cmd_adminlist(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await admin_only(update):
        return

    lines = [f"👑 Owner: {OWNER_ID}"]

    for admin_id in CFG["admins"]:
        lines.append(f"🛡 Admin: {admin_id}")

    await update.message.reply_text(
        B("\n".join(lines)),
        parse_mode="HTML",
        protect_content=is_protected_content(),
    )


# =========================================================
# MAIN
# =========================================================

def main():
    if BOT_TOKEN == "PASTE_NEW_BOT_TOKEN_HERE":
        raise RuntimeError(
            "BOT_TOKEN set karo. Old exposed token ko use mat karo; "
            "BotFather se new token generate karke yahan paste karo."
        )

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    # -----------------------------------------------------
    # USER TRACKING
    # -----------------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.ALL,
            track_user,
        ),
        group=-1,
    )

    # -----------------------------------------------------
    # BASIC
    # -----------------------------------------------------

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("myid", cmd_myid))

    # -----------------------------------------------------
    # PRODUCT CALLBACKS
    # -----------------------------------------------------

    app.add_handler(
        CallbackQueryHandler(
            on_product_click,
            pattern=rf"^prod_([1-9]|1[0-2])$",
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            on_buy_click,
            pattern=rf"^buy_([1-9]|1[0-2])$",
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            on_back,
            pattern=r"^back_home$",
        )
    )

    # -----------------------------------------------------
    # APPROVE / REJECT
    # -----------------------------------------------------

    app.add_handler(
        CallbackQueryHandler(
            on_approve_reject,
            pattern=rf"^(ap|rj)_\d+_([1-9]|1[0-2])$",
        )
    )

    # -----------------------------------------------------
    # PAYMENT SCREENSHOT
    # -----------------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.PHOTO | filters.Document.IMAGE,
            on_screenshot,
        )
    )

    # -----------------------------------------------------
    # PANEL
    # -----------------------------------------------------

    app.add_handler(CommandHandler("panel", cmd_panel))
    app.add_handler(CommandHandler("protect", cmd_protect))

    # -----------------------------------------------------
    # START
    # -----------------------------------------------------

    app.add_handler(CommandHandler("setstart", cmd_setstart))
    app.add_handler(CommandHandler("addstartmedia", cmd_addstartmedia))
    app.add_handler(CommandHandler("startmedialist", cmd_startmedialist))
    app.add_handler(CommandHandler("delstartmedia", cmd_delstartmedia))

    # -----------------------------------------------------
    # PRODUCTS
    # -----------------------------------------------------

    app.add_handler(CommandHandler("setbtn", cmd_setbtn))
    app.add_handler(CommandHandler("setproduct", cmd_setproduct))
    app.add_handler(CommandHandler("addproductmedia", cmd_addproductmedia))
    app.add_handler(CommandHandler("productmedialist", cmd_productmedialist))
    app.add_handler(CommandHandler("delproductmedia", cmd_delproductmedia))
    app.add_handler(CommandHandler("setcaption", cmd_setcaption))
    app.add_handler(CommandHandler("setdelivery", cmd_setdelivery))

    # -----------------------------------------------------
    # PAYMENT
    # -----------------------------------------------------

    app.add_handler(CommandHandler("setqr", cmd_setqr))
    app.add_handler(CommandHandler("setpqr", cmd_setpqr))
    app.add_handler(CommandHandler("setupi", cmd_setupi))
    app.add_handler(CommandHandler("setpaytext", cmd_setpaytext))

    # -----------------------------------------------------
    # APPROVED SS CAPTION
    # -----------------------------------------------------

    app.add_handler(
        CommandHandler(
            "setbsscaption",
            cmd_setbsscaption,
        )
    )

    # -----------------------------------------------------
    # BROADCAST
    # -----------------------------------------------------

    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("broadcaststats", cmd_broadcaststats))

    # -----------------------------------------------------
    # CUSTOM COMMANDS
    # -----------------------------------------------------

    app.add_handler(CommandHandler("addcmd", cmd_addcmd))
    app.add_handler(CommandHandler("delcmd", cmd_delcmd))
    app.add_handler(CommandHandler("cmdlist", cmd_cmdlist))

    # -----------------------------------------------------
    # ADMINS
    # -----------------------------------------------------

    app.add_handler(CommandHandler("addadmin", cmd_addadmin))
    app.add_handler(CommandHandler("deladmin", cmd_deladmin))
    app.add_handler(CommandHandler("adminlist", cmd_adminlist))

    # -----------------------------------------------------
    # APPROVED SS BROADCAST BUTTON
    # -----------------------------------------------------

    app.add_handler(
        CallbackQueryHandler(
            on_broadcast_ss,
            pattern=r"^broadcast_ss_",
        )
    )

    # -----------------------------------------------------
    # CUSTOM COMMAND FALLBACK
    # -----------------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.COMMAND,
            on_custom_cmd,
        )
    )

    print("=" * 55)
    print("                    BOT IS RUNNING")
    print("=" * 55)
    print("🔒 Protected content: ENABLED")
    print("📢 Broadcast: ENABLED")
    print("🗑 Broadcast auto-delete: DISABLED")
    print("📝 Approved SS caption: ENABLED")
    print("🗑 Start auto-delete: 10 MINUTES")
    print("📦 Products: 12")
    print("🎨 Button styles: SUCCESS / PRIMARY / DANGER")
    print("🧾 Admin SS UI: FIXED + SPACED")
    print("⛔ Forward/Save restriction: ENABLED")
    print("Press Ctrl+C to stop.")
    print("=" * 55)

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
