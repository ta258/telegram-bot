import os
import re
import time
import uuid
import smtplib
import ssl
import threading
import sqlite3
import json
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import telebot
from telebot import types

# -----------------------------------------------------------
# --- نظام البروكسي لتخطي الحظر الشديد (معطل افتراضياً) ---
# إذا استمر الخطأ، احذف علامة # من الأسطر أسفله واكتب IP بروكسي شغال
# تأكد من تثبيت المكتبة أولاً في الاستضافة بكتابة: pip install pysocks
# import socks
# PROXY_IP = "188.226.141.211" # ضع البروكسي هنا
# PROXY_PORT = 1080            # ضع بورت البروكسي هنا
# socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5, PROXY_IP, PROXY_PORT)
# socket.socket = socks.socksocket
# -----------------------------------------------------------

# --- إجبار بايثون على استخدام IPv4 فقط لحل مشكلة الشبكة ---
old_getaddrinfo = socket.getaddrinfo
def new_getaddrinfo(*args, **kwargs):
    responses = old_getaddrinfo(*args, **kwargs)
    return [response for response in responses if response[0] == socket.AF_INET]
socket.getaddrinfo = new_getaddrinfo
# -----------------------------------------------------------

TOKEN = '8802118672:AAEfEndBO_qPf2yyOLK0EfkzXCKNFjnJhHU'
bot = telebot.TeleBot(TOKEN)

IMAGE_DIR = "temp_images"
if not os.path.exists(IMAGE_DIR):
    os.makedirs(IMAGE_DIR)

DB_NAME = "bot_data.db"

# قاموس لمتابعة وإيقاف عمليات الإرسال الحالية لكل مستخدم
active_sending_tasks = {}

# --- محرك الاتصال بـ Gmail (المطور لتخطي حظر الاستضافات) ---

def connect_gmail_smtp(email, password, retries=3):
    try:
        context = ssl._create_unverified_context()
    except AttributeError:
        context = ssl.create_default_context()

    last_exception = None
    timeout_seconds = 20
    
    # قائمة بسيرفرات جوجل (النطاق + الايبيهات المباشرة لتخطي حظر الـ DNS)
    google_smtp_servers = [
        'smtp.gmail.com',
        '142.251.175.108',
        '142.250.102.108',
        '142.250.141.108',
        '74.125.137.108'
    ]
    
    for server_addr in google_smtp_servers:
        for attempt in range(retries):
            # المحاولة عبر المنفذ 465 (مفضل في بعض الاستضافات)
            try:
                server = smtplib.SMTP_SSL(server_addr, 465, context=context, timeout=timeout_seconds)
                server.login(email, password)
                return server
            except Exception as e:
                last_exception = f"465 ({server_addr}): {e}"

            # المحاولة عبر المنفذ 587
            try:
                server = smtplib.SMTP(server_addr, 587, timeout=timeout_seconds)
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(email, password)
                return server
            except Exception as e:
                last_exception = f"{last_exception} | 587 ({server_addr}): {e}"
                
            time.sleep(2)
            
    raise Exception(f"فشل الاتصال: {last_exception}")

