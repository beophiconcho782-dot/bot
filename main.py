import logging
import time
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

# --- CẤU HÌNH ---
TELEGRAM_TOKEN = "8934224180:AAHJ3qXQ9fW81c8598Nv_ZyhCAAbYkkELwg"
ADMIN_PASSCODE = "8973095616"

BAD_WORDS = ["dm", "vl", "cc", "cl", "dcm", "lồn", "buồi", "óc chó", "đm", "vkl"]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Trạng thái cho ConversationHandler (Hệ thống Rep tin nhắn CSKH)
WAITING_REPLY_TEXT = 1

# 1. LỆNH /admin <mã_số>
async def set_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if not context.args or context.args[0] != ADMIN_PASSCODE:
        await update.message.reply_text("❌ **Sai mã số Admin!** Cú pháp: `/admin 8973095616`", parse_mode="Markdown")
        return

    admin_id = update.message.chat_id
    context.bot_data["owner_id"] = admin_id
    await update.message.reply_text("👑 **XÁC THỰC ADMIN THÀNH CÔNG!**", parse_mode="Markdown")

# 2. LỆNH /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    text = (
        "🤖 **BẢNG HƯỚNG DẪN CÁC LỆNH BOT**\n"
        "───────────────────────────────\n"
        "🔑 `/key` : Lấy link Get Key tự động\n"
        "💳 `/card` : Bảng giá Shop, Nạp & Check thẻ\n"
        "☁️ `/cloud` : Hướng dẫn Mua Cloud Phone / VPS\n"
        "🎮 `/napho` : Đặt Nạp hộ Play Together VNG\n"
        "💵 `/naptien` : Nạp tiền vào tài khoản (Chọn Menu)\n"
        "📞 `/alo <nội dung>` : Gửi tin nhắn hỗ trợ tới Admin\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# 3. LỆNH /napho <Tên gói>, <Giá tiền>, <Mã/Seri thẻ>
