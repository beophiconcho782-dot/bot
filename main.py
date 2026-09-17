import logging
import os
import time
import random
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

# --- WEB SERVER GIẢ CHẠY RENDER FREE ---
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is online 24/7!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# --- CẤU HÌNH BẢO MẬT BÍ MẬT ---
TELEGRAM_TOKEN = "8934224180:AAHJ3qXQ9fW81c8598Nv_ZyhCAAbYkkELwg"
ADMIN_PASSCODE = "726371882"  # MÃ ADMIN DUY NHẤT

# DANH SÁCH TỪ BẬY CẤM (AUTO BAN NẾU PHÁT HIỆN)
BAD_WORDS = ["dm", "đm", "dkm", "đkm", "cl", "clm", "vcl", "vkl", "đồ ngu", "óc chó", "bố mày", "chửi"]

# DANH SÁCH CÂU CHAT LINH TINH KHI BOT ĐƯỢC TAG HOẶC TRẢ LỜI TRONG NHÓM
BOT_RESPONSES = [
    "Dạ, em nghe đây ạ! Bạn cần hỗ trợ gì nhắn em nha ❤️",
    "Có em đây ạ! Muốn mua Acc hay nạp tiền bấm /start nha!",
    "Ai gọi em đó, có em đâyyy 🤖",
    "Dạ em là Bot hỗ trợ tự động 24/7, gõ /start để xem menu nhé!",
    "Chào bạn nha, chúc bạn một ngày vui vẻ! ✨",
    "Cần giao dịch uy tín cứ để Bot lo nhé 😎"
]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Các Trạng Thái Conversation Handler
WAITING_CARD_DETAILS = 1
WAITING_BUY_ACC_NOTE = 2
WAITING_SUPPORT_MSG = 3
WAITING_ADMIN_ACC_DELIVERY = 4
WAITING_DONGGOP_MSG = 5
WAITING_ADMIN_REPLY_MSG = 6

