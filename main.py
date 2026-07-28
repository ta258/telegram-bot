Import os
import time
import uuid
import smtplib
import threading
import sqlite3
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import telebot
from telebot import types

# ضع توكن البوت الخاص بك هنا
TOKEN = '8893480234:AAEUWUzrtNudRvL2VuFLouYWlcs33IBRUWQ'
bot = telebot.TeleBot(TOKEN)

IMAGE_DIR = "temp_images"
if not os.path.exists(IMAGE_DIR):
    os.makedirs(IMAGE_DIR)

DB_NAME = "bot_data.db"

# --- إدارة قاعدة البيانات (SQLite) ---

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                senders TEXT,
                recipients TEXT,
                subject TEXT,
                message TEXT,
                count INTEGER,
                delay INTEGER,
                smart_delays TEXT,
                image_path TEXT
            )
        ''')
        conn.commit()

def save_user_data(user_id, data):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (user_id, senders, recipients, subject, message, count, delay, smart_delays, image_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                senders=excluded.senders,
                recipients=excluded.recipients,
                subject=excluded.subject,
                message=excluded.message,
                count=excluded.count,
                delay=excluded.delay,
                smart_delays=excluded.smart_delays,
                image_path=excluded.image_path
        ''', (
            user_id,
            json.dumps(data["senders"], ensure_ascii=False),
            json.dumps(data["recipients"], ensure_ascii=False),
            data["subject"],
            data["message"],
            data["count"],
            data["delay"],
            json.dumps(data["smart_delays"]),
            data["image_path"]
        ))
        conn.commit()

def get_user_data(user_id):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT senders, recipients, subject, message, count, delay, smart_delays, image_path FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        
        if row:
            return {
                "senders": json.loads(row[0]),
                "recipients": json.loads(row[1]),
                "subject": row[2],
                "message": row[3],
                "count": row[4],
                "delay": row[5],
                "smart_delays": json.loads(row[6]),
                "image_path": row[7]
            }
        else:
            default_data = {
                "senders": [],
                "recipients": [],
                "subject": "بدون موضوع",
                "message": "فارغ",
                "count": 1,
                "delay": 0,
                "smart_delays": [],
                "image_path": None
            }
            save_user_data(user_id, default_data)
            return default_data

# --- الواجهة والأزرار ---

def build_inline_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    btn1 = types.InlineKeyboardButton("عرض معلوماتي", callback_data="show_info")
    btn2 = types.InlineKeyboardButton("المشاركه", callback_data="share")
    btn3 = types.InlineKeyboardButton("CH", callback_data="channel")
    btn4 = types.InlineKeyboardButton("ابدا الارسال", callback_data="start_sending_menu")
    btn5 = types.InlineKeyboardButton("اضافه المرسل", callback_data="add_sender")
    btn6 = types.InlineKeyboardButton("اضافه المستلم", callback_data="add_recipient")
    btn7 = types.InlineKeyboardButton("عرض ايملاتي", callback_data="show_emails")
    btn8 = types.InlineKeyboardButton("اضافه الرساله", callback_data="add_message")
    btn9 = types.InlineKeyboardButton("اضافه الموضوع", callback_data="add_subject")
    btn10 = types.InlineKeyboardButton("اضافه العدد", callback_data="add_count")
    btn11 = types.InlineKeyboardButton("اضافه الثواني", callback_data="add_delay")
    btn12 = types.InlineKeyboardButton("السليب الذكي 🧠", callback_data="add_smart_delay")
    btn13 = types.InlineKeyboardButton("اضافه الصوره", callback_data="add_image")
    btn14 = types.InlineKeyboardButton("مسح الصوره", callback_data="clear_image")
    
    markup.add(btn1)
    markup.add(btn2, btn3)
    markup.add(btn4)
    markup.add(btn5, btn6)
    markup.add(btn7)
    markup.add(btn8, btn9)
    markup.add(btn10, btn11)
    markup.add(btn12)
    markup.add(btn13, btn14)
    
    return markup