# --- إدارة قاعدة البيانات ---

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
    bot.send_message(message.chat.id, "بوت الرفع الخارجي جاهز للعمل بعد ادخال معلوماتك", reply_markup=build_inline_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = get_user_data(user_id)
    action = call.data

    if action == "cancel_sending":
        if user_id in active_sending_tasks:
            active_sending_tasks[user_id]['cancel'] = True
            bot.answer_callback_query(call.id, "🛑 جاري إلغاء عملية الإرسال...")
        else:
            bot.answer_callback_query(call.id, "⚠️ لا توجد عملية إرسال جارية حالياً.")

    elif action == "add_sender":
        bot.answer_callback_query(call.id)
        cancel_markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("رجوع", callback_data="cancel_input"))
        msg = bot.send_message(call.message.chat.id, "اضف ايميلات الارسال بالصيغة التالية:\n\nالايميل:الباسورد\n\nمثال:\nGis@gmail.com:password123", reply_markup=cancel_markup)
        bot.register_next_step_handler(msg, step_get_senders_list)

    elif action == "add_recipient":
        bot.answer_callback_query(call.id)
        cancel_markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("رجوع", callback_data="cancel_input"))
        msg = bot.send_message(call.message.chat.id, "📥 اضف ايميلات المستلمين (كل ايميل في سطر):", reply_markup=cancel_markup)
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
        bot.send_message(call.message.chat.id, f"عدد إيميلات المرسل: {len(senders)}\nعدد المستلمين: {len(data['recipients'])}", reply_markup=markup)

    elif action.startswith("del_email_"):
        idx = int(action.split("_")[2])
        if idx < len(data['senders']):
            removed = data['senders'].pop(idx)
            save_user_data(user_id, data)
            bot.answer_callback_query(call.id, f"تم حذف {removed['email']}")
            call.data = "show_emails"
            callback_handler(call)

    elif action == "clear_all_emails":
        data['senders'].clear()
        save_user_data(user_id, data)
        bot.answer_callback_query(call.id, "تم مسح جميع الإيميلات")
        bot.send_message(call.message.chat.id, "🗑️ تم مسح جميع الإيميلات بنجاح.", reply_markup=build_inline_keyboard())

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
        msg = bot.send_message(call.message.chat.id, "⏱️ أدخل الفارق الزمني بالثواني:")
        bot.register_next_step_handler(msg, step_get_delay)

    elif action == "add_smart_delay":
        bot.answer_callback_query(call.id)
        cancel_markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("رجوع", callback_data="cancel_input"))
        msg = bot.send_message(call.message.chat.id, "🧠 **إعداد السليب الذكي:**\nأرسل الثواني كل رقم في سطر:", parse_mode="Markdown", reply_markup=cancel_markup)
        bot.register_next_step_handler(msg, step_get_smart_delay)

    elif action == "add_image":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "🖼️ أرسل الصورة المراد إرفاقها:")
        bot.register_next_step_handler(msg, step_get_image)

    elif action == "clear_image":
        if data['image_path'] and os.path.exists(data['image_path']):
            try: os.remove(data['image_path'])
            except: pass
        data['image_path'] = None
        save_user_data(user_id, data)
        bot.answer_callback_query(call.id, "تم مسح الصورة بنجاح")
        bot.send_message(call.message.chat.id, "🗑️ تم مسح الصورة.")

    elif action == "show_info":
        recipients_text = "\n".join(data['recipients']) if data['recipients'] else "غير محدد"
        delay_info = f"سليب ذكي 🧠 ({', '.join(map(str, data['smart_delays']))} ثانية)" if data['smart_delays'] else f"{data['delay']} ثانية"
        info = (
            f"📊 **معلومات إعداداتك:**\n\n"
            f"• عدد المرسلين: {len(data['senders'])}\n"
            f"• عدد المستلمين: {len(data['recipients'])}\n"
            f"• الموضوع: {data['subject']}\n"
            f"• العدد لكل مرسل: {data['count']}\n"
            f"• نظام الثواني: {delay_info}\n"
            f"• صورة مرفقة: {'نعم ✅' if data['image_path'] else 'لا ❌'}"
        )
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, info, parse_mode="Markdown")

    elif action in ["share", "channel"]:
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "📢 قريباً...")

    elif action == "start_sending_menu":
        if user_id in active_sending_tasks and not active_sending_tasks[user_id]['cancel']:
            bot.answer_callback_query(call.id, "⚠️ هناك عملية إرسال جارية بالفعل!")
            return
        bot.answer_callback_query(call.id)
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🌐 إرسال كلي (الجميع معاً)", callback_data="send_mode_all"),
            types.InlineKeyboardButton("👤 إرسال فردي (حساب تلو الآخر)", callback_data="send_mode_individual"),
            types.InlineKeyboardButton("رجوع ❌", callback_data="cancel_input")
        )
        bot.edit_message_text("⚙️ **اختر طريقة الإرسال:**", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif action in ["send_mode_all", "send_mode_individual"]:
        bot.answer_callback_query(call.id)
        mode = "all" if action == "send_mode_all" else "individual"
        start_sending_process(call.message, user_id, mode)

# --- معالجة الإدخالات ---

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
            server = connect_gmail_smtp(sender['email'], sender['password'])
            server.quit()
            valid_count += 1
        except Exception as e:
            invalid_accounts.append(f"{sender['email']} (الخطأ: {str(e)[:30]})")

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
    matches = re.findall(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})[\s:=]+([^\s]+)', text)
    for email_raw, pwd_raw in matches:
        email = email_raw.strip().lower()
        pwd = pwd_raw.strip().replace(" ", "")
        if email.endswith("@gmail.com") and pwd and email not in existing_emails:
            data['senders'].append({"email": email, "password": pwd})
            existing_emails.add(email)
            added += 1
        else:
            ignored += 1
    save_user_data(user_id, data) 
    bot.send_message(message.chat.id, f"✅ تم حفظ {added} حساب مرسل بنجاح.")

