import sqlite3, asyncio, re, logging
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeExpiredError, PhoneCodeInvalidError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta

# --- SOZLAMALAR ---
API_ID = 37692398 
API_HASH = 'd35b9ff25f2691ef5efedd5642220894'
BOT_TOKEN = '8411218348:AAHJ7NRkTJyvpRk3nRvWY_4QfvyJRQjJwZ8'
ADMIN_ID = 8056595398 

bot = TelegramClient('bot_v38_session', API_ID, API_HASH)
scheduler = AsyncIOScheduler()
user_sessions = {}

# --- DATABASE ---
def db_query(q, p=(), f=False):
    conn = sqlite3.connect("bot_v38.db")
    cur = conn.cursor()
    cur.execute(q, p)
    res = cur.fetchall() if f else None
    conn.commit()
    conn.close()
    return res

def init_db():
    # expires_at ustuni qo'shildi
    db_query("CREATE TABLE IF NOT EXISTS users (uid INTEGER PRIMARY KEY, sess TEXT, approved INTEGER DEFAULT 0, expires_at TEXT)")
    db_query("CREATE TABLE IF NOT EXISTS grps (id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, gid TEXT, title TEXT, sel INTEGER DEFAULT 0)")

async def get_cl(uid):
    if uid in user_sessions: return user_sessions[uid]
    s = db_query("SELECT sess FROM users WHERE uid=?", (uid,), True)
    if s and s[0][0]:
        try:
            cl = TelegramClient(StringSession(s[0][0]), API_ID, API_HASH)
            await cl.connect()
            if await cl.is_user_authorized():
                user_sessions[uid] = cl
                return cl
        except: pass
    return None

# --- ADMIN VA START ---
# --- ADMIN VA START (RUHSATNI QAT'IY TEKSHIRISH) ---
@bot.on(events.NewMessage(pattern='/start'))
async def start(ev):
    sender = await ev.get_sender()
    uid = ev.sender_id
    full_name = f"{sender.first_name or ''} {sender.last_name or ''}".strip() or "Noma'lum"

    # 1. Admin bo'lsa, darrov menyuni ko'rsatish
    if uid == ADMIN_ID:
        db_query("INSERT OR REPLACE INTO users (uid, approved, expires_at) VALUES (?, 1, ?)", (uid, "2099-01-01 00:00:00"))
        await show_menu(uid)
        return

    # 2. Bazadan tekshirish
    res = db_query("SELECT approved, expires_at FROM users WHERE uid=?", (uid,), True)
    
    if res:
        approved, exp_str = res[0]
        if approved == 1:
            exp_date = datetime.strptime(exp_str, '%Y-%m-%d %H:%M:%S')
            if datetime.now() < exp_date:
                # RUXSAT BOR BO'LSA SHU YERDAN TO'XTAYDI VA MENYUNI KO'RSATADI
                await show_menu(uid)
                return
            else:
                # Muddat tugagan bo'lsa, approvedni 0 qilamiz
                db_query("UPDATE users SET approved=0 WHERE uid=?", (uid,))

    # 3. Agar yuqoridagilar ishlamasa (ruxsat yo'q bo'lsa), ruxsat so'rash:
    await ev.respond(f"⏳ {full_name}, ruxsat kutilmoqda. Admin tasdiqlashini kuting...")
    
    msg = f"🔔 **Yangi ruxsat so'rovi:**\n👤 Ismi: {full_name}\n🆔 ID: `{uid}`"
    # Tugmani bosganda adminga aniq xabar borishi uchun:
    await bot.send_message(ADMIN_ID, msg, buttons=[[Button.inline("✅ 1 oyga ruxsat berish", f"ok_{uid}")]])

@bot.on(events.CallbackQuery(pattern=r'ok_'))
async def approve(ev):
    # Tugmadan IDni ajratib olish
    data = ev.data.decode().split('_')
    t_id = int(data[1])
    
    # 1 oylik vaqtni hisoblash
    exp_time = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    
    # Bazaga yozish
    db_query("INSERT OR REPLACE INTO users (uid, approved, expires_at) VALUES (?, 1, ?)", (t_id, exp_time))
    
    await ev.edit(f"✅ ID: {t_id} uchun 1 oylik ruxsat berildi!")
    await bot.send_message(t_id, "🎉 Admin sizga 1 oyga ruxsat berdi! Endi /start bosing va akkaunt ulanadi.")