@bot.message_handler(commands=['start'])
def start_cmd(message):
    welcome_text = "بوت الرفع الخارجي جاهز للعمل بعد ادخال معلوماتك"
    bot.send_message(
        message.chat.id, 
        welcome_text, 
        reply_markup=build_inline_keyboard()
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = get_user_data(user_id)
    action = call.data

    if action == "add_sender":
        bot.answer_callback_query(call.id)
        cancel_markup = types.InlineKeyboardMarkup()
        cancel_markup.add(types.InlineKeyboardButton("رجوع", callback_data="cancel_input"))
        msg_text = "اضف ايميلات الارسال\n\nايميل:باسورد\nايميل:باسورد"
        msg = bot.send_message(call.message.chat.id, msg_text, reply_markup=cancel_markup)
        bot.register_next_step_handler(msg, step_get_senders_list)

    elif action == "add_recipient":
        bot.answer_callback_query(call.id)
        cancel_markup = types.InlineKeyboardMarkup()
        cancel_markup.add(types.InlineKeyboardButton("رجوع", callback_data="cancel_input"))
        msg_text = "📥 اضف ايميلات المستلمين (كل ايميل في سطر):\n\nexample1@gmail.com\nexample2@gmail.com"
        msg = bot.send_message(call.message.chat.id, msg_text, reply_markup=cancel_markup)
        bot.register_next_step_handler(msg, step_get_recipients_list)

    elif action == "cancel_input":
        bot.answer_callback_query(call.id, "تم الإلغاء")
        bot.send_message(call.message.chat.id, "❌ تم العودة للقائمة الرئيسية.", reply_markup=build_inline_keyboard())

    elif action == "show_emails":
        bot.answer_callback_query(call.id)
        senders = data['senders']
        markup = types.InlineKeyboardMarkup()
        for idx, sender in enumerate(senders):
            markup.add(types.InlineKeyboardButton(f"❌ {sender['email']}", callback_data=f"del_email_{idx}"))
        
        if senders:
            markup.add(types.InlineKeyboardButton(f"مسح كل الإيميلات ({len(senders)})", callback_data="clear_all_emails"))
            markup.add(types.InlineKeyboardButton("🔍 تحقق من صلاحية الإيميلات", callback_data="verify_emails"))
            
        markup.add(types.InlineKeyboardButton("رجوع", callback_data="cancel_input"))

        text = (
            "قائمة إيميلاتك\n\n"
            "اضغط على أي إيميل لحذفه مباشرة\n\n"
            f"عدد إيميلات المرسل: {len(senders)}\n"
            f"عدد المستلمين: {len(data['recipients'])}"
        )
        bot.send_message(call.message.chat.id, text, reply_markup=markup)

    elif action.startswith("del_email_"):
        idx = int(action.split("_")[2])
        if idx < len(data['senders']):
            removed = data['senders'].pop(idx)
            save_user_data(user_id, data)
            bot.answer_callback_query(call.id, f"تم حذف {removed['email']}")
            call.data = "show_emails"
            callback_handler(call)
        else:
            bot.answer_callback_query(call.id, "الإيميل غير موجود مسبقاً")

    elif action == "clear_all_emails":
        count = len(data['senders'])
        data['senders'].clear()
        save_user_data(user_id, data)
        bot.answer_callback_query(call.id, "تم مسح جميع الإيميلات")
        bot.send_message(call.message.chat.id, f"🗑️ تم مسح جميع الإيميلات بنجاح ({count}).")
        bot.send_message(call.message.chat.id, "القائمة الرئيسية:", reply_markup=build_inline_keyboard())

    elif action == "verify_emails":
        bot.answer_callback_query(call.id, "جاري التحقق من الحسابات...")
        verify_senders_process(call.message, data)

    elif action == "add_message":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "📝 أدخل نص الرسالة:")
        bot.register_next_step_handler(msg, step_get_message)

    elif action == "add_subject":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "📌 أدخل موضوع الرسالة:")
        bot.register_next_step_handler(msg, step_get_subject)

    elif action == "add_count":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "🔢 أدخل عدد مرات الإرسال لكل حساب:")
        bot.register_next_step_handler(msg, step_get_count)

    elif action == "add_delay":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "⏱️ أدخل الفارق الزمني الثابت بالثواني (سيتم إلغاء السليب الذكي):")
        bot.register_next_step_handler(msg, step_get_delay)

    elif action == "add_smart_delay":
        bot.answer_callback_query(call.id)
        cancel_markup = types.InlineKeyboardMarkup()
        cancel_markup.add(types.InlineKeyboardButton("رجوع", callback_data="cancel_input"))
        msg_text = "🧠 **إعداد السليب الذكي:**\n\nأرسل الثواني، كل رقم في سطر مستقل مثل:\n5\n6\n7"
        msg = bot.send_message(call.message.chat.id, msg_text, parse_mode="Markdown", reply_markup=cancel_markup)
        bot.register_next_step_handler(msg, step_get_smart_delay)

    elif action == "add_image":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "🖼️ أرسل الصورة المراد إرفاقها:")
        bot.register_next_step_handler(msg, step_get_image)

    elif action == "clear_image":
        if data['image_path'] and os.path.exists(data['image_path']):
            try:
                os.remove(data['image_path'])
            except:
                pass
        data['image_path'] = None
        save_user_data(user_id, data)
        bot.answer_callback_query(call.id, "تم مسح الصورة بنجاح")
        bot.send_message(call.message.chat.id, "🗑️ تم مسح الصورة بنجاح.")

    elif action == "show_info":
        recipients_text = "\n".join(data['recipients']) if data['recipients'] else "غير محدد"
        if data['smart_delays']:
            delay_info = f"سليب ذكي 🧠 ({', '.join(map(str, data['smart_delays']))} ثانية)"
        else:
            delay_info = f"{data['delay']} ثانية (ثابت)"

        info = (
            f"📊 **معلومات إعداداتك:**\n\n"
            f"• عدد المرسلين: {len(data['senders'])}\n"
            f"• عدد المستلمين: {len(data['recipients'])}\n"
            f"• المستلمون:\n{recipients_text}\n\n"
            f"• الموضوع: {data['subject']}\n"
            f"• الرسالة: {data['message']}\n"
            f"• العدد لكل مرسل: {data['count']}\n"
            f"• نظام الثواني: {delay_info}\n"
            f"• صورة مرفقة: {'نعم ✅' if data['image_path'] else 'لا ❌'}"
        )
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, info, parse_mode="Markdown")

    elif action == "share":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "🔗 رابط مشاركة البوت:")

    elif action == "channel":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "📢 قناة البوت:")

    # القائمة الجديدة للإرسال الفردي/الكلي
    elif action == "start_sending_menu":
        bot.answer_callback_query(call.id)
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🌐 إرسال كلي (جميع الحسابات معاً)", callback_data="send_mode_all"),
            types.InlineKeyboardButton("👤 إرسال فردي (حساب تلو الآخر)", callback_data="send_mode_individual"),
            types.InlineKeyboardButton("رجوع ❌", callback_data="cancel_input")
        )
        bot.edit_message_text(
            "⚙️ **اختر طريقة الإرسال:**\n\n"
            "• **إرسال كلي 🌐:** سيتم تشغيل جميع إيميلاتك لترسل الرسائل في نفس الوقت (أسرع).\n"
            "• **إرسال فردي 👤:** سيقوم الإيميل الأول بإنهاء عدده بالكامل، ثم ينتقل للإيميل الثاني (أكثر أماناً).",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )

    # معالجة وضعيات الإرسال
    elif action in ["send_mode_all", "send_mode_individual"]:
        bot.answer_callback_query(call.id)
        mode = "all" if action == "send_mode_all" else "individual"
        start_sending_process(call.message, user_id, mode)