def step_get_recipients_list(message):
    if message.text and message.text.startswith("/"): return
    user_id = message.from_user.id
    lines = message.text.strip().split("\n")
    data = get_user_data(user_id)
    added = 0
    existing_recipients = set(data['recipients'])
    for line in lines:
        email = line.strip().lower()
        if "@" in email and "." in email and email not in existing_recipients:
            data['recipients'].append(email)
            existing_recipients.add(email)
            added += 1
    save_user_data(user_id, data) 
    bot.send_message(message.chat.id, f"✅ تم حفظ {added} مستلم.")

def step_get_message(message):
    data = get_user_data(message.from_user.id)
    data['message'] = message.text
    save_user_data(message.from_user.id, data)
    bot.reply_to(message, "✅ تم حفظ نص الرسالة.")

def step_get_subject(message):
    data = get_user_data(message.from_user.id)
    data['subject'] = message.text
    save_user_data(message.from_user.id, data)
    bot.reply_to(message, "✅ تم حفظ الموضوع.")

def step_get_count(message):
    if message.text.isdigit():
        data = get_user_data(message.from_user.id)
        data['count'] = int(message.text)
        save_user_data(message.from_user.id, data)
        bot.reply_to(message, f"✅ تم تحديد العدد.")

def step_get_delay(message):
    if message.text.isdigit():
        data = get_user_data(message.from_user.id)
        data['delay'] = int(message.text)
        data['smart_delays'] = [] 
        save_user_data(message.from_user.id, data)
        bot.reply_to(message, f"✅ تم تحديد الفارق الثابت.")

def step_get_smart_delay(message):
    delays = [int(line.strip()) for line in message.text.strip().split("\n") if line.strip().isdigit() and int(line.strip()) >= 0]
    if delays:
        data = get_user_data(message.from_user.id)
        data['smart_delays'] = delays
        data['delay'] = 0
        save_user_data(message.from_user.id, data)
        bot.reply_to(message, f"✅ تم تفعيل السليب الذكي.")

def step_get_image(message):
    if message.photo:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded = bot.download_file(file_info.file_path)
        path = os.path.join(IMAGE_DIR, f"{message.from_user.id}.jpg")
        with open(path, 'wb') as f: f.write(downloaded)
        data = get_user_data(message.from_user.id)
        data['image_path'] = path
        save_user_data(message.from_user.id, data)
        bot.reply_to(message, "✅ تم حفظ الصورة بنجاح.")

# --- محرك الإرسال المحدث ---

def build_and_send_email(server, sender_email, recipient, subject, body_text, image_path):
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient
    unique_id = uuid.uuid4().hex[:12]
    msg['Subject'] = subject
    msg.add_header('Message-ID', f"<{unique_id}@mail.gmail.com>")
    msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
    if image_path and os.path.exists(image_path):
        with open(image_path, 'rb') as img_f:
            msg.attach(MIMEImage(img_f.read(), name=os.path.basename(image_path)))
    server.sendmail(sender_email, recipient, msg.as_string())

def update_progress_msg(chat_id, message_id, user_id, results_dict, total_sends, mode_text):
    cancel_markup = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("🛑 إلغاء الإرسال", callback_data="cancel_sending")
    )
    last_success = -1
    last_failed = -1

    while not results_dict.get('is_done', False):
        if active_sending_tasks.get(user_id, {}).get('cancel', False):
            break

        if results_dict['success'] != last_success or results_dict['failed'] != last_failed:
            last_success = results_dict['success']
            last_failed = results_dict['failed']
            text = (
                f"🚀 **جاري الإرسال الآن...**\n\n"
                f"• الوضع: {mode_text}\n"
                f"• الإجمالي المستهدف: {total_sends}\n"
                f"✅ الناجح: {last_success}\n"
                f"❌ الفاشل: {last_failed}\n\n"
                f"⏳ يمكنك الضغط على الزر أدناه لإيقاف العملية في أي وقت:"
            )
            try:
                bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, parse_mode="Markdown", reply_markup=cancel_markup)
            except:
                pass
        time.sleep(2)
        
    is_cancelled = active_sending_tasks.get(user_id, {}).get('cancel', False)
    status_title = "🛑 **تم إلغاء عملية الإرسال!**" if is_cancelled else "🏁 **اكتملت عملية الإرسال بنجاح!**"
    
    final_text = (
        f"{status_title}\n\n"
        f"• الوضع: {mode_text}\n"
        f"✅ إجمالي الناجح: {results_dict['success']}\n"
        f"❌ إجمالي الفاشل: {results_dict['failed']}"
    )
    try:
        bot.edit_message_text(final_text, chat_id=chat_id, message_id=message_id, parse_mode="Markdown")
    except:
        pass