@bot.on(events.CallbackQuery(pattern=r'ok_'))
async def approve(ev):
    t_id = int(ev.data.decode().split('_')[1])
    exp_time = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    db_query("UPDATE users SET approved=1, expires_at=? WHERE uid=?", (exp_time, t_id))
    await ev.edit("✅ 1 oylik ruxsat berildi!")
    await bot.send_message(t_id, "🎉 Admin sizga 1 oyga ruxsat berdi! Endi /start bosing.")

async def show_menu(uid):
    cl = await get_cl(uid)
    btns = [[Button.inline("🔐 Akkauntni ulash", b"login")]] if not cl else [
        [Button.inline("🔄 Guruhlarni yangilash", b"sync")],
        [Button.inline("👥 Guruhlarni tanlash", b"sel_0")],
        [Button.inline("📬 Avto-xabarni sozlash", b"msg")],
        [Button.inline("🛑 To'xtatish", b"stop")]
    ]
    await bot.send_message(uid, "🛠 **Asosiy boshqaruv paneli**", buttons=btns)

# --- LOGIN & 2FA ---
@bot.on(events.CallbackQuery(pattern=b'login'))
async def login(ev):
    uid = ev.sender_id
    async with bot.conversation(uid, timeout=600) as conv:
        await conv.send_message("📱 Telefon raqam (+998XXXXXXXXX):")
        ph = (await conv.get_response()).text.strip().replace(" ", "")
        
        cl = TelegramClient(StringSession(), API_ID, API_HASH)
        await cl.connect()
        
        try:
            res = await cl.send_code_request(ph)
            await conv.send_message("📩 Telegramdan kelgan kodni yozing:")
            code_msg = await conv.get_response()
            code = re.sub(r'\D', '', code_msg.text)
            
            try:
                await cl.sign_in(ph, code, phone_code_hash=res.phone_code_hash)
            except SessionPasswordNeededError:
                await conv.send_message("🔐 2FA parol (Ikki bosqichli) aniqlandi. Parolni yuboring:")
                pwd = (await conv.get_response()).text.strip()
                await cl.sign_in(password=pwd)
            
            db_query("UPDATE users SET sess=? WHERE uid=?", (cl.session.save(), uid))
            user_sessions[uid] = cl
            await conv.send_message("✅ Akkaunt ulandi!"); await show_menu(uid)
            
        except Exception as e:
            await conv.send_message(f"❌ Xatolik: {str(e)}")

# --- GURUHLAR ---
@bot.on(events.CallbackQuery(pattern=b'sync'))
async def sync(ev):
    cl = await get_cl(ev.sender_id)
    if not cl: return
    await ev.answer("🔄 Guruhlar yuklanmoqda...")
    async for d in cl.iter_dialogs():
        if d.is_group: db_query("INSERT OR IGNORE INTO grps (uid, gid, title) VALUES (?, ?, ?)", (ev.sender_id, str(d.id), d.name))
    await ev.edit("✅ Guruhlar yangilandi!"); await show_menu(ev.sender_id)

@bot.on(events.CallbackQuery(pattern=r'sel_'))
async def select(ev):
    try:
        # Sahifa raqamini olamiz
        pg = int(ev.data.decode().split('_')[1])
    except:
        pg = 0
    await select_page(ev, pg)

async def select_page(ev, pg):
    # Guruhlarni bazadan olamiz
    gs = db_query("SELECT gid, title, sel FROM grps WHERE uid=?", (ev.sender_id,), True)
    if not gs:
        await ev.answer("❌ Guruhlar topilmadi!", alert=True)
        return

    per_page = 10
    curr = gs[pg*per_page:(pg+1)*per_page]
    
    btns = []
    for g in curr:
        # Statusni aniqlaymiz: 1 bo'lsa ✅, 0 bo'lsa ⬜️
        status = "✅" if g[2] == 1 else "⬜️"
        btns.append([Button.inline(f"{status} {g[1][:20]}", f"t_{g[0]}_{pg}")])
    
    nav = []
    if pg > 0: nav.append(Button.inline("⬅️ Oldingi", f"sel_{pg-1}"))
    if len(gs) > (pg+1)*per_page: nav.append(Button.inline("Keyingi ➡️", f"sel_{pg+1}"))
    
    if nav: btns.append(nav)
    btns.append([Button.inline("🔙 Orqaga", b"back")])
    
    # edit orqali menyuni yangilaymiz
    await ev.edit("👥 Guruhlarni tanlang (ustiga bosing):", buttons=btns)