async def nap_ho_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    args_text = " ".join(context.args) if context.args else ""
    if not args_text or "," not in args_text:
        await update.message.reply_text(
            "⚠️ **Sai cú pháp!** Vui lòng nhập:\n"
            "`/napho Tên gói, Giá tiền, Seri - Mã thẻ`\n"
            "📌 *Ví dụ:* `/napho Gói Thỏ 100k, 100.000đ, Viettel - 100023 - 555231`",
            parse_mode="Markdown"
        )
        return

    user = update.message.from_user
    owner_id = context.bot_data.get("owner_id")

    await update.message.reply_text("✅ Yêu cầu **Nạp hộ Play Together VNG** của bạn đã được gửi tới Admin!")

    if owner_id:
        keyboard = [
            [
                InlineKeyboardButton("✅ Phê duyệt", callback_data=f"approve_napho_{user.id}"),
                InlineKeyboardButton("❌ Từ chối", callback_data=f"reject_napho_{user.id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        msg = (
            f"🎮 **YÊU CẦU NẠP HỘ PLAY TOGETHER VNG**\n"
            f"👤 **Khách hàng:** {user.full_name} (@{user.username if user.username else 'Không có'})\n"
            f"🆔 **ID:** `{user.id}`\n"
            f"📝 **Chi tiết:** {args_text}"
        )
        await context.bot.send_message(chat_id=owner_id, text=msg, parse_mode="Markdown", reply_markup=reply_markup)

# 4. LỆNH /naptien (MENU BỐT CHỌN SỐ TIỀN & THẺ)
async def nap_tien_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    keyboard = [
        [InlineKeyboardButton("💵 10.000 VNĐ", callback_data="amt_10k"), InlineKeyboardButton("💵 20.000 VNĐ", callback_data="amt_20k")],
        [InlineKeyboardButton("💵 50.000 VNĐ", callback_data="amt_50k"), InlineKeyboardButton("💵 100.000 VNĐ", callback_data="amt_100k")],
        [InlineKeyboardButton("💵 200.000 VNĐ", callback_data="amt_200k"), InlineKeyboardButton("💵 500.000 VNĐ", callback_data="amt_500k")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("💳 **BẢNG CHỌN MỆNH GIÁ NẠP TIỀN:**\nChọn số tiền bạn muốn nạp:", parse_mode="Markdown", reply_markup=reply_markup)

# Xử lý sự kiện bấm Nút Menu
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    owner_id = context.bot_data.get("owner_id")
    data = query.data

    # Bấm chọn số tiền nạp
    if data.startswith("amt_"):
        amount = data.replace("amt_", "").upper()
        context.user_data["pending_amount"] = amount
        await query.edit_message_text(
            f"✅ Bạn đã chọn mệnh giá **{amount}**.\n"
            f"📌 Vui lòng gửi theo cú pháp: `Tên Thẻ - Số Seri - Mã Pin` để hoàn tất nạp tiền!",
            parse_mode="Markdown"
        )

    # Admin bấm Phê Duyệt / Từ Chối
    elif data.startswith("approve_") or data.startswith("reject_"):
        action, _, target_user_id = data.partition("_")[2].rpartition("_")
        is_approve = data.startswith("approve_")
        target_id = int(data.split("_")[-1])

        status_text = "✅ **ĐÃ PHÊ DUYỆT TÀI KHỎAN/THẺ!**" if is_approve else "❌ **YÊU CẦU ĐÃ BỊ TỪ CHỐI!**"
        
        # Báo về cho Admin
        await query.edit_message_text(f"{query.message.text}\n\n👉 **Kết quả Admin:** {status_text}", parse_mode="Markdown")
        
        # Báo về cho Khách
        try:
            await context.bot.send_message(chat_id=target_id, text=f"🔔 **Thông báo từ Admin:**\n{status_text}", parse_mode="Markdown")
        except Exception:
            pass

    # Admin bấm Trả lời (Reply) khách hàng
    elif data.startswith("reply_user_"):
        target_id = int(data.replace("reply_user_", ""))
        context.user_data["reply_to_user_id"] = target_id
        await context.bot.send_message(chat_id=query.from_user.id, text=f"✍️ **Nhập nội dung bạn muốn gửi cho khách hàng (ID: `{target_id}`):**", parse_mode="Markdown")
        return WAITING_REPLY_TEXT

# 5. LỆNH /alo <Nội dung hỗ trợ>
async def alo_support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    msg_text = " ".join(context.args) if context.args else ""
    if not msg_text:
        await update.message.reply_text("⚠️ **Vui lòng nhập nội dung!** Cú pháp: `/alo Nội dung cần hỗ trợ`", parse_mode="Markdown")
        return

    user = update.message.from_user
    owner_id = context.bot_data.get("owner_id")

    await update.message.reply_text("📩 Tin nhắn CSKH của bạn đã được gửi tới Admin. Vui lòng chờ phản hồi!")

    if owner_id:
        keyboard = [[InlineKeyboardButton("💬 Trả lời (Reply)", callback_data=f"reply_user_{user.id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        admin_msg = (
            f"📞 **TIN NHẮN HỖ TRỢ /ALO MỚI**\n"
            f"👤 **Khách hàng:** {user.full_name} (@{user.username if user.username else 'Không có'})\n"
            f"🆔 **ID:** `{user.id}`\n"
            f"💬 **Nội dung:** {msg_text}"
        )
        await context.bot.send_message(chat_id=owner_id, text=admin_msg, parse_mode="Markdown", reply_markup=reply_markup)

# LÝ XỬ TRẢ LỜI TIN NHẮN TỪ ADMIN
async def handle_admin_reply_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return ConversationHandler.END

    target_id = context.user_data.get("reply_to_user_id")
    reply_content = update.message.text

    if target_id:
        try:
            # Bot gửi tin nhắn đại diện cho Admin
            await context.bot.send_message(
                chat_id=target_id,
                text=f"💬 **Trả lời từ CSKH Admin:**\n\n{reply_content}",
                parse_mode="Markdown"
            )
            await update.message.reply_text(f"✅ Đã gửi tin nhắn tới khách hàng (`{target_id}`) thành công!", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Lỗi gửi tin nhắn: {e}")

    context.user_data.pop("reply_to_user_id", None)
    return ConversationHandler.END

async def cancel_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Đã hủy thao tác trả lời.")
    return ConversationHandler.END

# Các lệnh cố định khác
async def send_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("🔑 **LINK GET KEY:**\nhttps://lamquan.site/keys/getkey?admin=Kissmod")

async def send_card_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("💳 **BẢNG GIÁ:**\n• 15k = 1T\n• 30k = 2T\n• 70k = 5T\n\n⚠️ Hệ thống tự động đang bảo trì. Vui lòng dùng lệnh `/naptien`!")

async def send_cloud_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("☁️ **MUA CLOUD:** Nhập cú pháp: Tên Cloud - Tên Thẻ - Seri - Mã Thẻ - Số Ngày Mua")

# Quản trị nhóm
async def moderate_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message
        if not message or not message.from_user or not message.chat or message.chat.type == "private":
            return

        user = message.from_user
        chat = message.chat
        user_id = user.id

        try:
            chat_member = await chat.get_member(user_id)
            if chat_member.status in ["administrator", "creator"]:
                return
        except Exception:
            pass

        text = message.text.lower() if message.text else ""
        words = text.split()

        action = None
        reason = ""

        if text and ("http://" in text or "https://" in text or "t.me/" in text):
            action = "mute"
            reason = "Gửi link quảng cáo/spam"
        elif any(word in words for word in BAD_WORDS):
            action = "mute"
            reason = "Chửi thề / Sử dụng từ ngữ thô tục"
        elif message.photo or message.video or message.document:
            action = "ban"
            reason = "Gửi file/ảnh/video trái phép"

        if action:
            try:
                await message.delete()
            except Exception:
                pass

            if action == "mute":
                try:
                    await chat.restrict_member(user_id, permissions=ChatPermissions(can_send_messages=False), until_date=int(time.time()) + 3600)
                    await chat.send_message(f"🚫 **CẤM CHAT:** [{user.full_name}](tg://user?id={user_id}) 1 TIẾNG!\n🛑 **Lý do:** {reason}.", parse_mode="Markdown")
                except Exception:
                    pass
            elif action == "ban":
                try:
                    await chat.ban_member(user_id)
                    await chat.send_message(f"🚨 **ĐÃ KICK BỎ:** [{user.full_name}](tg://user?id={user_id}) khỏi nhóm!\n🛑 **Lý do:** {reason}.", parse_mode="Markdown")
                except Exception:
                    pass
    except Exception as e:
        logging.error(f"Lỗi Moderation: {e}")

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # ConversationHandler dành cho tính năng Reply CSKH
    reply_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_callback, pattern="^reply_user_")],
        states={
            WAITING_REPLY_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_reply_text)]
        },
        fallbacks=[CommandHandler("cancel", cancel_reply)],
        per_chat=False
    )

    app.add_handler(CommandHandler("admin", set_admin))
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("key", send_key))
    app.add_handler(CommandHandler("card", send_card_info))
    app.add_handler(CommandHandler("cloud", send_cloud_info))
    app.add_handler(CommandHandler("napho", nap_ho_command))
    app.add_handler(CommandHandler("naptien", nap_tien_command))
    app.add_handler(CommandHandler("alo", alo_support_command))

    app.add_handler(reply_handler)
    app.add_handler(CallbackQueryHandler(button_callback))

    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND & ~filters.UpdateType.EDITED_MESSAGE, moderate_group))

    print("🤖 Bot Shop, Nạp Hộ & CSKH đã khởi chạy!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
python-telegram-bot