# --- معالجة الإدخالات وحفظها مباشرة ---

def verify_senders_process(message, data):
    senders = data['senders']
    if not senders:
        bot.send_message(message.chat.id, "⚠️ لا توجد إيميلات للتحقق منها.")
        return

    status_msg = bot.send_message(message.chat.id, "⏳ جاري فحص الحسابات، يرجى الانتظار...")
    valid_count = 0
    invalid_accounts = []

    for sender in senders:
        try:
            server = smtplib.SMTP('smtp.gmail.com', 587, timeout=5)
            server.starttls()
            server.login(sender['email'], sender['password'])
            server.quit()
            valid_count += 1
        except Exception as e:
            invalid_accounts.append(f"{sender['email']} (الخطأ: {str(e)[:20]})")

    report = f"🔍 **نتيجة التحقق من الإيميلات:**\n\n✅ صالحة وتعمل: {valid_count}\n❌ معطلة: {len(invalid_accounts)}\n"
    if invalid_accounts:
        report += "\n**الإيميلات المعطلة:**\n" + "\n".join(invalid_accounts)

    bot.edit_message_text(report, chat_id=message.chat.id, message_id=status_msg.message_id, parse_mode="Markdown")

def step_get_senders_list(message):
    if message.text and message.text.startswith("/"): return
    user_id = message.from_user.id
    text = message.text.strip()
    data = get_user_data(user_id)
    added, ignored = 0, 0
    existing_emails = {s['email'] for s in data['senders']}
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    
    i = 0
    while i < len(lines):
        line = lines[i]
        email, pwd = "", ""
        if ":" in line and not line.endswith(":"):
            parts = line.split(":", 1)
            email = parts[0].strip().lower()
            pwd = parts[1].strip()
            i += 1
        elif line.endswith(":") and i + 1 < len(lines):
            email = line[:-1].strip().lower()
            pwd = lines[i+1].strip()
            i += 2
        elif "@" in line and i + 1 < len(lines):
            email = line.strip().lower()
            pwd = lines[i+1].strip()
            if pwd.startswith(":"): pwd = pwd[1:].strip()
            i += 2
        else:
            ignored += 1
            i += 1
            continue
            
        if email.endswith("@gmail.com") and pwd and email not in existing_emails:
            data['senders'].append({"email": email, "password": pwd})
            existing_emails.add(email)
            added += 1
        else:
            ignored += 1
            
    save_user_data(user_id, data) 
    response_msg = f"✅ تم حفظ {added} حساب مرسل بنجاح."
    if ignored > 0: response_msg += f"\n⚠️ تم تجاهل {ignored} بسبب صيغة غير صحيحة أو تكرارها."
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("رجوع", callback_data="cancel_input"))
    bot.send_message(message.chat.id, response_msg, reply_markup=markup)