@bot.on(events.CallbackQuery(pattern=r't_'))
async def toggle(ev):
    data = ev.data.decode().split('_')
    gid = data[1]
    pg = int(data[2])
    
    # BAZADA HOLATNI O'ZGARTIRISH (1 bo'lsa 0, 0 bo'lsa 1 qiladi)
    db_query("UPDATE grps SET sel = 1 - sel WHERE uid=? AND gid=?", (ev.sender_id, gid))
    
    # XATO BERMAYDIGAN USUL: Sahifani qayta chizamiz
    await select_page(ev, pg)
    await ev.answer("Holat o'zgardi")


# --- AVTO-XABAR (REPEATING) ---
@bot.on(events.CallbackQuery(pattern=b'msg'))
async def send_msg(ev):
    uid = ev.sender_id
    async with bot.conversation(uid, timeout=600) as conv:
        # 1. Xabar matnini so'rash
        await conv.send_message("✍️ **Guruhlarga yuboriladigan xabar matnini yuboring:**")
        msg_obj = await conv.get_response()
        txt = msg_obj.text
        
        # 2. Vaqtni so'rash
        await conv.send_message("⏱ Har necha daqiqada yuborsin? (Masalan: 5, 10, 60):")
        m_resp = await conv.get_response()
        
        # Raqamni tekshirib olish
        raw_mins = re.sub(r'\D', '', m_resp.text)
        mins = int(raw_mins) if raw_mins else 5
        
        # 3. Tanlangan guruhlarni bazadan olish
        gs = db_query("SELECT gid FROM grps WHERE uid=? AND sel=1", (uid,), True)
        
        if not gs:
            await conv.send_message("❌ Xato: Hech qanday guruh tanlanmagan!")
            return

        # 4. Eski ishlarni tozalash
        for j in scheduler.get_jobs():
            if j.id.startswith(f"j_{uid}"):
                scheduler.remove_job(j.id)
            
        # 5. Yangi xabarlarni schedulerga qo'shish
        for g in gs:
            # Diqqat: do_send funksiyasi kodning eng pastida bo'lishi kerak
            scheduler.add_job(
                do_send, 
                'interval', 
                minutes=mins, 
                args=[uid, int(g[0]), txt], 
                id=f"j_{uid}_{g[0]}", 
                replace_existing=True
            )
        
        # 6. SIZ AYTGAN TASDIQLASH XABARI (Chiroyli ko'rinishda)
        confirm_text = (
            f"✅ **Xabar yuborish boshlandi!**\n\n"
            f"📝 **Sizning xabaringiz:**\n`{txt}`\n\n"
            f"📊 Guruhlar soni: {len(gs)} ta\n"
            f"⏱ Vaqt oralig'i: har {mins} daqiqada\n\n"
            f"🛑 To'xtatish uchun: Pastdagi tugmani bosing yoki /stop deb yozing."
        )
        await conv.send_message(confirm_text, buttons=[[Button.inline("🛑 To'xtatish", b"stop")]])

# do_send funksiyasi mana bu ko'rinishda bo'lsin
async def do_send(u_id, g_id, text):
    cl = await get_cl(u_id)
    if cl:
        try:
            await cl.send_message(g_id, text)
        except Exception as e:
            print(f"Xabar ketmadi ({g_id}): {e}")

@bot.on(events.CallbackQuery(pattern=b'stop'))
async def stop(ev):
    for j in scheduler.get_jobs():
        if j.id.startswith(f"j_{ev.sender_id}"): scheduler.remove_job(j.id)
    await ev.answer("🛑 To'xtatildi", alert=True)

@bot.on(events.CallbackQuery(pattern=b'back'))
async def back(ev): await show_menu(ev.sender_id)

async def main():
    init_db()
    if not scheduler.running: scheduler.start()
    await bot.start(bot_token=BOT_TOKEN)
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())