def single_sender_task(message, user_id, sender, recipients, start_recipient_idx, start_delay_idx, subject, body_text, count, smart_delays, fixed_delay, image_path, results_dict, counter_lock):
    success, failed = 0, 0
    recipient_idx = start_recipient_idx
    delay_counter = start_delay_idx
    sender_email = sender['email']
    
    if active_sending_tasks.get(user_id, {}).get('cancel', False):
        return

    try:
        server = connect_gmail_smtp(sender_email, sender['password'])
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ تعذر تسجيل الدخول للحساب:\n`{sender_email}`\n*(السبب: {e})*", parse_mode="Markdown")
        with counter_lock:
            results_dict['failed'] += count
        return 

    for i in range(count):
        if active_sending_tasks.get(user_id, {}).get('cancel', False):
            break

        current_recipient = recipients[recipient_idx % len(recipients)]
        try:
            build_and_send_email(server, sender_email, current_recipient, subject, body_text, image_path)
            success += 1
        except Exception:
            failed += 1
        
        with counter_lock:
            results_dict['success'] += success
            results_dict['failed'] += failed
            success, failed = 0, 0
            
        recipient_idx += 1
        
        current_delay = smart_delays[delay_counter % len(smart_delays)] if smart_delays else fixed_delay
        if smart_delays: delay_counter += 1

        if current_delay > 0:
            for _ in range(int(current_delay)):
                if active_sending_tasks.get(user_id, {}).get('cancel', False):
                    break
                time.sleep(1)

    try: server.quit()
    except: pass

def sending_thread_individual(message, user_id, senders, recipients, subject, body_text, count, smart_delays, fixed_delay, image_path, status_msg, total_sends, mode_text):
    results = {'success': 0, 'failed': 0, 'is_done': False}
    counter_lock = threading.Lock()
    
    threading.Thread(target=update_progress_msg, args=(message.chat.id, status_msg.message_id, user_id, results, total_sends, mode_text)).start()

    recipient_idx, delay_counter = 0, 0
    
    for sender in senders:
        if active_sending_tasks.get(user_id, {}).get('cancel', False):
            break
        single_sender_task(message, user_id, sender, recipients, recipient_idx, delay_counter, subject, body_text, count, smart_delays, fixed_delay, image_path, results, counter_lock)
        recipient_idx += count
        delay_counter += count
        
    results['is_done'] = True
    active_sending_tasks.pop(user_id, None)

def sending_thread_all(message, user_id, senders, recipients, subject, body_text, count, smart_delays, fixed_delay, image_path, status_msg, total_sends, mode_text):
    results = {'success': 0, 'failed': 0, 'is_done': False}
    counter_lock = threading.Lock()
    
    threading.Thread(target=update_progress_msg, args=(message.chat.id, status_msg.message_id, user_id, results, total_sends, mode_text)).start()

    threads = []
    recipient_idx, delay_counter = 0, 0
    
    for sender in senders:
        t = threading.Thread(target=single_sender_task, args=(message, user_id, sender, recipients, recipient_idx, delay_counter, subject, body_text, count, smart_delays, fixed_delay, image_path, results, counter_lock))
        threads.append(t)
        t.start()
        recipient_idx += count
        delay_counter += count
        
    for t in threads:
        t.join()
        
    results['is_done'] = True
    active_sending_tasks.pop(user_id, None)

def start_sending_process(message, user_id, mode):
    data = get_user_data(user_id)

    if not data['senders'] or not data['recipients']:
        bot.send_message(message.chat.id, "⚠️ يرجى التأكد من إضافة مرسل ومستلم واحد على الأقل.")
        return

    active_sending_tasks[user_id] = {'cancel': False}
    count = data['count']
    total_sends = len(data['senders']) * count
    mode_text = "🌐 كلي" if mode == 'all' else "👤 فردي"

    cancel_markup = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("🛑 إلغاء الإرسال", callback_data="cancel_sending")
    )

    status_msg = bot.send_message(
        message.chat.id, 
        f"🚀 **جاري تجهيز بدء الإرسال...**\n\nالرجاء الانتظار قليلاً.", 
        parse_mode="Markdown",
        reply_markup=cancel_markup
    )

    target_func = sending_thread_all if mode == 'all' else sending_thread_individual

    thread = threading.Thread(
        target=target_func, 
        args=(message, user_id, list(data['senders']), list(data['recipients']), data['subject'], data['message'], count, list(data['smart_delays']), data['delay'], data['image_path'], status_msg, total_sends, mode_text)
    )
    thread.start()

if __name__ == '__main__':
    init_db()
    print("البوت يعمل الآن وقاعدة البيانات متصلة...")
    bot.infinity_polling()