def step_get_recipients_list(message):
    if message.text and message.text.startswith("/"): return
    user_id = message.from_user.id
    lines = message.text.strip().split("\n")
    data = get_user_data(user_id)
    added, ignored = 0, 0
    existing_recipients = set(data['recipients'])

    for line in lines:
        email = line.strip().lower()
        if "@" in email and "." in email and email not in existing_recipients:
            data['recipients'].append(email)
            existing_recipients.add(email)
            added += 1
        else:
            ignored += 1

    save_user_data(user_id, data) 
    response_msg = f"✅ تم حفظ {added} مستلم بنجاح."
    if ignored > 0: response_msg += f"\n⚠️ تم تجاهل {ignored} بسبب صيغة غير صحيحة أو تكرار."
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("رجوع", callback_data="cancel_input"))
    bot.send_message(message.chat.id, response_msg, reply_markup=markup)

def step_get_message(message):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    data['message'] = message.text
    save_user_data(user_id, data)
    bot.reply_to(message, "✅ تم حفظ نص الرسالة.")

def step_get_subject(message):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    data['subject'] = message.text
    save_user_data(user_id, data)
    bot.reply_to(message, "✅ تم حفظ الموضوع.")

def step_get_count(message):
    if message.text.isdigit():
        user_id = message.from_user.id
        data = get_user_data(user_id)
        data['count'] = int(message.text)
        save_user_data(user_id, data)
        bot.reply_to(message, f"✅ تم تحديد العدد: {message.text}")
    else:
        bot.reply_to(message, "❌ أرسل رقماً صحيحاً فقط.")