# --- QUẢN LÝ DỮ LIỆU BỘ NHỚ ---
def get_user_balance(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> int:
    if "balances" not in context.bot_data:
        context.bot_data["balances"] = {}
    return context.bot_data["balances"].get(user_id, 0)

def set_user_balance(context: ContextTypes.DEFAULT_TYPE, user_id: int, amount: int):
    if "balances" not in context.bot_data:
        context.bot_data["balances"] = {}
    context.bot_data["balances"][user_id] = amount

def record_user_info(context: ContextTypes.DEFAULT_TYPE, user):
    if not user: return
    if "user_logs" not in context.bot_data:
        context.bot_data["user_logs"] = {}
    
    uid = user.id
    if uid not in context.bot_data["user_logs"]:
        context.bot_data["user_logs"][uid] = {
            "name": user.full_name,
            "username": f"@{user.username}" if user.username else "(Không có)",
            "actions": []
        }
    else:
        context.bot_data["user_logs"][uid]["name"] = user.full_name
        context.bot_data["user_logs"][uid]["username"] = f"@{user.username}" if user.username else "(Không có)"

def add_user_log(context: ContextTypes.DEFAULT_TYPE, user, action: str):
    record_user_info(context, user)
    timestamp = time.strftime("%H:%M:%S %d/%m/%Y")
    context.bot_data["user_logs"][user.id]["actions"].append(f"[{timestamp}] {action}")

def get_user_restrictions(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    banned_list = context.bot_data.get("banned_users", [])
    muted_dict = context.bot_data.get("muted_users", {})
    
    if user_id in banned_list:
        return "BANNED", None

    if user_id in muted_dict:
        unmute_time = muted_dict[user_id]
        now = time.time()
        if now < unmute_time:
            remaining_mins = int((unmute_time - now) // 60) + 1
            return "MUTED", remaining_mins
        else:
            del context.bot_data["muted_users"][user_id]

    return "NORMAL", None

async def check_ban_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if not user: return True
    
    record_user_info(context, user)
    status, remaining = get_user_restrictions(context, user.id)

    if status == "BANNED":
        msg = "🚫 Tài khoản của bạn đã bị **BAND VĨNH VIỄN** khỏi hệ thống bot!"
        if update.message: await update.message.reply_text(msg, parse_mode="Markdown")
        elif update.callback_query: await update.callback_query.answer("🚫 Bạn đã bị BAND!", show_alert=True)
        return False
    elif status == "MUTED":
        msg = f"⏳ Bạn đang bị **CẤM CHAT**! Thời gian cấm còn lại: **{remaining} phút**."
        if update.message: await update.message.reply_text(msg, parse_mode="Markdown")
        elif update.callback_query: await update.callback_query.answer(f"⏳ Cấm chat còn {remaining} phút!", show_alert=True)
        return False

    return True

async def notify_all_admins(context: ContextTypes.DEFAULT_TYPE, message_text: str, reply_markup=None):
    admin_list = context.bot_data.get("admin_list", set())
    if admin_list:
        for admin_id in admin_list:
            try:
                await context.bot.send_message(chat_id=admin_id, text=message_text, parse_mode="Markdown", reply_markup=reply_markup)
            except Exception as e:
                logging.error(f"Lỗi gửi tới Admin {admin_id}: {e}")

# 1. LỆNH XÁC MINH ADMIN
async def set_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_ban_middleware(update, context): return
    if not update.message: return
    
    user = update.message.from_user
    args = context.args

    if not args or args[0] != ADMIN_PASSCODE:
        await update.message.reply_text("❌ Lệnh hoặc Mã xác thực Admin không hợp lệ!")
        return
    
    if "admin_list" not in context.bot_data:
        context.bot_data["admin_list"] = set()
    
    context.bot_data["admin_list"].add(user.id)
    
    await update.message.reply_text(
        f"👑 **XÁC THỰC ADMIN THÀNH CÔNG!**\n"
        f"Tài khoản **{user.full_name}** (ID: `{user.id}`) đã được xác nhận là Admin.",
        parse_mode="Markdown"
    )

# LỆNH KICK ĐUỔI THÀNH VIÊN KHỎI NHÓM
async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_list = context.bot_data.get("admin_list", set())
    user_id = update.message.from_user.id

    if user_id not in admin_list:
        await update.message.reply_text("❌ Bạn không có quyền dùng lệnh /kick!")
        return

    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text("❌ Lệnh này chỉ dùng được trong Nhóm/Group!")
        return

    target_user_id = None
    if update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
    elif context.args:
        try:
            target_user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ ID không hợp lệ!")
            return

    if target_user_id:
        try:
            await chat.ban_member(user_id=target_user_id)
            await update.message.reply_text(f"🚀 Đã đuổi (kick) thành công thành viên (ID: `{target_user_id}`) khỏi nhóm!", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Không thể kick thành viên này. Hãy đảm bảo Bot đã được cấp quyền Admin Nhóm!\nLỗi: {e}")
    else:
        await update.message.reply_text("📌 Hãy reply tin nhắn của người cần kick hoặc gõ: `/kick [ID_Nguoi_Dung]`", parse_mode="Markdown")

# 2. LỆNH /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_ban_middleware(update, context): return
    if not update.message: return
    
    user = update.message.from_user
    add_user_log(context, user, "Bấm /start")
    balance = get_user_balance(context, user.id)

    text = (
        f"🤖 **HỆ THỐNG BOT TỰ ĐỘNG**\n"
        f"👤 Khách hàng: **{user.full_name}**\n"
        f"💰 Số dư tài khoản: **{balance:,} VNĐ**\n"
        f"───────────────────────────────\n"
        f"💳 `/naptien` : Nạp tiền / Đặt thẻ chiết khấu\n"
        f"🎮 `/muaacc` : Chọn mua các loại Acc Play Together\n"
        f"📞 `/support` : Gửi tin nhắn hỗ trợ Admin\n"
        f"💡 `/donggop` : Gửi ý kiến đóng góp cho Admin"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# 3. NẠP TIỀN
async def nap_tien_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_ban_middleware(update, context): return
    if not update.message: return

    user = update.message.from_user
    add_user_log(context, user, "Mở /naptien")
    balance = get_user_balance(context, user.id)

    keyboard = [
        [InlineKeyboardButton("💳 15k / 1 Tốc độ", callback_data="cardrate_15k"), InlineKeyboardButton("💳 50k / 3 Tốc độ", callback_data="cardrate_50k")],
        [InlineKeyboardButton("💳 70k / 5 Tốc độ", callback_data="cardrate_70k")],
        [InlineKeyboardButton("🔴 Viettel", callback_data="cardtype_viettel"), InlineKeyboardButton("🔵 Vina", callback_data="cardtype_vina"), InlineKeyboardButton("🟡 Mobi", callback_data="cardtype_mobi")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = (
        f"💳 **DANH MỤC NẠP TIỀN & ĐẶT THẺ**\n"
        f"💰 Số dư hiện tại: **{balance:,} VNĐ**\n\n"
        f"📌 **Bảng giá đặt thẻ:**\n"
        f"• 15k = 1T | 50k = 3T | 70k = 5T\n\n"
        f"👇 *Chọn loại thẻ bên dưới để nhập Seri & Mã thẻ:* "
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)

async def card_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    card_type = query.data.replace("cardtype_", "").upper()
    context.user_data["selected_card_type"] = card_type

    await query.edit_message_text(
        f"📥 Bạn đã chọn loại thẻ: **{card_type}**\n\n"
        f"Vui lòng nhập: **[Mệnh giá] [Số Seri] [Mã Thẻ]**\n"
        f"📌 *Ví dụ:* `50k 1000234567 555231890`",
        parse_mode="Markdown"
    )
    return WAITING_CARD_DETAILS

async def process_card_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    card_info = update.message.text
    card_type = context.user_data.get("selected_card_type", "LOẠI THẺ KHÔNG XÁC ĐỊNH")
    
    add_user_log(context, user, f"Nạp thẻ {card_type}: {card_info}")
    await update.message.reply_text("✅ Yêu cầu nạp thẻ đã được gửi lên Ban Quản Trị! Vui lòng chờ duyệt.")

    keyboard = [
        [
            InlineKeyboardButton("✅ Duyệt Nạp (+50k)", callback_data=f"approve_card_{user.id}"),
            InlineKeyboardButton("❌ Từ Chối", callback_data=f"reject_card_{user.id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    admin_msg = (
        f"💳 **YÊU CẦU NẠP THẺ MỚI**\n"
        f"👤 **Khách gửi:** {user.full_name} (@{user.username if user.username else 'Không có'})\n"
        f"🆔 **ID Khách:** `{user.id}`\n"
        f"🏷 **Loại thẻ:** {card_type}\n"
        f"📝 **Thông tin:** `{card_info}`"
    )

    await notify_all_admins(context, admin_msg, reply_markup)
    return ConversationHandler.END

# 4. CHỨC NĂNG MUA ACC
async def mua_acc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_ban_middleware(update, context): return
    if not update.message: return

    user = update.message.from_user
    add_user_log(context, user, "Mở /muaacc")
    balance = get_user_balance(context, user.id)

    keyboard = [
        [InlineKeyboardButton("🔥 Acc Full Sự Kiện (Full SK)", callback_data="buycat_full_sk")],
        [InlineKeyboardButton("🌾 Acc Cày Full Sự Kiện", callback_data="buycat_cay_full_sk")],
        [InlineKeyboardButton("🎣 Acc Full Cần Quỷ Vương (QV)", callback_data="buycat_full_can_qv")],
        [InlineKeyboardButton("💎 Acc Nhiều KC / TS / Đã Nạp", callback_data="buycat_nhieu_kc_ts")],
        [InlineKeyboardButton("👑 Acc VIP (Mức Giá 1M - 2M)", callback_data="buycat_acc_1_2m")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🎮 **DANH MỤC MUA ACC PLAY TOGETHER**\n"
        f"💰 Số dư của bạn: **{balance:,} VNĐ**\n\n"
        f"👇 *Vui lòng chọn loại Acc bạn muốn đặt mua bên dưới:*",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def buy_acc_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    cat_key = query.data.replace("buycat_", "")
    cat_names = {
        "full_sk": "Acc Full Sự Kiện",
        "cay_full_sk": "Acc Cày Full Sự Kiện",
        "full_can_qv": "Acc Full Cần Quỷ Vương",
        "nhieu_kc_ts": "Acc Nhiều KC / Nhiều TS / Đã Nạp",
        "acc_1_2m": "Acc VIP Giá 1M - 2M"
    }
    selected_name = cat_names.get(cat_key, "Acc Yêu Cầu")
    context.user_data["selected_acc_cat"] = selected_name

    add_user_log(context, user, f"Chọn danh mục Acc: {selected_name}")

    keyboard_admin = [[InlineKeyboardButton("📦 Giao Acc & Trừ Tiền", callback_data=f"sell_acc_{user.id}")]]
    admin_msg = (
        f"🎮 **YÊU CẦU DỰ MUA ACC MỚI!**\n"
        f"👤 **Khách hàng:** {user.full_name} (@{user.username if user.username else 'Không có'})\n"
        f"🆔 **ID:** `{user.id}`\n"
        f"💰 **Số dư hiện tại:** {get_user_balance(context, user.id):,} VNĐ\n"
        f"🏷 **Loại Acc chọn:** *{selected_name}*"
    )
    await notify_all_admins(context, admin_msg, InlineKeyboardMarkup(keyboard_admin))

    await query.edit_message_text(
        f"📌 Bạn đã chọn: **{selected_name}**\n\n"
        f"✅ Yêu cầu đã được gửi tới Admin!\n"
        f"💡 *Nếu muốn nhắn thêm yêu cầu/ghi chú riêng cho Admin, bạn có thể dùng lệnh:* `/yk [nội dung]`",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def yk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_ban_middleware(update, context): return
    if not update.message: return

    user = update.message.from_user
    msg_text = " ".join(context.args) if context.args else ""
    if not msg_text:
        await update.message.reply_text("❌ Vui lòng nhập nội dung yêu cầu! Cú pháp: `/yk [Nội dung yêu cầu]`", parse_mode="Markdown")
        return

    add_user_log(context, user, f"Gửi ý kiến /yk: {msg_text}")
    await update.message.reply_text("✨ Yêu cầu ghi chú của bạn đã được gửi trực tiếp tới Admin!")

    keyboard = [
        [
            InlineKeyboardButton("💬 Trả Lời Khách Hàng", callback_data=f"reply_user_{user.id}"),
            InlineKeyboardButton("📦 Giao Acc", callback_data=f"sell_acc_{user.id}")
        ]
    ]
    admin_msg = (
        f"📝 **GHI CHÚ / YÊU CẦU MUA ACC TỪ KHÁCH**\n"
        f"👤 **Khách:** {user.full_name} (@{user.username if user.username else 'Không có'})\n"
        f"🆔 **ID:** `{user.id}`\n"
        f"💬 **Nội dung:** {msg_text}"
    )
    await notify_all_admins(context, admin_msg, InlineKeyboardMarkup(keyboard))

# 5. GỬI Ý KIẾN ĐÓNG GÓP
async def dong_gop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_ban_middleware(update, context): return
    if not update.message: return

    user = update.message.from_user
    add_user_log(context, user, "Mở /donggop")

    msg_text = " ".join(context.args) if context.args else ""
    if msg_text:
        await send_donggop_to_admin(update, context, user, msg_text)
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "💡 **GỬI Ý KIẾN ĐÓNG GÓP TỚI ADMIN**\n\n"
            "Vui lòng nhập nội dung ý kiến/góp ý của bạn bên dưới:",
            parse_mode="Markdown"
        )
        return WAITING_DONGGOP_MSG

async def process_donggop_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    msg_text = update.message.text
    await send_donggop_to_admin(update, context, user, msg_text)
    return ConversationHandler.END

async def send_donggop_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user, msg_text: str):
    add_user_log(context, user, f"Đóng góp ý kiến: {msg_text}")
    await update.message.reply_text("✨ Cảm ơn bạn! Ý kiến đóng góp đã được gửi tới Ban Quản Trị.")

    keyboard = [[InlineKeyboardButton("💬 Trả Lời Khách Hàng", callback_data=f"reply_user_{user.id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    admin_msg = (
        f"💡 **TIN NHẮN ĐÓNG GÓP Ý KIẾN MỚI**\n"
        f"👤 **Khách gửi:** {user.full_name} (@{user.username if user.username else 'Không có'})\n"
        f"🆔 **ID:** `{user.id}`\n"
        f"💬 **Nội dung đóng góp:** {msg_text}"
    )
    await notify_all_admins(context, admin_msg, reply_markup)

# 6. SUPPORT
async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_ban_middleware(update, context): return
    if not update.message: return

    user = update.message.from_user
    add_user_log(context, user, "Mở /support")

    msg_text = " ".join(context.args) if context.args else ""
    if msg_text:
        await send_support_to_admin(update, context, user, msg_text)
        return ConversationHandler.END
    else:
        await update.message.reply_text("📞 **Vui lòng nhập nội dung bạn cần hỗ trợ gửi tới Admin:**", parse_mode="Markdown")
        return WAITING_SUPPORT_MSG

async def process_support_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    msg_text = update.message.text
    await send_support_to_admin(update, context, user, msg_text)
    return ConversationHandler.END

async def send_support_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user, msg_text: str):
    add_user_log(context, user, f"Gửi hỗ trợ: {msg_text}")
    await update.message.reply_text("✅ Tin nhắn hỗ trợ đã được gửi tới Admin!")

    keyboard = [[InlineKeyboardButton("💬 Trả Lời Khách Hàng", callback_data=f"reply_user_{user.id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    admin_msg = (
        f"📞 **TIN NHẮN HỖ TRỢ / SUPPORT**\n"
        f"👤 **Khách:** {user.full_name} (@{user.username if user.username else 'Không có'})\n"
        f"🆔 **ID:** `{user.id}`\n"
        f"💬 **Nội dung:** {msg_text}"
    )
    await notify_all_admins(context, admin_msg, reply_markup)

# 7. XỬ LÝ TỰ ĐỘNG CHAT, LỌC TỪ BẬY (AUTO BAN) & TRUYỀN TIN NHẮN TỚI ADMIN
async def forward_all_user_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_ban_middleware(update, context): return
    if not update.message or not update.message.text: return

    user = update.message.from_user
    chat = update.effective_chat
    user_text = update.message.text.lower()
    admin_list = context.bot_data.get("admin_list", set())

    # --- A. KIỂM TRA & AUTO BAN NẾU NÓI TỪ BẬY ---
    if any(bad_word in user_text for bad_word in BAD_WORDS):
        if "banned_users" not in context.bot_data: context.bot_data["banned_users"] = []
        if user.id not in context.bot_data["banned_users"]:
            context.bot_data["banned_users"].append(user.id)

        try:
            await update.message.delete()
        except Exception:
            pass

        if chat.type != "private":
            try:
                await chat.ban_member(user_id=user.id)
            except Exception:
                pass

        alert_msg = f"🚫 **HỆ THỐNG AUTO BAN!**\nKhách **{user.full_name}** (ID: `{user.id}`) đã bị **BAND VĨNH VIỄN** do sử dụng ngôn từ vi phạm quy chuẩn!"
        await context.bot.send_message(chat_id=chat.id, text=alert_msg, parse_mode="Markdown")
        await notify_all_admins(context, f"🚨 **THÔNG BÁO AUTO BAN:**\n{alert_msg}")
        return

    # --- B. XỬ LÝ TỰ ĐỘNG CHAT TRONG NHÓM KHI ĐƯỢC TAG HOẶC REPLY ---
    bot_username = context.bot.username
    is_mentioned = bot_username and f"@{bot_username.lower()}" in user_text
    is_replied = update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id

    if chat.type != "private":
        if is_mentioned or is_replied:
            reply_txt = random.choice(BOT_RESPONSES)
            await update.message.reply_text(reply_txt)
            return

    if user.id in admin_list:
        return

    # --- C. KHÁCH CHAT CÁ NHÂN -> CHUYỂN TỚI ADMIN ---
    if chat.type == "private":
        add_user_log(context, user, f"Nhắn tin: {update.message.text}")

        keyboard = [
            [
                InlineKeyboardButton("💬 Trả Lời Khách Hàng", callback_data=f"reply_user_{user.id}"),
                InlineKeyboardButton("🛑 Quản Lý Ban ID Trực Tiếp", callback_data=f"manage_user_{user.id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        admin_msg = (
            f"📩 **TIN NHẮN MỚI TỪ KHÁCH HÀNG**\n"
            f"👤 **Tên:** {user.full_name} (@{user.username if user.username else 'Không có'})\n"
            f"🆔 **ID:** `{user.id}`\n"
            f"💬 **Nội dung:** {update.message.text}"
        )
        await notify_all_admins(context, admin_msg, reply_markup)

# 8. HÀM BẤM NÚT MUA ACC & TRẢ LỜI CỦA ADMIN
async def admin_sell_acc_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    target_user_id = int(query.data.replace("sell_acc_", ""))
    context.user_data["target_sell_user_id"] = target_user_id

    box_text = (
        f"📦 **KHUNG PHÊ DUYỆT & GIAO ACC (ID KHÁCH: `{target_user_id}`)**\n"
        f"───────────────────────────────\n"
        f"Vui lòng gửi tin nhắn theo cú pháp chuẩn sau:\n\n"
        f"`[Số_Tiền] [Tài_Khoản] [Mật_Khẩu]`\n\n"
        f"📌 *Ví dụ mẫu:* `50000 acc_vip_123 mk_baomat_456`"
    )
    await context.bot.send_message(chat_id=query.from_user.id, text=box_text, parse_mode="Markdown")
    return WAITING_ADMIN_ACC_DELIVERY

async def process_admin_delivery_acc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_text = update.message.text
    target_user_id = context.user_data.get("target_sell_user_id")

    try:
        parts = admin_text.strip().split()
        if len(parts) < 3:
            await update.message.reply_text("❌ Nhập thiếu thông tin! Vui lòng nhập đủ: `[Số_Tiền] [Tài_Khoản] [Mật_Khẩu]`")
            return WAITING_ADMIN_ACC_DELIVERY

        price = int(parts[0])
        acc_name = parts[1]
        acc_pass = " ".join(parts[2:])

        current_bal = get_user_balance(context, target_user_id)
        if current_bal < price:
            await update.message.reply_text(f"❌ Khách không đủ tiền! Số dư khách: {current_bal:,} VNĐ, Giá Acc: {price:,} VNĐ")
            return ConversationHandler.END

        set_user_balance(context, target_user_id, current_bal - price)

        user_msg = (
            f"🎉 **BẠN ĐÃ MUA ACC THÀNH CÔNG!**\n"
            f"💰 Đã trừ: **{price:,} VNĐ** (Số dư còn: {get_user_balance(context, target_user_id):,} VNĐ)\n\n"
            f"📦 **THÔNG TIN TÀI KHOẢN:**\n"
            f"👤 **Tên tài khoản (TK):** `{acc_name}`\n"
            f"🔑 **Mật khẩu (MK):** `{acc_pass}`"
        )
        await context.bot.send_message(chat_id=target_user_id, text=user_msg, parse_mode="Markdown")

        await update.message.reply_text(
            f"✅ **ĐÃ GIAO ACC THÀNH CÔNG!**\n"
            f"👤 ID Khách: `{target_user_id}`\n"
            f"💵 Đã trừ: **{price:,} VNĐ**\n"
            f"🔒 *Thông tin tài khoản/mật khẩu đã được gửi trực tiếp cho khách.*"
        )
    except ValueError:
        await update.message.reply_text("❌ Giá tiền phải là số nguyên (Ví dụ: 50000). Vui lòng nhập lại!")
        return WAITING_ADMIN_ACC_DELIVERY

    return ConversationHandler.END

async def admin_reply_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    target_user_id = int(query.data.replace("reply_user_", ""))
    context.user_data["target_reply_user_id"] = target_user_id

    await context.bot.send_message(
        chat_id=query.from_user.id,
        text=f"✍️ **Nhập nội dung phản hồi gửi tới Khách hàng (ID: `{target_user_id}`):**\n*(Hoặc gõ lệnh `/rep {target_user_id} nội dung`)*",
        parse_mode="Markdown"
    )
    return WAITING_ADMIN_REPLY_MSG

async def process_admin_reply_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_text = update.message.text
    target_user_id = context.user_data.get("target_reply_user_id")

    if target_user_id:
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"📩 **PHẢN HỒI TỪ BAN QUẢN TRỊ ADMIN:**\n\n{admin_text}",
                parse_mode="Markdown"
            )
            await update.message.reply_text(f"✅ Đã gửi phản hồi thành công tới khách hàng (ID: `{target_user_id}`)!")
        except Exception as e:
            await update.message.reply_text(f"❌ Không thể gửi tin nhắn tới khách. Lỗi: {e}")

    return ConversationHandler.END

async def rep_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_list = context.bot_data.get("admin_list", set())
    if update.message.from_user.id not in admin_list:
        await update.message.reply_text("❌ Bạn không có quyền sử dụng lệnh /rep!")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("❌ Cú pháp sai! Vui lòng gõ: `/rep [ID_Khách] [Nội_Dung]`\n📌 Ví dụ: `/rep 897385616 Shop đã nhận yêu cầu nhé!`", parse_mode="Markdown")
        return

    try:
        target_id = int(context.args[0])
        reply_content = " ".join(context.args[1:])

        await context.bot.send_message(
            chat_id=target_id,
            text=f"📩 **PHẢN HỒI TỪ BAN QUẢN TRỊ ADMIN:**\n\n{reply_content}",
            parse_mode="Markdown"
        )
        await update.message.reply_text(f"✅ Đã gửi tin nhắn tới ID khách `{target_id}` thành công!", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ ID Khách phải là một dãy số nguyên!")
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi gửi tin nhắn: {e}")

# 9. LỆNH /ban
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_list = context.bot_data.get("admin_list", set())
    if update.message.from_user.id not in admin_list:
        await update.message.reply_text("❌ Bạn không có quyền sử dụng lệnh /ban!")
        return

    if context.args:
        try:
            target_id = int(context.args[0])
            await send_user_ban_card(update, context, target_id)
            return
        except ValueError:
            await update.message.reply_text("❌ ID người dùng phải là con số. Ví dụ: `/ban 897385616`", parse_mode="Markdown")
            return

    logs = context.bot_data.get("user_logs", {})
    if not logs:
        await update.message.reply_text("📁 Chưa có dữ liệu khách hàng nào từng nhắn tin cho Bot từ lúc khởi động.\n📌 Bạn có thể dùng cú pháp `/ban [ID_Khách]` để ban trực tiếp!", parse_mode="Markdown")
        return

    await update.message.reply_text("🛑 **DANH SÁCH KHÁCH HÀNG - QUẢN LÝ BAND / CẤM CHAT:**")

    for uid in list(logs.keys()):
        await send_user_ban_card(update, context, uid)

async def send_user_ban_card(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: int):
    logs = context.bot_data.get("user_logs", {})
    udata = logs.get(uid, {"name": "Khách chưa lưu tên", "username": "(Không có)"})

    status, remaining = get_user_restrictions(context, uid)

    status_text = "🟢 Bình thường"
    if status == "BANNED":
        status_text = "🔴 **ĐÃ BỊ BAND VĨNH VIỄN**"
    elif status == "MUTED":
        status_text = f"⏳ **ĐANG BỊ CẤM CHAT** ({remaining} phút)"

    keyboard = []
    if status != "NORMAL":
        keyboard.append([InlineKeyboardButton("🟢 MỜ BAND / MỞ CẤM CHAT", callback_data=f"unban_action_{uid}")])
    else:
        keyboard.append([
            InlineKeyboardButton("🚫 Band Vĩnh Viễn", callback_data=f"ban_perm_{uid}"),
            InlineKeyboardButton("⏰ Cấm Chat Min", callback_data=f"mute_menu_{uid}")
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = (
        f"👤 **Khách:** {udata['name']}\n"
        f"🏷 **Username:** {udata['username']}\n"
        f"🆔 **ID Khách:** `{uid}`\n"
        f"💰 **Số dư:** {get_user_balance(context, uid):,} VNĐ\n"
        f"📌 **Trạng thái:** {status_text}"
    )
    
    if update.message:
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id=update.effective_user.id, text=msg, parse_mode="Markdown", reply_markup=reply_markup)

# 10. XỬ LÝ CÁC NÚT BẤM BAND / CẤM CHAT
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("approve_card_") or data.startswith("reject_card_"):
        user_id = int(data.split("_")[-1])
        is_approve = data.startswith("approve_card_")

        if is_approve:
            set_user_balance(context, user_id, get_user_balance(context, user_id) + 50000)
            status_txt = "✅ **THẺ ĐÚNG!** Đã cộng +50.000 VNĐ vào tài khoản."
        else:
            status_txt = "❌ **THẺ SAI HOẶC ĐÃ DÙNG!** Yêu cầu nạp bị từ chối."

        await query.edit_message_text(f"{query.message.text}\n\n👉 **Kết quả:** {status_txt}", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=user_id, text=f"🔔 **Thông báo nạp thẻ:**\n{status_txt}", parse_mode="Markdown")
        except Exception:
            pass

    elif data.startswith("manage_user_"):
        target_id = int(data.replace("manage_user_", ""))
        await send_user_ban_card(update, context, target_id)

    elif data.startswith("ban_perm_"):
        target_id = int(data.replace("ban_perm_", ""))
        if "banned_users" not in context.bot_data: context.bot_data["banned_users"] = []
        if target_id not in context.bot_data["banned_users"]:
            context.bot_data["banned_users"].append(target_id)
        
        keyboard = [[InlineKeyboardButton("🟢 MỜ BAND / MỞ CẤM CHAT", callback_data=f"unban_action_{target_id}")]]
        await query.edit_message_text(f"{query.message.text}\n\n🛑 **KẾT QUẢ:** Đã **BAND VĨNH VIỄN** người dùng ID: `{target_id}`", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("unban_action_"):
        target_id = int(data.replace("unban_action_", ""))
        if "banned_users" in context.bot_data and target_id in context.bot_data["banned_users"]:
            context.bot_data["banned_users"].remove(target_id)
        if "muted_users" in context.bot_data and target_id in context.bot_data["muted_users"]:
            del context.bot_data["muted_users"][target_id]
        
        keyboard = [[
            InlineKeyboardButton("🚫 Band Vĩnh Viễn", callback_data=f"ban_perm_{target_id}"),
            InlineKeyboardButton("⏰ Cấm Chat Min", callback_data=f"mute_menu_{target_id}")
        ]]
        await query.edit_message_text(f"{query.message.text}\n\n🟢 **KẾT QUẢ:** Đã **MỞ BAND / MỞ KHÓA CHAT** cho ID: `{target_id}`", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("mute_menu_"):
        target_id = int(data.replace("mute_menu_", ""))
        keyboard = [
            [
                InlineKeyboardButton("⏱ 15 Phút", callback_data=f"apply_mute_{target_id}_15"),
                InlineKeyboardButton("⏱ 60 Phút", callback_data=f"apply_mute_{target_id}_60"),
                InlineKeyboardButton("⏱ 24 Giờ", callback_data=f"apply_mute_{target_id}_1440")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"{query.message.text}\n\n⏰ **Chọn thời gian Cấm Chat:**", parse_mode="Markdown", reply_markup=reply_markup)

    elif data.startswith("apply_mute_"):
        parts = data.split("_")
        target_id = int(parts[2])
        mins = int(parts[3])

        if "muted_users" not in context.bot_data: context.bot_data["muted_users"] = {}
        context.bot_data["muted_users"][target_id] = time.time() + (mins * 60)

        keyboard = [[InlineKeyboardButton("🟢 MỜ BAND / MỞ CẤM CHAT", callback_data=f"unban_action_{target_id}")]]
        await query.edit_message_text(f"{query.message.text}\n\n⏳ **KẾT QUẢ:** Đã **CẤM CHAT** ID `{target_id}` trong **{mins} phút**!", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# 11. DASHBOARD QUẢN LÝ CHUNG
async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_list = context.bot_data.get("admin_list", set())
    if update.message.from_user.id not in admin_list:
        await update.message.reply_text("❌ Bạn không có quyền truy cập!")
        return

    logs = context.bot_data.get("user_logs", {})
    if not logs:
        await update.message.reply_text("Chưa có dữ liệu người dùng tương tác.")
        return

    await update.message.reply_text("📊 **DANH SÁCH TẢI KHOẢN KHÁCH HÀNG:**")
    for uid, udata in logs.items():
        status, remaining = get_user_restrictions(context, uid)
        
        status_text = "🟢 Bình thường"
        if status == "BANNED": status_text = "🔴 Đã Bị Band"
        elif status == "MUTED": status_text = f"⏳ Đang Cấm Chat ({remaining}p)"

        action_history = "\n".join(udata["actions"][-5:])
        msg = (
            f"👤 **Khách:** {udata['name']} ({udata['username']})\n"
            f"🆔 **ID:** `{uid}`\n"
            f"💰 **Số dư:** {get_user_balance(context, uid):,} VNĐ\n"
            f"🔴 **Trạng thái:** {status_text}\n"
            f"📝 **Lịch sử thao tác:**\n{action_history}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Đã hủy thao tác.")
    return ConversationHandler.END

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    card_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(card_type_callback, pattern="^cardtype_")],
        states={WAITING_CARD_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_card_input)]},
        fallbacks=[CommandHandler("cancel", cancel_handler)],
        per_message=True
    )

    support_conv = ConversationHandler(
        entry_points=[CommandHandler("support", support_command)],
        states={WAITING_SUPPORT_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_support_input)]},
        fallbacks=[CommandHandler("cancel", cancel_handler)],
        per_message=True
    )

    donggop_conv = ConversationHandler(
        entry_points=[CommandHandler("donggop", dong_gop_command)],
        states={WAITING_DONGGOP_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_donggop_input)]},
        fallbacks=[CommandHandler("cancel", cancel_handler)],
        per_message=True
    )

    admin_reply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_reply_user_callback, pattern="^reply_user_")],
        states={WAITING_ADMIN_REPLY_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_reply_msg)]},
        fallbacks=[CommandHandler("cancel", cancel_handler)],
        per_message=True
    )

    admin_delivery_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_sell_acc_callback, pattern="^sell_acc_")],
        states={WAITING_ADMIN_ACC_DELIVERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_delivery_acc)]},
        fallbacks=[CommandHandler("cancel", cancel_handler)],
        per_message=True
    )

    app.add_handler(CommandHandler("admin", set_admin))
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("naptien", nap_tien_command))
    app.add_handler(CommandHandler("muaacc", mua_acc_command))
    app.add_handler(CommandHandler("dashboard", dashboard_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("kick", kick_command))
    app.add_handler(CommandHandler("rep", rep_command))
    app.add_handler(CommandHandler("yk", yk_command))

    app.add_handler(card_conv)
    app.add_handler(support_conv)
    app.add_handler(donggop_conv)
    app.add_handler(admin_reply_conv)
    app.add_handler(admin_delivery_conv)

    app.add_handler(CallbackQueryHandler(buy_acc_category_callback, pattern="^buycat_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, forward_all_user_messages))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot Telegram nâng cấp hoàn tất đã sẵn sàng!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
    python-telegram-bot