def step_get_delay(message):
    if message.text.isdigit():
        user_id = message.from_user.id
        data = get_user_data(user_id)
        data['delay'] = int(message.text)
        data['smart_delays'] = [] 
        save_user_data(user_id, data)
        bot.reply_to(message, f"✅ تم تحديد الفارق الثابت: {message.text} ثواني.")
    else:
        bot.reply_to(message, "❌ أرسل رقماً صحيحاً فقط.")

def step_get_smart_delay(message):
    if message.text and message.text.startswith("/"): return
    user_id = message.from_user.id
    data = get_user_data(user_id)
    delays = [int(line.strip()) for line in message.text.strip().split("\n") if line.strip().isdigit() and int(line.strip()) >= 0]

    if delays:
        data['smart_delays'] = delays
        data['delay'] = 0
        save_user_data(user_id, data)
        bot.reply_to(message, f"✅ تم تفعيل السليب الذكي بنجاح!\nالترتيب: {data['smart_delays']}")
    else:
        bot.reply_to(message, "❌ لم يتم التعرف على أرقام صالحة. أرسل أرقاماً صحيحة كل رقم في سطر.")

def step_get_image(message):
    if message.photo:
        user_id = message.from_user.id
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded = bot.download_file(file_info.file_path)
        path = os.path.join(IMAGE_DIR, f"{user_id}.jpg")
        with open(path, 'wb') as f:
            f.write(downloaded)
        
        data = get_user_data(user_id)
        data['image_path'] = path
        save_user_data(user_id, data)
        bot.reply_to(message, "✅ تم حفظ الصورة بنجاح.")
    else:
        bot.reply_to(message, "❌ يرجى إرسال ملف صورة صالح.")

# --- محرك الإرسال ---

def build_and_send_email(server, sender_email, recipient, subject, body_text, image_path):
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient
    
    unique_id = uuid.uuid4().hex[:12]
    msg['Subject'] = subject
    msg.add_header('Message-ID', f"<{unique_id}@mail.gmail.com>")
    msg.add_header('X-Entity-Ref-ID', unique_id)
    msg.attach(MIMEText(body_text, 'plain', 'utf-8'))

    if image_path and os.path.exists(image_path):
        with open(image_path, 'rb') as img_f:
            msg.attach(MIMEImage(img_f.read(), name=os.path.basename(image_path)))

    server.sendmail(sender_email, recipient, msg.as_string())

def single_sender_task(message, sender, recipients, start_recipient_idx, start_delay_idx, subject, body_text, count, smart_delays, fixed_delay, image_path, results_dict, counter_lock):
    """دالة مهمة الإرسال لحساب مرسل واحد (تستخدم للكل والفردي)"""
    success, failed = 0, 0
    recipient_idx = start_recipient_idx
    delay_counter = start_delay_idx
    
    sender_email = sender['email']
    sender_password = sender['password']
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
        server.starttls()
        server.login(sender_email, sender_password)
    except Exception as e:
        print(f"❌ فشل تسجيل الدخول للحساب {sender_email}: {e}")
        bot.send_message(message.chat.id, f"⚠️ تعذر تسجيل الدخول للحساب: {sender_email}")
        with counter_lock:
            results_dict['failed'] += count
        return 

    for i in range(count):
        current_recipient = recipients[recipient_idx % len(recipients)]
        try:
            build_and_send_email(server, sender_email, current_recipient, subject, body_text, image_path)
            success += 1
            print(f"✅ تم الإرسال من {sender_email} إلى {current_recipient}")
        except Exception as e:
            failed += 1
            print(f"❌ فشل الإرسال من {sender_email} إلى {current_recipient}. السبب: {e}")
        
        recipient_idx += 1
        
        if smart_delays:
            current_delay = smart_delays[delay_counter % len(smart_delays)]
            delay_counter += 1
        else:
            current_delay = fixed_delay

        if current_delay > 0:
            time.sleep(current_delay)
    
    try:
        server.quit()
    except:
        pass
        
    # تسجيل النتائج بطريقة آمنة للمسارات (Thread-safe)
    with counter_lock:
        results_dict['success'] += success
        results_dict['failed'] += failed

def sending_thread_individual(message, user_id, senders, recipients, subject, body_text, count, smart_delays, fixed_delay, image_path):
    """إرسال فردي: الإرسال بالتتابع حساباً تلو الآخر"""
    results = {'success': 0, 'failed': 0}
    counter_lock = threading.Lock()
    recipient_idx = 0
    delay_counter = 0
    
    for sender in senders:
        single_sender_task(message, sender, recipients, recipient_idx, delay_counter, subject, body_text, count, smart_delays, fixed_delay, image_path, results, counter_lock)
        recipient_idx += count
        delay_counter += count
        
    bot.send_message(
        message.chat.id, 
        f"🏁 اكتملت عملية الإرسال الفردي!\n\n✅ الناجح: {results['success']}\n❌ الفاشل: {results['failed']}"
    )

def sending_thread_all(message, user_id, senders, recipients, subject, body_text, count, smart_delays, fixed_delay, image_path):
    """إرسال كلي: تشغيل جميع الحسابات لترسل في نفس الوقت"""
    results = {'success': 0, 'failed': 0}
    counter_lock = threading.Lock()
    threads = []
    recipient_idx = 0
    delay_counter = 0
    
    for sender in senders:
        t = threading.Thread(
            target=single_sender_task,
            args=(message, sender, recipients, recipient_idx, delay_counter, subject, body_text, count, smart_delays, fixed_delay, image_path, results, counter_lock)
        )
        threads.append(t)
        t.start()
        
        # دفع المؤشرات حتى يرسل كل حساب لأشخاص مختلفين 
        recipient_idx += count
        delay_counter += count
        
    # انتظار انتهاء جميع المهام
    for t in threads:
        t.join()
        
    bot.send_message(
        message.chat.id, 
        f"🏁 اكتملت عملية الإرسال الكلي!\n\n✅ الناجح: {results['success']}\n❌ الفاشل: {results['failed']}"
    )

def start_sending_process(message, user_id, mode):
    data = get_user_data(user_id)

    if not data['senders']:
        bot.send_message(message.chat.id, "⚠️ يرجى إضافة مرسل واحد على الأقل.")
        return
    if not data['recipients']:
        bot.send_message(message.chat.id, "⚠️ يرجى إضافة مستلم واحد على الأقل.")
        return

    count = data['count']
    senders = data['senders']
    recipients = data['recipients']
    smart_delays = data['smart_delays']
    fixed_delay = data['delay']

    total_sends = len(senders) * count
    delay_type_str = f"سليب ذكي ({smart_delays})" if smart_delays else f"{fixed_delay} ثانية"
    mode_text = "🌐 إرسال كلي (الكل معاً)" if mode == 'all' else "👤 إرسال فردي (حساب تلو الآخر)"

    bot.send_message(
        message.chat.id, 
        f"🚀 جاري بدء الإرسال في الخلفية...\n"
        f"• الوضع: {mode_text}\n"
        f"• عدد الحسابات: {len(senders)}\n"
        f"• العدد لكل حساب: {count}\n"
        f"• الإجمالي: {total_sends} رسالة\n"
        f"• التأخير: {delay_type_str}\n\n"
        f"⏳ يمكنك الاستمرار في استخدام البوت ولن يتوقف أثناء الإرسال."
    )

    # اختيار الدالة المناسبة بناءً على الوضع
    target_func = sending_thread_all if mode == 'all' else sending_thread_individual

    thread = threading.Thread(
        target=target_func, 
        args=(
            message, 
            user_id, 
            list(senders), 
            list(recipients), 
            data['subject'], 
            data['message'], 
            count, 
            list(smart_delays), 
            fixed_delay, 
            data['image_path']
        )
    )
    thread.start()

if __name__ == '__main__':
    init_db() # تهيئة قاعدة البيانات عند بدء التشغيل
    print("البوت يعمل الآن وقاعدة البيانات متصلة...")
    bot.infinity_polling()
