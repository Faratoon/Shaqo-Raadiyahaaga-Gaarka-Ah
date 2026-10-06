import os
import sys
import time
import json
import re
import urllib.parse
from pathlib import Path
import requests

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Ensure imports work from current project root
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

try:
    from portal_app import get_career_ai_response, get_curated_somali_it_jobs, is_spam_or_invalid
except ImportError:
    def get_career_ai_response(msg):
        return "Salamaat! Waxaan ahay Kaaliyaha Baahiye AI & Shaqo Raadiyaha Dhalinyarada Soomaaliyeed. Waxaan kaa caawin karaa dhammaan fursadaha shaqo, gaar ahaan IT-ga, CV ATS ah, iyo buugaagta Isbar."
    def get_curated_somali_it_jobs():
        return []
    def is_spam_or_invalid(msg):
        return False, ""

def load_env_file():
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

load_env_file()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("CRITICAL: TELEGRAM_BOT_TOKEN is not set in environment or .env file!")

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
PRIMARY_DOMAIN = "https://isbar-ai.com"
FALLBACK_DOMAIN = "https://auto-jobs-applier-aih-awk-live.vercel.app"
WEB_APP_URL = PRIMARY_DOMAIN
GITHUB_REPO_URL = "https://github.com/Faratoon/Shaqo-Raadiyahaaga-Gaarka-Ah"
SUBSTACK_URL = "https://somalilibrary.substack.com"
DHEGEYSO_BUUG_SUBSTACK = "https://dhegeysobuug.substack.com/"
YOUTUBE_URL = "https://www.youtube.com/@Mfaratoon"
SHARE_TEXT = urllib.parse.quote("🔥 Fursadaha Shaqo, Akadeemiyada Isbar & Maamulka Telegram (isbar-ai.com)! Ka faa'iideyso @Baahiyebot 🚀")

# Database & Telegram Management Configuration
IS_VERCEL = bool(os.environ.get("VERCEL"))
if IS_VERCEL:
    TG_DATA_FILE = Path("/tmp/telegram_management_data.json")
    seed_file = BASE_DIR / "telegram_management_data.json"
    if seed_file.exists() and not TG_DATA_FILE.exists():
        try:
            import shutil
            shutil.copy2(seed_file, TG_DATA_FILE)
        except Exception:
            pass
else:
    TG_DATA_FILE = BASE_DIR / "telegram_management_data.json"
VULGAR_WORDS = [
    "wasmo", "siil", "gus", "futada", "fck", "bitch", "shit",
    "dhuuq", "qaniis", "dhillo", "naago", "futo", "aflagaado"
]

def load_tg_data():
    if TG_DATA_FILE.exists():
        try:
            with open(TG_DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"users": {}, "channels": {}, "groups": {}, "knowledge_docs": []}

def save_tg_data(data):
    try:
        with open(TG_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[!] Error saving tg data: {e}", flush=True)

USER_STATES = {}  # In-memory user state machine: uid -> {"state": "...", ...}

def get_user_record(user_id, referrer_id=None, first_name=None):
    data = load_tg_data()
    uid = str(user_id)
    now = time.time()
    current_week = int(now / (7 * 86400))
    
    if uid not in data["users"]:
        data["users"][uid] = {
            "name": first_name or f"User_{uid[-4:]}",
            "created_at": now,
            "referrals": [],
            "unlocked_permanent": False,
            "points": 20,  # Welcome bonus points
            "weekly_posts_used": 0,
            "last_week_reset": current_week,
            "channels": [],
            "groups": [],
            "schedule": {"morning": True, "noon": False, "evening": True}
        }
        
        # Credit referrer if valid
        if referrer_id and str(referrer_id) != uid:
            ref_uid = str(referrer_id)
            if ref_uid in data["users"]:
                if uid not in data["users"][ref_uid].setdefault("referrals", []):
                    data["users"][ref_uid]["referrals"].append(uid)
                    data["users"][ref_uid]["points"] = data["users"][ref_uid].get("points", 20) + 25
                    if len(data["users"][ref_uid]["referrals"]) >= 10:
                        data["users"][ref_uid]["unlocked_permanent"] = True
                    save_tg_data(data)
                    # Notify referrer
                    try:
                        ref_count = len(data["users"][ref_uid]["referrals"])
                        if ref_count >= 10:
                            send_message(int(ref_uid), "🌟 <b>HAMBALYO HEER SARE AH!</b>\n\nWaxaad keentay <b>10 qof</b>! Waxaa laguu furay <b>VIP Lifetime Partner (Multi-Posting & Auto-Schedules Bilaash ah)</b>!")
                        else:
                            send_message(int(ref_uid), f"🎉 <b>Qof cusub ayaa ku soo biiray link-gaaga! (+25 dhibcood)</b>\n\nWaxaad keentay: <b>{ref_count}/10 qof</b>. Markaad gaarto 10 qof waxaad helaysaa VIP Permanent Access!")
                    except Exception:
                        pass
        save_tg_data(data)

    user = data["users"][uid]
    if first_name and (not user.get("name") or user.get("name").startswith("User_")):
        user["name"] = first_name
        save_tg_data(data)

    # Weekly quota reset
    if user.get("last_week_reset") != current_week:
        user["weekly_posts_used"] = 0
        user["last_week_reset"] = current_week
        save_tg_data(data)

    elapsed_days = int((now - user.get("created_at", now)) / 86400)
    days_left = max(0, 40 - elapsed_days)
    referrals_count = len(user.get("referrals", []))
    points = user.get("points", 20)
    is_vip = user.get("unlocked_permanent", False) or (referrals_count >= 10) or (points >= 250)
    is_active = is_vip or (days_left > 0)

    if is_vip:
        rank = "👑 VIP Lifetime Partner"
        limit = 9999
    elif referrals_count >= 5 or points >= 100:
        rank = "🚀 Team Leader"
        limit = 10
    else:
        rank = "⭐ Ambassador"
        limit = 5

    posts_used = user.get("weekly_posts_used", 0)
    posts_left = "Unlimited (∞)" if is_vip else max(0, limit - posts_used)

    return {
        "user_id": uid,
        "name": user.get("name", first_name or f"User_{uid[-4:]}"),
        "days_left": days_left,
        "referrals_count": referrals_count,
        "points": points,
        "rank": rank,
        "is_permanent": is_vip,
        "is_active": is_active,
        "weekly_posts_used": posts_used,
        "weekly_posts_limit": limit,
        "posts_left": posts_left,
        "channels": user.get("channels", []),
        "groups": user.get("groups", []),
        "schedule": user.get("schedule", {"morning": True, "noon": False, "evening": True}),
        "referral_link": f"https://t.me/Baahiyebot?start=ref_{uid}"
    }

def record_user_post(user_id):
    data = load_tg_data()
    uid = str(user_id)
    if uid in data["users"]:
        data["users"][uid]["weekly_posts_used"] = data["users"][uid].get("weekly_posts_used", 0) + 1
        data["users"][uid]["points"] = data["users"][uid].get("points", 20) + 5
        save_tg_data(data)

def add_user_channel(user_id, channel_name):
    data = load_tg_data()
    uid = str(user_id)
    if uid in data["users"]:
        chans = data["users"][uid].setdefault("channels", [])
        if channel_name not in chans:
            chans.append(channel_name)
            save_tg_data(data)
            return True
    return False

def toggle_user_schedule(user_id, slot):
    data = load_tg_data()
    uid = str(user_id)
    if uid in data["users"]:
        sched = data["users"][uid].setdefault("schedule", {"morning": True, "noon": False, "evening": True})
        sched[slot] = not sched.get(slot, False)
        save_tg_data(data)
        return sched[slot]
    return False

def get_leaderboard_data():
    data = load_tg_data()
    all_users = []
    for uid, u in data.get("users", {}).items():
        ref_count = len(u.get("referrals", []))
        pts = u.get("points", 20)
        name = u.get("name", f"Ambassador_{uid[-4:]}")
        all_users.append({
            "uid": uid,
            "name": name,
            "referrals": ref_count,
            "points": pts,
            "is_vip": u.get("unlocked_permanent", False) or ref_count >= 10 or pts >= 250
        })
    all_users.sort(key=lambda x: (x["referrals"], x["points"]), reverse=True)
    return all_users[:10]

def delete_message(chat_id, message_id):
    url = f"{API_URL}/deleteMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "message_id": message_id}, timeout=10)
    except Exception:
        pass

def configure_bot_menu_button():
    """Sets the Telegram Chat Menu Button to open the Mini App natively."""
    url = f"{API_URL}/setChatMenuButton"
    payload = {
        "menu_button": {
            "type": "web_app",
            "text": "📱 isbar-ai.com",
            "web_app": {"url": WEB_APP_URL}
        }
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        data = res.json()
        print(f"[*] Telegram Chat Menu Button set: {data.get('ok')}", flush=True)
    except Exception as e:
        print(f"[!] Error setting menu button: {e}", flush=True)

def send_photo(chat_id, photo_path, caption=None, reply_markup=None, parse_mode="HTML"):
    url = f"{API_URL}/sendPhoto"
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
        data["parse_mode"] = parse_mode
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        p = Path(photo_path)
        if p.exists():
            with open(p, "rb") as f:
                res = requests.post(url, data=data, files={"photo": f}, timeout=25)
                data_res = res.json()
                if data_res.get("ok"):
                    print(f"[*] Photo banner sent to {chat_id}", flush=True)
                    return data_res
                print(f"[!] sendPhoto failed: {data_res}", flush=True)
    except Exception as e:
        print(f"[!] Error sending photo: {e}", flush=True)
    if caption:
        return send_message(chat_id, caption, reply_markup, parse_mode=parse_mode)
    return None

def send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    url = f"{API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        res = requests.post(url, json=payload, timeout=15)
        data = res.json()
        if not data.get("ok") and parse_mode:
            payload.pop("parse_mode", None)
            res = requests.post(url, json=payload, timeout=15)
            data = res.json()
        print(f"[*] Message sent to {chat_id} (OK: {data.get('ok')})", flush=True)
        return data
    except Exception as e:
        print(f"[!] Error sending message to {chat_id}: {e}", flush=True)
        return None

def answer_callback_query(callback_query_id, text=None):
    url = f"{API_URL}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass

FIELD_NAMES = {
    "finance": "📊 Maamul & Xisaabaad",
    "sales": "📞 Customer Care & Iib",
    "health": "🏥 Caafimaad & NGO",
    "edu": "📚 Waxbarasho & Macallin",
    "tech": "💻 IT & Farsamo",
    "logistics": "📦 Logistics & Gaadiid"
}

LOCATION_NAMES = {
    "muqdisho": "🇸🇴 Muqdisho",
    "hargeysa": "🇸🇴 Hargeysa & Puntland",
    "nairobi": "🇰🇪 Nairobi (Kenya)",
    "remote": "🌐 Remote (Online Guriga)",
    "canada": "🇨🇦 Diaspora (Canada & Global)"
}

EXP_NAMES = {
    "entry": "🌱 Ku cusub / Qalin-jabin (Entry)",
    "mid": "💼 1 ilaa 3 Sano oo Khibrad ah",
    "senior": "🏆 3+ Sano (Khibrad Sare)"
}

def get_main_keyboard():
    return {
        "inline_keyboard": [
            # Row 1: Full-width Web App button
            [
                {"text": "🚀 Fur Web App-ka (isbar-ai.com)", "web_app": {"url": WEB_APP_URL}}
            ],
            # Row 2: Prominent Interactive Quiz & All Jobs
            [
                {"text": "🎯 Quiz: Ii Raadi Shaqadayda 🧭", "callback_data": "quiz_q1"},
                {"text": "💼 Dhammaan Shaqooyinka 🔥", "callback_data": "menu_jobs"}
            ],
            # Row 3: Tools & Telegram Management
            [
                {"text": "⚡ Dhis CV (ATS)", "callback_data": "menu_cv"},
                {"text": "🤖 Maamulka Telegram", "callback_data": "menu_tg_admin"}
            ],
            # Row 4: 2-column Learning & Mentorship
            [
                {"text": "📚 Buugaagta Isbar", "callback_data": "menu_academy"},
                {"text": "📅 Ballan Live ah", "callback_data": "menu_booking"}
            ],
            # Row 5: 2-column Public Info & Community
            [
                {"text": "📞 Xidhiidhka & Taageerada", "callback_data": "menu_contact"},
                {"text": "📢 Baahi / Share", "callback_data": "menu_broadcast"}
            ],
            # Row 6: Open Source GitHub Showcase (100% Free & Open Source)
            [
                {"text": "⭐ GitHub (100% Free & Open Source)", "url": GITHUB_REPO_URL}
            ]
        ]
    }

def handle_start(chat_id, first_name):
    welcome_text = f"""🦅 <b>Shaqo Baahiye (@Baahiyebot)</b>

Ku soo dhowow <b>{first_name}</b>!
Madasha fursadaha shaqo (Maamul, Xisaabaad, Caafimaad, Iib, IT & Remote), CV ATS ah, iyo buugaagta Isbar.

🧭 <b>Shaqo ma raadinaysaa?</b> Guji <i>'🎯 Quiz: Ii Raadi Shaqadayda'</i> si 3 tallaabo laguu caawiyo!"""

    banner_path = BASE_DIR / "assets" / "shaqo_baahiye_banner.png"
    if banner_path.exists():
        send_photo(chat_id, banner_path, caption=welcome_text, reply_markup=get_main_keyboard())
    else:
        send_message(chat_id, welcome_text, get_main_keyboard())

def handle_jobs(chat_id):
    jobs = get_curated_somali_it_jobs()
    text = """💼 <b>Fursadaha Shaqada ee Hadda Bannaan:</b>
<i>(Soomaaliya, Bariga Afrika & Remote)</i>

Shaqo Baahiye wuxuu kuu raadinayaa dhammaan qeybaha: Maamul, Iib, Caafimaad, Waxbarasho, IT & Remote.\n\n"""
    
    for idx, j in enumerate(jobs[:5], 1):
        text += f"<b>{idx}. {j['title']}</b>\n"
        text += f"🏢 {j['company']} &bull; 📍 {j['location']}\n"
        text += f"🔗 <a href='{j['job_url']}'>Codsashada Tooska ah</a>\n\n"

    markup = {
        "inline_keyboard": [
            [{"text": "🎯 Quiz: Ii Raadi Shaqadayda 🧭", "callback_data": "quiz_q1"}],
            [{"text": "📱 Baadh Dhammaan Shaqooyinka (Web App)", "web_app": {"url": f"{WEB_APP_URL}#jobsSection"}}],
            [
                {"text": "🇸🇴 Soomaaliya & Bariga Afrika", "web_app": {"url": f"{WEB_APP_URL}#jobsSection"}},
                {"text": "🌐 Remote & Canada", "web_app": {"url": f"{WEB_APP_URL}#jobsSection"}}
            ],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_quiz_step1(chat_id):
    text = """🎯 <b>Quiz: Ii Raadi Shaqada Ku Habboon (Tallaabada 1/3)</b> 🧭

Dooro xirfadda ama qeybta aad ugu jeceshahay inaad ka shaqeyso:"""
    markup = {
        "inline_keyboard": [
            [
                {"text": "📊 Maamul & Xisaabaad", "callback_data": "quiz_f_finance"},
                {"text": "📞 Customer Care & Iib", "callback_data": "quiz_f_sales"}
            ],
            [
                {"text": "🏥 Caafimaad & NGO", "callback_data": "quiz_f_health"},
                {"text": "📚 Waxbarasho & Macallin", "callback_data": "quiz_f_edu"}
            ],
            [
                {"text": "💻 IT & Farsamo", "callback_data": "quiz_f_tech"},
                {"text": "📦 Logistics & Gaadiid", "callback_data": "quiz_f_logistics"}
            ],
            [
                {"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}
            ]
        ]
    }
    send_message(chat_id, text, markup)

def handle_quiz_step2(chat_id, field):
    f_name = FIELD_NAMES.get(field, "Qeybta aad dooratay")
    text = f"""📍 <b>Quiz: Goobta aad Joogto ama Doonayso (Tallaabada 2/3)</b> 🌍

Doorka aad xiiseyso: <b>{f_name}</b>
Hadda dooro goobta aad shaqada ka raadinayso:"""
    markup = {
        "inline_keyboard": [
            [
                {"text": "🇸🇴 Muqdisho", "callback_data": f"quiz_l_{field}_muqdisho"},
                {"text": "🇸🇴 Hargeysa & Puntland", "callback_data": f"quiz_l_{field}_hargeysa"}
            ],
            [
                {"text": "🇰🇪 Nairobi (Kenya)", "callback_data": f"quiz_l_{field}_nairobi"},
                {"text": "🌐 Remote (Online Guriga)", "callback_data": f"quiz_l_{field}_remote"}
            ],
            [
                {"text": "🇨🇦 Diaspora (Canada & Global)", "callback_data": f"quiz_l_{field}_canada"}
            ],
            [
                {"text": "🔙 Dib u noqo", "callback_data": "quiz_q1"}
            ]
        ]
    }
    send_message(chat_id, text, markup)

def handle_quiz_step3(chat_id, field, location):
    f_name = FIELD_NAMES.get(field, "Qeybta")
    l_name = LOCATION_NAMES.get(location, "Goobta")
    text = f"""🎓 <b>Quiz: Heerka Khibraddaada (Tallaabada 3/3)</b> 💼

Doorka: <b>{f_name}</b> | Goobta: <b>{l_name}</b>
Intee in le'eg ayay le'eg tahay khibraddaadu?"""
    markup = {
        "inline_keyboard": [
            [
                {"text": "🌱 Ku cusub / Qalin-jabin (Entry)", "callback_data": f"quiz_r_{field}_{location}_entry"}
            ],
            [
                {"text": "💼 1 ilaa 3 Sano oo Khibrad ah", "callback_data": f"quiz_r_{field}_{location}_mid"}
            ],
            [
                {"text": "🏆 3+ Sano (Khibrad Sare)", "callback_data": f"quiz_r_{field}_{location}_senior"}
            ],
            [
                {"text": "🔙 Dib u noqo", "callback_data": f"quiz_f_{field}"}
            ]
        ]
    }
    send_message(chat_id, text, markup)

def handle_quiz_result(chat_id, field, location, exp):
    f_name = FIELD_NAMES.get(field, field)
    l_name = LOCATION_NAMES.get(location, location)
    e_name = EXP_NAMES.get(exp, exp)

    loc_query = "Muqdisho" if location == "muqdisho" else ("Hargeysa" if location == "hargeysa" else ("Nairobi" if location == "nairobi" else "Remote"))
    matched = get_curated_somali_it_jobs(term=field, location=loc_query)

    if exp == "entry":
        exp_tip = "💡 <b>Talo Qalin-jabiyaha:</b> CV-gaaga ku caddee maadooyinka aad ugu fiicnayd jaamacadda, mashruucyadii aad qabatay, tababarrada (internships), iyo luuqadaha."
    elif exp == "mid":
        exp_tip = "💡 <b>Talo Khibradda Dhexe:</b> CV-gaaga ku cabbir natiijooyin la taaban karo oo tiro leh (tusaale: 'Waxaan maareeyay xisaabaadka 100+ macaamiil ah')."
    else:
        exp_tip = "💡 <b>Talo Khibradda Sare:</b> Muuji hoggaamintaada, maaraynta kooxaha shaqada, iyo xallinta dhibaatooyinka waaweyn ee ganacsiga."

    text = f"""🎉 <b>Natiijada Quiz-kaaga Shaqo! 🧭</b>

• Doorka: <b>{f_name}</b>
• Goobta: <b>{l_name}</b>
• Khibradda: <b>{e_name}</b>

{exp_tip}

🔥 <b>Fursadaha Kuugu Habboon ee Hadda Bannaan:</b>\n\n"""

    for idx, j in enumerate(matched[:3], 1):
        text += f"<b>{idx}. {j['title']}</b>\n"
        text += f"🏢 {j['company']} &bull; 📍 {j['location']}\n"
        text += f"🔗 <a href='{j['job_url']}'>Codsashada Tooska ah</a>\n\n"

    markup = {
        "inline_keyboard": [
            [{"text": "⚡ Dhis CV Ku Habboon (ATS)", "callback_data": "menu_cv"}],
            [{"text": "📅 Qabso Ballan Live ah (Mentorship)", "callback_data": "menu_booking"}],
            [{"text": "🔄 Dib u bilaaw Quiz-ka", "callback_data": "quiz_q1"}],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_cv(chat_id):
    text = """⚡ <b>Diyaarinta CV ATS ah & Wareysiga:</b>

• 📄 <b>ATS Resume (1-Page):</b> Qaab nadiif ah oo nidaamyada shirkadaha u aqbalaan si toos ah.
• 📝 <b>Cover Letter:</b> Warqad codsi oo ku habboon doorkaaga.
• 🎯 <b>STAR Method:</b> Qaabka guusha ee looga jawaabo wareysiyada."""

    markup = {
        "inline_keyboard": [
            [{"text": "⚡ Dhis & Falanqee CV (Web App)", "web_app": {"url": f"{WEB_APP_URL}#assessSection"}}],
            [{"text": "📄 Soo Degso Resume Template (PDF)", "url": f"{WEB_APP_URL}/download/resume"}],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_academy(chat_id):
    text = """📚 <b>Akadeemiyada Isbar & Buugaagta:</b>

📖 <b>Buugaagta Isbar (Af-Soomaali):</b>
• 💻 <b>ISBAR COMPUTER</b> ($5) — Windows 11, Office, Photoshop
• 👨‍💻 <b>ISBAR PROGRAMMING</b> ($5) — Web, Python, Database
• 🧠 <b>ISBAR AI BASIC</b> ($7) — AI, Automation & Ganacsiga
• 🤖 <b>ISBAR Prompts</b> — 🎁 <b>Bilaash</b>

📬 <b>Hel 2 Buug oo Bilaash ah (Free):</b>
Ku biir warsidaha <a href="https://dhegeysobuug.substack.com/">dhegeysobuug.substack.com</a> si aad <b>2 Buug oo Bilaash ah</b> si toos ah ugu hesho inbox-kaaga!"""

    markup = {
        "inline_keyboard": [
            [{"text": "📬 Hel 2 Buug oo Free ah (Substack)", "url": DHEGEYSO_BUUG_SUBSTACK}],
            [{"text": "📱 Gal Akadeemiyada Isbar (Web App)", "web_app": {"url": f"{WEB_APP_URL}#coursesHubSection"}}],
            [
                {"text": "💬 Dalbo Buug (WhatsApp)", "url": "https://wa.me/15873064137?text=Salamaat%20Mohamed,%20waxaan%20rabaa%20buug%20Isbar"},
                {"text": "🎁 ChatGPT Prompts (Free)", "web_app": {"url": f"{WEB_APP_URL}#coursesHubSection"}}
            ],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
        ]
    }
    send_message(chat_id, text, markup)

BOOKING_SERVICES = {
    "ai": {
        "title": "AI & Chatbots Coaching",
        "duration": "45 Daqiiqo",
        "badge": "🚀 Live 1-on-1 Coaching",
        "desc": "Baro dhismaha nidaamyada AI Automation (n8n, Python Bots, Make, OpenAI API). Sida aad ugu dhisi lahayd bots Telegram iyo WhatsApp ganacsiyada iyo waxbarashada.",
        "icon": "🚀",
        "wa_text": "Salamaat Mohamed, waxaan rabaa ballan Live ah oo ku saabsan AI & Chatbots Coaching."
    },
    "cv": {
        "title": "CV ATS & Interview Prep",
        "duration": "30 Daqiiqo",
        "badge": "📄 1-on-1 Mentorship",
        "desc": "Dib-u-eegis toos ah oo CV-gaaga ah si uu u dhaafo nidaamyada ATS. Tababarka wareysiyada shaqada adag (STAR Method) iyo diyaarinta LinkedIn.",
        "icon": "📄",
        "wa_text": "Salamaat Mohamed, waxaan rabaa ballan Live ah oo ku saabsan CV ATS Review & Tababarka Wareysiga."
    },
    "career": {
        "title": "Career Roadmapping & Shaqo",
        "duration": "30 Daqiiqo",
        "badge": "🧭 Istaraatiijiyadda Shaqada",
        "desc": "Qorshaha shaqo raadinta (Soomaaliya, Bariga Afrika, Remote iyo Canada). Shahaadooyinka la rabo iyo khariidadda guusha ee qalin-jabiyaha.",
        "icon": "🧭",
        "wa_text": "Salamaat Mohamed, waxaan rabaa ballan Live ah oo ku saabsan Career Roadmapping & Mentorship."
    }
}

def handle_booking(chat_id):
    text = """╔═══════════════════════════════════════╗
   📅  XARUNTA BALLAMAHA & MENTORSHIP-KA
   👨‍🏫  Mohamed Yasin (Direct 1-on-1)
╚═══════════════════════════════════════╝

✨ <b>Dooro Kaarka Adeegga aad u baahan tahay (Interactive Cards):</b>
Kulan toos ah oo 1-on-1 ah (Google Meet, Zoom, ama WhatsApp Audio) oo aad toos ula yeelanayso <b>Mohamed Yasin</b> (Edmonton, Canada 🇨🇦 & Global).

1️⃣ 🚀 <b>AI & Chatbots Coaching (45 Min)</b>
• n8n, Make & Python Bots
• Isku xirka Telegram, WhatsApp & APIs

2️⃣ 📄 <b>CV ATS & Interview Prep (30 Min)</b>
• Hagaajinta CV-gaaga heerka ATS
• Tababarka wareysiyada adag (STAR Method)

3️⃣ 🧭 <b>Career Roadmapping & Shaqo (30 Min)</b>
• Istaraatiijiyadda fursadaha shaqo (Somalia & Global)
• Hagidda shahaadooyinka Google, AWS & Coursera

<i>Guji mid ka mid ah kaadhadhka hoose si aad u doorato waqtigaaga:</i>"""

    markup = {
        "inline_keyboard": [
            [
                {"text": "🚀 1. Card: AI & Chatbots", "callback_data": "book_card_ai"},
                {"text": "📄 2. Card: CV ATS & Wareysi", "callback_data": "book_card_cv"}
            ],
            [
                {"text": "🧭 3. Card: Career Mentorship", "callback_data": "book_card_career"}
            ],
            [
                {"text": "📱 Foomka Web App (isbar-ai.com)", "web_app": {"url": f"{WEB_APP_URL}#bookingSection"}},
                {"text": "💬 WhatsApp Toos ah", "url": "https://wa.me/15873064137?text=Salamaat%20Mohamed,%20waxaan%20rabaa%20ballan%20mentorship"}
            ],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_booking_card(chat_id, service_key):
    s = BOOKING_SERVICES.get(service_key, BOOKING_SERVICES["career"])
    text = f"""┌───────────────────────────────────────┐
   {s['icon']} <b>KAARKA: {s['title'].upper()}</b>
   Muddada: {s['duration']} | Online 1-on-1
└───────────────────────────────────────┘

✨ <b>Maxaa ku jira kulankan?</b>
{s['desc']}

🕒 <b>Dooro Waqtiga kugu habboon maanta:</b>"""

    wa_link = f"https://wa.me/15873064137?text={urllib.parse.quote(s['wa_text'])}"

    markup = {
        "inline_keyboard": [
            [
                {"text": "🌅 Subax: 10:00 AM", "callback_data": f"book_slot_{service_key}_10am"},
                {"text": "☀️ Galab: 02:00 PM", "callback_data": f"book_slot_{service_key}_2pm"}
            ],
            [
                {"text": "🌙 Habeen: 08:00 PM", "callback_data": f"book_slot_{service_key}_8pm"}
            ],
            [
                {"text": "📲 Xaqiiji WhatsApp (+1 587-306-4137)", "url": wa_link}
            ],
            [
                {"text": "🔙 Dib ugu noqo Kaadhadhka", "callback_data": "menu_booking"}
            ]
        ]
    }
    send_message(chat_id, text, markup)

def handle_booking_slot_confirm(chat_id, service_key, time_slot):
    s = BOOKING_SERVICES.get(service_key, BOOKING_SERVICES["career"])
    slot_label = "10:00 AM Subaxnimo" if time_slot == "10am" else ("02:00 PM Galabnimo" if time_slot == "2pm" else "08:00 PM Habeennimo")
    
    confirm_msg = f"Salamaat Mohamed, waxaan doortay ballanta '{s['title']}' waqtiga: {slot_label}. Fadlan ii xaqiiji."
    wa_url = f"https://wa.me/15873064137?text={urllib.parse.quote(confirm_msg)}"

    text = f"""🎉 <b>BALLANKAAGA WAA LA DOORTAY!</b>

• 📌 <b>Adeegga:</b> {s['title']}
• ⏱️ <b>Muddada:</b> {s['duration']}
• 🕒 <b>Waqtiga:</b> {slot_label}
• 👨‍🏫 <b>Khubaro:</b> Mohamed Yasin

Guji badhanka hoose si aad WhatsApp-ka Mohamed Yasin ugu dirto xaqiijinta tooska ah:"""

    markup = {
        "inline_keyboard": [
            [{"text": "💬 Dir Xaqiijinta WhatsApp (1-Tap)", "url": wa_url}],
            [{"text": "📱 Ku Buuxi Foomka isbar-ai.com", "web_app": {"url": f"{WEB_APP_URL}#bookingSection"}}],
            [{"text": "🔙 Kaadhadhka Kale", "callback_data": "menu_booking"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_contact(chat_id):
    text = """📞 <b>Xidhiidhka & Taageerada (Support & Contacts):</b>

Dooro nooca caawinaad ee aad doonayso:

🤖 <b>1. Kaaliyaha AI (Bot Chat):</b>
Wuxuu si toos ah kaaga caawinayaa raadinta shaqooyinka, talooyinka CV-ga, iyo buugaagta. Halkan toos ugu qor su'aashaada!

👤 <b>2. Qof Dhab ah (Human Support):</b>
Kala xidhiidh <b>Mohamed Yasin</b> toos:
👉 <b>Telegram:</b> @MFARATOON
👉 <b>WhatsApp:</b> +1 (587) 306-4137

📬 <b>3. Buugaagta Bilaashka ah:</b>
<a href="https://dhegeysobuug.substack.com/">dhegeysobuug.substack.com</a> (2 Buug oo Free ah)"""

    markup = {
        "inline_keyboard": [
            [
                {"text": "🤖 La Hadal Kaaliyaha AI (Chat)", "callback_data": "contact_ai_chat"},
                {"text": "👤 Human Support (@MFARATOON)", "url": "https://t.me/MFARATOON"}
            ],
            [
                {"text": "📱 WhatsApp Toos ah", "url": "https://wa.me/15873064137?text=Salamaat%20Mohamed,%20waxaan%20doonayaa%20caawinaad"},
                {"text": "📬 Hel 2 Buug Free", "url": DHEGEYSO_BUUG_SUBSTACK}
            ],
            [
                {"text": "📺 YouTube (@Mfaratoon)", "url": YOUTUBE_URL},
                {"text": "🌐 isbar-ai.com", "url": PRIMARY_DOMAIN}
            ],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
        ]
    }
    send_message(chat_id, text, markup)

# ========================================================
# 2. MANAGERS HUB: PROFILE, LEADERBOARD, MULTIPOSTING, AUTOMATION
# ========================================================

def handle_tg_admin(chat_id, user_id=None, first_name=None):
    uid = user_id or chat_id
    rec = get_user_record(uid, first_name=first_name)
    status_badge = "👑 VIP Lifetime" if rec["is_permanent"] else f"⏳ {rec['days_left']} Maalmood"
    
    text = f"""╔═══════════════════════════════════════╗
   👑  MAAMULKA TELEGRAM (MANAGERS HUB)
   👤  {rec['name']} | {rec['rank']}
╚═══════════════════════════════════════╝

📊 <b>Xaaladdaada & Dhibcahaaga:</b>
• 🎖️ Darajada: <b>{rec['rank']}</b>
• 👥 Referrals: <b>{rec['referrals_count']}/10 qof</b> ({status_badge})
• 🏆 Dhibcaha: <b>{rec['points']} pts</b> (+25 pt referral, +5 pt post)
• 📝 Post Quota: <b>{rec['posts_left']}</b> (Todobaadkan)
• 📢 Channels & Groups ku xiran: <b>{len(rec['channels'])} channel, {len(rec['groups'])} group</b>

🚀 <b>Aaladaha Maamulaha:</b> Dooro adeegga aad doonayso:"""

    markup = {
        "inline_keyboard": [
            [
                {"text": "📢 Multi-Posting & Badhamo", "callback_data": "tg_multipost"},
                {"text": "⏰ Jadwalka & Automation", "callback_data": "tg_schedule"}
            ],
            [
                {"text": "🎓 3-da Fasalka English Tutor (AI)", "callback_data": "tg_channels"},
                {"text": "💡 AI Generator (2 Tusaale / Manhaj)", "callback_data": "tg_ai_gen"}
            ],
            [
                {"text": "👤 Profile & Quota", "callback_data": "tg_profile"},
                {"text": "🏆 Ambassador Leaderboard", "callback_data": "tg_leaderboard"}
            ],
            [
                {"text": "➕ Ku Xir Channel/Group", "callback_data": "tg_add_channel"},
                {"text": "🛡️ Classroom Shield (Groups)", "callback_data": "tg_groups"}
            ],
            [
                {"text": "🔙 Ku noqo Menu-ga Weyn", "callback_data": "menu_main"}
            ]
        ]
    }
    send_message(chat_id, text, markup)

def handle_tg_profile(chat_id, user_id=None):
    uid = user_id or chat_id
    rec = get_user_record(uid)
    
    text = f"""╔═══════════════════════════════════════╗
   👤  PROFILE-KA AMBASSADOR / MANAGER
╚═══════════════════════════════════════╝

• <b>Magaca:</b> {rec['name']}
• <b>ID:</b> <code>{uid}</code>
• <b>Darajada:</b> {rec['rank']}
• <b>Dhibcaha:</b> {rec['points']} Dhibcood
• <b>Dadka aad keentay:</b> {rec['referrals_count']} qof (10 qof = VIP Lifetime)
• <b>Post Quota (Weekly):</b> {rec['posts_left']}
• <b>Channels ku xiran:</b> {', '.join(rec['channels']) if rec['channels'] else 'Ma jiraan (Guji Ku Xir Channel)'}

🎁 <b>Faa'iidada Team-ka & Share-ka:</b>
Qof kasta oo share gareeya wuxuu toddobaadkii helayaa <b>5 Post oo Bilaash ah</b> oo uu channels-ka ugu baahiyo! Markaad keento 10 qof waxaad noqonaysaa <b>👑 VIP Lifetime</b> (Unlimited Posts & Auto-Schedule)!

🔗 <b>Link-gaaga gaarka ah ee Referral-ka:</b>
<code>{rec['referral_link']}</code>"""

    share_url = f"https://t.me/share/url?url={urllib.parse.quote(rec['referral_link'])}&text={urllib.parse.quote('🚀 Ku biir Shaqo Baahiye (@Baahiyebot) - Hel shaqooyinka, CV ATS ah, iyo maamulka Telegram!')}"

    markup = {
        "inline_keyboard": [
            [{"text": "📤 Share Link-gaaga (Hel Dhibco & VIP)", "url": share_url}],
            [{"text": "🏆 Eeg Leaderboard-ka", "callback_data": "tg_leaderboard"}],
            [{"text": "🔙 Ku noqo Maamulka", "callback_data": "menu_tg_admin"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_tg_leaderboard(chat_id, current_user_id=None):
    c_uid = str(current_user_id or chat_id)
    leaders = get_leaderboard_data()
    
    text = """╔═══════════════════════════════════════╗
   🏆  SHAXDA HORYAALKA (AMBASSADORS)
   Top Promoters & Team Managers
╚═══════════════════════════════════════╝\n\n"""

    badges = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    for i, u in enumerate(leaders):
        badge = badges[i] if i < len(badges) else f"{i+1}."
        vip_tag = "👑 VIP" if u["is_vip"] else "⭐ Amb"
        you_tag = " 👉 <i>(Adiga)</i>" if u["uid"] == c_uid else ""
        text += f"{badge} <b>{u['name']}</b> ({vip_tag}): {u['referrals']} Referrals | {u['points']} pts{you_tag}\n"

    text += "\n💡 <b>Sida aad Safka Hore ugu Soo Gali karto:</b>\nShare-garee link-gaaga referral-ka si aad u hesho <b>+25 pts</b> qof kasta, una furato VIP Lifetime!"

    markup = {
        "inline_keyboard": [
            [{"text": "📤 Share Link-gaaga Hadda", "callback_data": "tg_profile"}],
            [{"text": "🔙 Ku noqo Maamulka", "callback_data": "menu_tg_admin"}]
        ]
    }
    send_message(chat_id, text, markup)

# ========================================================
# 3. MULTI-POSTING ENGINE (WITH BUTTONS & LINKS)
# ========================================================

def handle_tg_multipost(chat_id, user_id=None):
    uid = user_id or chat_id
    rec = get_user_record(uid)
    
    if not rec["is_permanent"] and rec["weekly_posts_used"] >= rec["weekly_posts_limit"]:
        text = f"""⚠️ <b>Xadka Post-yada Todobaadkan Waa Buuxsamay:</b>

Waxaad isticmaashay <b>{rec['weekly_posts_used']}/{rec['weekly_posts_limit']}</b> posts ee bilaashka ahaa todobaadkan.

🚀 <b>Sida loo kordhiyo:</b>
• Share-garee link-gaaga si aad u hesho <b>Post-yo dheeraad ah</b>.
• Ama keen 10 qof si aad u furato <b>👑 VIP Lifetime (Unlimited Posts)</b>!"""
        markup = {
            "inline_keyboard": [
                [{"text": "🎁 Share-garee & Fur Posts Dheeraad ah", "callback_data": "tg_profile"}],
                [{"text": "🔙 Ku noqo Maamulka", "callback_data": "menu_tg_admin"}]
            ]
        }
        send_message(chat_id, text, markup)
        return

    text = f"""📢 <b>Xarunta Multi-Posting-ka & Badhamada Casriga ah:</b>

• Quota: <b>{rec['posts_left']}</b> post baa kuu haray
• Channels ku xiran: <b>{len(rec['channels'])}</b> ({', '.join(rec['channels']) if rec['channels'] else 'Ma jiraan - Default Mode'})

Dooro nooca post-ka aad rabto inaad u diyaariso kanaaladaada:"""

    markup = {
        "inline_keyboard": [
            [
                {"text": "📣 1. Ogeysiis Degdeg ah (Announcement)", "callback_data": "tg_mp_quick"},
                {"text": "💼 2. Fursad Shaqo (Job Post)", "callback_data": "tg_mp_job"}
            ],
            [
                {"text": "📚 3. Cashar / Manhaj (Lesson Post)", "callback_data": "tg_mp_lesson"},
                {"text": "✍️ 4. Qor Qoraal Gaar ah (Custom)", "callback_data": "tg_mp_custom"}
            ],
            [
                {"text": "➕ Ku Xir Channel Cusub", "callback_data": "tg_add_channel"}
            ],
            [
                {"text": "🔙 Ku noqo Maamulka", "callback_data": "menu_tg_admin"}
            ]
        ]
    }
    send_message(chat_id, text, markup)

def handle_tg_multipost_preview(chat_id, user_id, post_type):
    if post_type == "quick":
        post_text = """📣 <b>OGEYSIIS MUHIIM AH:</b>

Waxaa dhammaan xubnaha lagu wargelinayaa in fursado shaqo oo cusub, koorsooyinka AI Automation-ka, iyo 2 buug oo bilaash ah laga heli karo madashayada rasmiga ah!

Ka faa'iideyso fursadaha maanta ka hor intaysan dhicin."""
    elif post_type == "job":
        post_text = """💼 <b>FURSAD SHAQO OO CUSUB:</b>

🏢 <b>Shirkadda:</b> Somali Tech Hub & Partner NGOs
📍 <b>Goobta:</b> Muqdisho / Hargeysa / Remote
🎓 <b>Doorka:</b> IT Support & Administrative Coordinator
📅 <b>Xilliga:</b> Waqti Buuxa (Full-time)

🚀 Codso hadda adoo adeegsanaya link-ga hoose:"""
    elif post_type == "lesson":
        post_text = """🇬🇧 <b>DAILY ENGLISH LESSON:</b>

📚 <b>Word of the Day:</b> 'Streamline' (Habayn iyo Fududeyn)
<i>"We use AI tools to streamline our daily communication."</i>
(Waxaan u adeegsannaa aaladaha AI si aan u fududeyno wada-xiriirka maalinlaha ah).

🎯 <b>Practice Question:</b>
Sidee Ingiriis ahaan loogu dhahaa: <i>'Shaqadaydu waa computer support'</i>?
👉 <i>"My job is computer support."</i>"""
    else:
        post_text = "Qoraalkaaga gaarka ah."

    preview_wrapper = f"""👁️ <b>HOR-DHAC (POST PREVIEW):</b>
<i>Sidan ayuu post-ku ugu muuqan doonaa channel-kaaga:</i>
━━━━━━━━━━━━━━━━━━━━━
{post_text}
━━━━━━━━━━━━━━━━━━━━━

Badhamada ku lifaaqan:
[ 🌐 Booqo Link-ga ] | [ 📱 Ka Qaybgal ]"""

    markup = {
        "inline_keyboard": [
            [{"text": "🚀 Baahi Hadda (Broadcast to Channels)", "callback_data": f"tg_mp_send_{post_type}"}],
            [{"text": "🔙 Ka Noqo", "callback_data": "tg_multipost"}]
        ]
    }
    send_message(chat_id, preview_wrapper, markup)

def handle_tg_multipost_send(chat_id, user_id, post_type):
    uid = user_id or chat_id
    rec = get_user_record(uid)
    
    if not rec["is_permanent"] and rec["weekly_posts_used"] >= rec["weekly_posts_limit"]:
        send_message(chat_id, "⚠️ Quota-daadii waa buuxsantay todobaadkan! Keen dad dheeraad ah si aad u hesho posts bilaash ah.")
        return

    if post_type == "quick":
        content = "📣 <b>OGEYSIIS MUHIIM AH:</b>\n\nFursado shaqo oo cusub, koorsooyin AI ah iyo 2 buug oo bilaash ah ka hel madashayada rasmiga ah!"
        markup = {"inline_keyboard": [[{"text": "🌐 Booqo isbar-ai.com", "url": PRIMARY_DOMAIN}], [{"text": "📱 @Baahiyebot", "url": "https://t.me/Baahiyebot"}]]}
    elif post_type == "job":
        content = "💼 <b>FURSAD SHAQO OO CUSUB:</b>\n\nIT Support, Admin & Remote roles ka raadi Shaqo Baahiye!"
        markup = {"inline_keyboard": [[{"text": "🚀 Codso Hadda", "url": f"{PRIMARY_DOMAIN}#jobsSection"}]]}
    else:
        content = "🇬🇧 <b>DAILY ENGLISH LESSON:</b>\n\nKu baro af Ingiriisiga heer kasta bot-ka @Baahiyebot!"
        markup = {"inline_keyboard": [[{"text": "📖 Ka Qaybgal", "url": "https://t.me/Baahiyebot?start=channels"}]]}

    success_count = 0
    channels_to_send = rec["channels"]
    
    if channels_to_send:
        for ch in channels_to_send:
            res = send_message(ch, content, markup)
            if res and res.get("ok"):
                success_count += 1
    else:
        send_message(chat_id, f"📢 <b>[SIMULATION TEST POST]</b>\n\n{content}", markup)
        success_count = 1

    record_user_post(uid)
    
    send_message(chat_id, f"""✅ <b>BAAHINTII WAA LA GUULEYSTAY!</b>

• Post-ka waxaa loo diray: <b>{success_count}</b> goobood
• Dhibco laguugu daray: <b>+5 Points</b> 🏆
• Quota haray: <b>{get_user_record(uid)['posts_left']}</b>""", {
        "inline_keyboard": [
            [{"text": "📢 Samee Post Kale", "callback_data": "tg_multipost"}],
            [{"text": "🔙 Ku noqo Maamulka", "callback_data": "menu_tg_admin"}]
        ]
    })

# ========================================================
# 4. JADWALKA & AUTOMATION (SCHEDULE POSTS)
# ========================================================

def handle_tg_schedule(chat_id, user_id=None):
    uid = user_id or chat_id
    rec = get_user_record(uid)
    sched = rec["schedule"]
    
    m_icon = "✅" if sched.get("morning") else "❌"
    n_icon = "✅" if sched.get("noon") else "❌"
    e_icon = "✅" if sched.get("evening") else "❌"

    text = f"""⏰ <b>Jadwalka & Posting Automation ee Channels-ka:</b>

Bot-ku wuxuu si otomaatig ah channels-kaaga ugu baahin karaa casharro iyo ogeysiisyada waqtiyada aad doorato:

1. 🌅 <b>Subaxdii (08:00 AM):</b> {m_icon} Daily English Lesson & Tech Tip
2. ☀️ <b>Duhurdii (01:00 PM):</b> {n_icon} Fursadaha Shaqada & Ogeysiis
3. 🌙 <b>Habeenkii (08:00 PM):</b> {e_icon} Interactive Quiz & Su'aalaha Fasalada

<i>Guji badhamada hoose si aad u shido (ON) ama u damiso (OFF) waqtiyada:</i>"""

    markup = {
        "inline_keyboard": [
            [
                {"text": f"{m_icon} Subax 08:00 AM", "callback_data": "tg_sched_toggle_morning"},
                {"text": f"{n_icon} Duhur 01:00 PM", "callback_data": "tg_sched_toggle_noon"}
            ],
            [
                {"text": f"{e_icon} Habeen 08:00 PM", "callback_data": "tg_sched_toggle_evening"}
            ],
            [
                {"text": "🔙 Ku noqo Maamulka", "callback_data": "menu_tg_admin"}
            ]
        ]
    }
    send_message(chat_id, text, markup)

# ========================================================
# 5. AUTONOMOUS 3-LEVEL ENGLISH CLASSES (AI TUTOR)
# ========================================================

CLASS_LEVELS = {
    "1": {
        "name": "Fasalka 1aad: Beginners (Aasaaska)",
        "badge": "🟢 Heerka 1aad",
        "title": "Salaanta, Erayada Maalinlaha ah & Wadahadalka Fudud",
        "vocab": [("Good morning", "Subax wanaagsan"), ("How are you?", "Sidee tahay?"), ("I want to learn", "Waxaan rabaa inaan barto")],
        "dialogue": "A: 'Hello Ahmed, how are you today?'\nB: 'I am doing great, thank you!'",
        "quiz_q": "Dooro jawaabta saxda ah ee 'Subax wanaagsan':",
        "quiz_opts": [("A. Good morning", "correct"), ("B. Good night", "wrong"), ("C. Goodbye", "wrong")]
    },
    "2": {
        "name": "Fasalka 2aad: Intermediate (Dhexe)",
        "badge": "🟡 Heerka 2aad",
        "title": "Naxwaha (Grammar), Tenses & Khaladaadka Badan",
        "vocab": [("Troubleshoot", "Xallinta ciladaha"), ("Improve", "Hagaajin / Kordhin"), ("Coordinate", "Isku-dubarid")],
        "dialogue": "A: 'Have you finished the computer certificate?'\nB: 'Yes, I finished it yesterday.'",
        "quiz_q": "Buuxi meesha bannaan: 'She _____ in Hargeisa for two years.'",
        "quiz_opts": [("A. has lived", "correct"), ("B. live", "wrong"), ("C. is live", "wrong")]
    },
    "3": {
        "name": "Fasalka 3aad: Advanced & Career (Sare)",
        "badge": "🔵 Heerka 3aad",
        "title": "Wareysiyada Shaqada (Job Interviews) & STAR Method",
        "vocab": [("Collaborate", "Wada-shaqayn kooxeed"), ("Implement", "Hirgelin nidaam cusub"), ("Streamline", "Fududeyn iyo hufnaan")],
        "dialogue": "'In my previous role, I collaborated with the tech team to resolve 50+ network issues.'",
        "quiz_q": "Maxay tahay ujeeddada STAR Method ee wareysiyada shaqada?",
        "quiz_opts": [("A. Situation, Task, Action, Result", "correct"), ("B. Simple, True, Active, Real", "wrong"), ("C. System, Tech, App, Run", "wrong")]
    }
}

def handle_tg_channels(chat_id):
    text = """🎓 <b>3-da Fasalka Luuqadda Ingiriisiga (Autonomous AI Tutor):</b>

Bot-ka <b>@Baahiyebot</b> ayaa si buuxda ula wareegaya maamulka iyo baridda 3-da fasal:

🟢 <b>Fasalka 1aad (Beginners):</b> Aasaaska, erayada, iyo wadahadalka maalinlaha ah.
🟡 <b>Fasalka 2aad (Intermediate):</b> Naxwaha, Tenses-ka, iyo qaladaadka caadiga ah.
🔵 <b>Fasalka 3aad (Advanced & Career):</b> Wareysiyada shaqada, STAR method, iyo erayada xirfadeed.

<i>Guji fasalka aad rabto inaad casharkiisa eegto ama u dirto channel-ka:</i>"""

    markup = {
        "inline_keyboard": [
            [{"text": "🟢 Fasalka 1aad: Beginners", "callback_data": "tg_class_1"}],
            [{"text": "🟡 Fasalka 2aad: Intermediate", "callback_data": "tg_class_2"}],
            [{"text": "🔵 Fasalka 3aad: Advanced & Career", "callback_data": "tg_class_3"}],
            [{"text": "🔙 Ku noqo Maamulka", "callback_data": "menu_tg_admin"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_tg_class_detail(chat_id, level_id):
    lvl = CLASS_LEVELS.get(level_id, CLASS_LEVELS["1"])
    
    text = f"""╔═══════════════════════════════════════╗
   {lvl['badge']}: {lvl['name'].upper()}
╚═══════════════════════════════════════╝

📚 <b>Mowduuca:</b> {lvl['title']}

📖 <b>Erayo Muhiim ah (Vocabulary):</b>\n"""
    for en, so in lvl["vocab"]:
        text += f"• <b>{en}:</b> {so}\n"

    text += f"""\n💬 <b>Wadahadal (Dialogue):</b>\n<i>{lvl['dialogue']}</i>\n
🎯 <b>Interactive Quiz:</b>
{lvl['quiz_q']}"""

    quiz_row = []
    for opt_text, status in lvl["quiz_opts"]:
        quiz_row.append({"text": opt_text.split('.')[0], "callback_data": f"tg_quiz_ans_{level_id}_{status}"})

    markup = {
        "inline_keyboard": [
            quiz_row,
            [
                {"text": "⚡ AI: Diyaari Cashar Cusub", "callback_data": f"tg_class_refresh_{level_id}"},
                {"text": "📢 U Dir Channel-ka (Post)", "callback_data": f"tg_class_broadcast_{level_id}"}
            ],
            [
                {"text": "🔙 Fasalada Kale", "callback_data": "tg_channels"}
            ]
        ]
    }
    send_message(chat_id, text, markup)

# ========================================================
# 6. AI KNOWLEDGE BASE & 2-EXAMPLES CONTENT GENERATOR
# ========================================================

def generate_ai_content(prompt_text):
    clean_prompt = prompt_text.strip()
    if OpenAI and os.environ.get("OPENAI_API_KEY"):
        try:
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            sys_msg = "Waxaad tahay Khubaro AI ah oo channels-ka iyo fasalada Telegram u diyaariya casharro iyo qoraallo waxbarasho oo heer sare ah. Isticmaal Af-Soomaali xarrago leh, cinwaanno cadcad, emojis, iyo layli gaaban."
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": f"Diyaari qoraal channel ku saabsan: {clean_prompt}"}
                ],
                max_tokens=650,
                temperature=0.7
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            pass
    # Intelligent fallback
    return f"""📢 <b>Cashar & Nuxur: {clean_prompt.capitalize()}</b>

✨ <b>Fahamka Guud:</b>
Barashada iyo fahamka <b>{clean_prompt}</b> waxay aasaas u tahay guushaada xirfadeed iyo horumarinta ganacsiga ama fasalkaaga.

🔍 <b>Laba Tusaale oo La Taaban Karo:</b>
1. <b>Tusaalaha 1aad:</b> Hirgelinta nidaam otomaatig ah oo badbaadiya 5+ saacadood oo shaqo maalinle ah.
2. <b>Tusaalaha 2aad:</b> Xiriir hufan oo la la yeesho macaamiisha ama ardayda adoo adeegsanaya aaladaha casriga ah.

🎯 <b>Layli Gaaban:</b>
Sidee baad nuxurkan ugu dabaqi kartaa shaqadaada maanta?

⭐ <i>Waxaa diyaariyay Kaaliyaha AI ee @Baahiyebot | isbar-ai.com</i>"""

def handle_tg_ai_generator(chat_id, user_id=None):
    text = """💡 <b>AI Content Generator (Manhaj & 2 Tusaale):</b>

Bot-ku wuxuu awood u leeyahay inuu qoraal ama cashar buuxa ka soo saaro laba tusaale oo aad siiso ama mowduuca fasalkaaga ka hadlayo:

1️⃣ <b>Laba Tusaale (2 Real Examples):</b>
Sii 2 tusaale (tusaale: <i>'Customer care bangi'</i> iyo <i>'Customer care dukaanka online'</i>), wuxuuna ka dhigayaa cashar nidaamsan oo layli leh!

2️⃣ <b>Mowduuc Toos ah (Topic Generator):</b>
Qor mowduuc kasta (IT, Xisaabaad, English, AI), isla markiiba post diyaar ah ayuu kuu soo saarayaa!

<i>Dooro mid ka mid ah fursadaha hoose:</i>"""

    markup = {
        "inline_keyboard": [
            [
                {"text": "💡 1. Sii 2 Tusaale (Generate)", "callback_data": "tg_ai_gen_ex"},
                {"text": "📝 2. Qor Mowduuc (Topic)", "callback_data": "tg_ai_gen_topic"}
            ],
            [
                {"text": "📚 Manhajka Koorsooyinka Isbar", "callback_data": "tg_docs"}
            ],
            [
                {"text": "🔙 Ku noqo Maamulka", "callback_data": "menu_tg_admin"}
            ]
        ]
    }
    send_message(chat_id, text, markup)

def handle_tg_add_channel(chat_id, user_id=None):
    uid = str(user_id or chat_id)
    USER_STATES[uid] = {"state": "waiting_channel"}

    text = """➕ <b>Ku Xir Channel-kaaga ama Group-kaaga:</b>

Si bot-ku uu ugu shubo casharrada, qoraallada, iyo multi-posting-ka:

1. 👑 <b>Ku dar Bot-ka:</b> Ku dar <code>@Baahiyebot</code> channel-kaaga ama group-kaaga adoo ka dhigaya <b>Admin</b> (oo leh rukhsadda <i>Post Messages</i>).
2. ✍️ <b>Qor Username-ka Channel-ka:</b> Halkan hadda toos ugu soo qor username-ka channel-ka (tusaale: <code>@channelkayga</code>).

<i>Fadlan hadda qor username-ka channel-ka:</i>"""

    markup = {
        "inline_keyboard": [
            [{"text": "🔙 Ka Noqo / Cancel", "callback_data": "menu_tg_admin"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_tg_groups(chat_id):
    text = """🛡️ <b>Maamulka Fasalada & Groups-ka (Classroom Shield):</b>

Sida aad ugu xirayso bot-ka fasalkaaga ama group-kaaga:

1. ➕ <b>Ku dar Bot-ka:</b> Ku dar <code>@Baahiyebot</code> group-ka ama fasalkaaga.
2. 👑 <b>Ka dhig Admin:</b> Sii rukhsadda <i>'Delete Messages'</i> si uu u tirtiro spam-ka iyo aflagaadada.
3. ⚡ <b>Shaqooyinka Otomaatiga ah:</b>
   • <b>Soo dhoweyn:</b> Arday kasta oo cusub wuxuu siinayaa fariin soo dhoweyn iyo xeerarka fasalka.
   • <b>Word Filter:</b> Erayada qadafka ah iyo links-ka spam-ka ah si degdeg ah ayuu u tirtirayaa.
   • <b>Kaaliyaha Su'aalaha:</b> Ardaydu waxay qori karaan <code>/ask [su'aasha]</code> AI-ga ayaana uga jawaabaya.

<i>Tijaabi hadda adoo ku daraya group-kaaga!</i>"""
    markup = {
        "inline_keyboard": [
            [{"text": "➕ Ku Dar Group (Direct)", "url": "https://t.me/Baahiyebot?startgroup=true"}],
            [{"text": "🤝 Xallinta Khilaafaadka", "callback_data": "tg_conflict"}],
            [{"text": "🔙 Ku noqo Maamulka", "callback_data": "menu_tg_admin"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_tg_conflict(chat_id):
    text = """🤝 <b>Xallinta Khilaafaadka & Ilaalinta Anshaxa Fasalada:</b>

Fasalada iyo group-yada Telegram marka arday badani isugu timaado:

1. ⚖️ <b>Xeerka Dhexdhexaadnimada:</b> Ha qaadan dhinac go'an haddii ardaydu is-qabtaan; ku hagi ujeedka waxbarashada.
2. 🚫 <b>Digniin Shakhsi ah:</b> Qofka anshax-xumada la yimaada, fariintiisa waa la tirtirayaa waxaana loo dirayaa digniin shakhsi ah.
3. 🕊️ <b>Qoraal Nabadeyn ah:</b> Bot-ku wuxuu si toos ah u dirayaa fariin dejin ah si jawiga waxbarashadu u ahaado mid deggan.
4. 🔇 <b>Xaddidaadda Qoraalka (Mute):</b> Hadii dooddu kululaato, admin-ku wuxuu xiri karaa qoraalka muddo 15 daqiiqo ah."""
    markup = {
        "inline_keyboard": [
            [{"text": "🛡️ Maamulka Groups-ka", "callback_data": "tg_groups"}],
            [{"text": "🔙 Ku noqo Maamulka", "callback_data": "menu_tg_admin"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_tg_docs(chat_id):
    text = """📚 <b>Soo Dir Manhajkaaga ama Xogtaada (Custom Knowledge Base):</b>

Ma rabtaa in bot-ka <b>@Baahiyebot</b> uu si gaar ah ardaydaada ugu sharaxo casharradaada iyo manhajkaaga?

1. 📄 <b>Noocyada Xogta:</b> Qoraal toos ah, syllabus, su'aalo & jawaabo, ama PDF.
2. 📩 <b>Sida Loo Soo Diro:</b>
   • Email: <code>Suxufi34@gmail.com</code>
   • WhatsApp: <code>+1 (587) 306-4137</code> (Mohamed Yasin)
3. ⚡ <b>Dhaqangelinta:</b> Waxaan manhajkaaga toos ugu lifaaqaynaa AI-ga bot-ka si uu ardaydaada fasalka ugu baro!"""
    markup = {
        "inline_keyboard": [
            [{"text": "💬 WhatsApp Toos ah (Mohamed Yasin)", "url": "https://wa.me/15873064137?text=Salamaat%20Mohamed,%20waxaan%20rabaa%20inaan%20soo%20diro%20manhajka%20fasalkayga"}],
            [{"text": "🔙 Ku noqo Maamulka", "callback_data": "menu_tg_admin"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_broadcast(chat_id):
    text = """📢 <b>Baahinta Fursadaha (Channels & Groups):</b>

Waxaad shaqooyinkan, buugaagta, iyo koorsooyinka bilaashka ah la wadaagi kartaa asxaabtaada ama channel-kaaga Telegram:"""

    markup = {
        "inline_keyboard": [
            [{"text": "📤 Share garee (One-Click)", "url": f"https://t.me/share/url?url=https://t.me/Baahiyebot&text={SHARE_TEXT}"}],
            [{"text": "⭐ Eeg GitHub Repository", "url": GITHUB_REPO_URL}],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
        ]
    }
    send_message(chat_id, text, markup)

def process_callback_query(callback_query):
    cq_id = callback_query.get("id")
    data = callback_query.get("data")
    message = callback_query.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    user_id = callback_query.get("from", {}).get("id") or chat_id

    print(f"[*] Callback query '{data}' from {chat_id} (User: {user_id})", flush=True)
    answer_callback_query(cq_id)

    if data == "menu_main":
        send_message(chat_id, "🦅 <b>Dooro adeegga aad u baahan tahay:</b>", get_main_keyboard())
    elif data == "quiz_q1":
        handle_quiz_step1(chat_id)
    elif data.startswith("quiz_f_"):
        field = data.replace("quiz_f_", "")
        handle_quiz_step2(chat_id, field)
    elif data.startswith("quiz_l_"):
        parts = data.split("_")
        if len(parts) >= 4:
            handle_quiz_step3(chat_id, parts[2], parts[3])
    elif data.startswith("quiz_r_"):
        parts = data.split("_")
        if len(parts) >= 5:
            handle_quiz_result(chat_id, parts[2], parts[3], parts[4])
    elif data == "menu_jobs":
        handle_jobs(chat_id)
    elif data == "menu_cv":
        handle_cv(chat_id)
    elif data == "menu_tg_admin":
        handle_tg_admin(chat_id, user_id)
    elif data == "tg_profile":
        handle_tg_profile(chat_id, user_id)
    elif data == "tg_leaderboard":
        handle_tg_leaderboard(chat_id, user_id)
    elif data == "tg_multipost":
        handle_tg_multipost(chat_id, user_id)
    elif data in ["tg_mp_quick", "tg_mp_job", "tg_mp_lesson"]:
        p_type = data.replace("tg_mp_", "")
        handle_tg_multipost_preview(chat_id, user_id, p_type)
    elif data.startswith("tg_mp_send_"):
        p_type = data.replace("tg_mp_send_", "")
        handle_tg_multipost_send(chat_id, user_id, p_type)
    elif data == "tg_mp_custom":
        USER_STATES[str(user_id)] = {"state": "waiting_custom_post"}
        send_message(chat_id, "✍️ <b>Qor Qoraalkaaga Gaarka ah:</b>\n\nFadlan halkan toos ugu soo qor fariinta aad rabto inaad u baahiso kanaaladaada.\n<i>(Tusaale: 'Waxaan bilownay fasal cusub oo bilaash ah...')</i>", {
            "inline_keyboard": [[{"text": "🔙 Ka Noqo / Cancel", "callback_data": "tg_multipost"}]]
        })
    elif data == "tg_schedule":
        handle_tg_schedule(chat_id, user_id)
    elif data.startswith("tg_sched_toggle_"):
        slot = data.replace("tg_sched_toggle_", "")
        toggle_user_schedule(user_id, slot)
        handle_tg_schedule(chat_id, user_id)
    elif data == "tg_groups":
        handle_tg_groups(chat_id)
    elif data == "tg_channels":
        handle_tg_channels(chat_id)
    elif data in ["tg_class_1", "tg_class_2", "tg_class_3"]:
        lvl_num = data.replace("tg_class_", "")
        handle_tg_class_detail(chat_id, lvl_num)
    elif data.startswith("tg_class_refresh_"):
        lvl_num = data.replace("tg_class_refresh_", "")
        send_message(chat_id, "⚡ <i>AI-gu wuxuu diyaarinayaa cashar cusub...</i>")
        handle_tg_class_detail(chat_id, lvl_num)
    elif data.startswith("tg_class_broadcast_"):
        lvl_num = data.replace("tg_class_broadcast_", "")
        handle_tg_multipost_send(chat_id, user_id, "lesson")
    elif data.startswith("tg_quiz_ans_"):
        parts = data.split("_")
        status = parts[-1] if len(parts) >= 4 else "wrong"
        if status == "correct":
            answer_callback_query(cq_id, "🎉 HAMBALYO! Jawaabtaadu waa sax! 🌟")
            send_message(chat_id, "🎉 <b>HAMBALYO!</b> Jawaabtaadu waa 100% sax! Horay u soco! 🌟")
        else:
            answer_callback_query(cq_id, "❌ Ma saxna. Isku day mar kale! 💪")
            send_message(chat_id, "❌ <b>Ma saxna!</b> Isku day mar kale adoo akhrinaya casharka kore. 💪")
    elif data == "tg_ai_gen":
        handle_tg_ai_generator(chat_id, user_id)
    elif data == "tg_ai_gen_ex":
        USER_STATES[str(user_id)] = {"state": "waiting_examples"}
        send_message(chat_id, "💡 <b>Sii 2 Tusaale oo AI-gu Cashar ka Dhigo:</b>\n\nHalkan hadda toos ugu qor laba tusaale oo dhab ah (tusaale: <i>'1. Sidee loo qoraa email codsi shaqo' iyo '2. Sidee looga jawaabaa su'aasha adag ee wareysiga'</i>):", {
            "inline_keyboard": [[{"text": "🔙 Ka Noqo", "callback_data": "tg_ai_gen"}]]
        })
    elif data == "tg_ai_gen_topic":
        USER_STATES[str(user_id)] = {"state": "waiting_topic"}
        send_message(chat_id, "📝 <b>Qor Mowduuca aad Rabto (Topic):</b>\n\nHalkan toos ugu qor mowduuc kasta oo aad rabto in AI-gu kuu diyaariyo (tusaale: <i>'Xisaabaadka ganacsiga yar yar'</i> ama <i>'Barashada Python'</i>):", {
            "inline_keyboard": [[{"text": "🔙 Ka Noqo", "callback_data": "tg_ai_gen"}]]
        })
    elif data == "tg_add_channel":
        handle_tg_add_channel(chat_id, user_id)
    elif data == "tg_referral":
        handle_tg_profile(chat_id, user_id)
    elif data == "tg_conflict":
        handle_tg_conflict(chat_id)
    elif data == "tg_docs":
        handle_tg_docs(chat_id)
    elif data == "menu_academy":
        handle_academy(chat_id)
    elif data == "menu_booking":
        handle_booking(chat_id)
    elif data.startswith("book_card_"):
        s_key = data.replace("book_card_", "")
        handle_booking_card(chat_id, s_key)
    elif data.startswith("book_slot_"):
        parts = data.split("_")
        if len(parts) >= 4:
            handle_booking_slot_confirm(chat_id, parts[2], parts[3])
    elif data == "menu_contact":
        handle_contact(chat_id)
    elif data == "contact_ai_chat":
        text = """🤖 <b>Kaaliyaha AI waa diyaar!</b>

Qor su'aashaada adoo adeegsanaya qoraal toos ah (tusaale: <i>'Ii raadi shaqo maamul ama IT'</i> ama <i>'Sideen CV u qoraa?'</i>). Kaaliyaha AI ayaa isla markiiba kuugu soo jawaabaya! 🚀"""
        send_message(chat_id, text, {"inline_keyboard": [[{"text": "🔙 Ku noqo Xidhiidhka", "callback_data": "menu_contact"}]]})
    elif data == "menu_broadcast":
        handle_broadcast(chat_id)

def process_message(message):
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    chat_type = chat.get("type", "private")
    is_group = chat_type in ["group", "supergroup"]
    text = message.get("text", "").strip()
    first_name = chat.get("first_name", "Walaal")
    user_id = message.get("from", {}).get("id") or chat_id
    uid_str = str(user_id)

    # Check Active Multi-step User States
    if uid_str in USER_STATES and not is_group and text:
        state = USER_STATES[uid_str].get("state")
        del USER_STATES[uid_str]
        
        if state == "waiting_channel":
            clean_ch = text.strip()
            if not clean_ch.startswith("@") and not clean_ch.startswith("-100"):
                clean_ch = "@" + clean_ch
            add_user_channel(uid_str, clean_ch)
            send_message(chat_id, f"🎉 <b>Channel-ka {clean_ch} si guul leh baa loogu xiray nidaamka!</b>\n\nHadda waxaad u diri kartaa Multi-Posting iyo casharro otomaatig ah!", {
                "inline_keyboard": [
                    [{"text": "📢 Samee Post Hadda", "callback_data": "tg_multipost"}],
                    [{"text": "🔙 Ku noqo Maamulka", "callback_data": "menu_tg_admin"}]
                ]
            })
            return
        elif state in ["waiting_examples", "waiting_topic", "waiting_custom_post"]:
            send_message(chat_id, "⏳ <i>AI-gu wuxuu diyaarinayaa nuxurka iyo casharkaaga...</i>")
            generated_content = generate_ai_content(text)
            send_message(chat_id, f"📝 <b>Qoraalkii Diyaarsanaa (Preview):</b>\n\n{generated_content}", {
                "inline_keyboard": [
                    [{"text": "🚀 Baahi Hadda (Broadcast)", "callback_data": "tg_mp_send_quick"}],
                    [{"text": "🔙 Ku noqo Maamulka", "callback_data": "menu_tg_admin"}]
                ]
            })
            return

    # 1. Handle New Chat Members in Groups (Classroom Welcome)
    if "new_chat_members" in message:
        for member in message["new_chat_members"]:
            m_name = member.get("first_name", "Arday")
            if member.get("is_bot") and member.get("username") == "Baahiyebot":
                send_message(chat_id, "👋 <b>Salamaat Dhammaan!</b> Waxaan ahay Kaaliyaha AI ee fasalka / group-ka. Waxaan diyaar u ahay inaan idinka caawiyo ilaalinta anshaxa, soo dhoweynta ardayda cusub, iyo ka jawaabista su'aalaha casharrada. Qor <code>/ask [su'aashaada]</code>!")
            elif not member.get("is_bot"):
                welcome_group = f"""👋 <b>Ku soo dhowow fasalka, {m_name}!</b>

📖 Fadlan ilaali anshaxa iyo xeerarka fasalka:
1. Ka fogow xayeysiisyada spam-ka ah iyo links-ka aan la ogolayn.
2. Is-ixtiraama oo ka faa'iideysta casharrada.
3. Haddii aad qabto su'aal ku saabsan casharka, qor <code>/ask [su'aashaada]</code>."""
                send_message(chat_id, welcome_group)
        return

    # 2. Profanity & Spam Filter in Groups
    if is_group and text:
        text_check = text.lower()
        has_profanity = any(re.search(r"\b" + re.escape(v) + r"\b", text_check) for v in VULGAR_WORDS)
        has_invite_spam = ("t.me/joinchat" in text_check or "t.me/+" in text_check) and not any(w in text_check for w in ["baahiyebot", "isbar-ai.com"])
        if has_profanity or has_invite_spam:
            msg_id = message.get("message_id")
            if msg_id:
                delete_message(chat_id, msg_id)
            sender_name = message.get("from", {}).get("first_name", "Walaal")
            send_message(chat_id, f"⚠️ <b>Digniin:</b> {sender_name}, fariintaada waa la tirtiray sababtoo ah waxay jabisay xeerarka anshaxa fasalka/group-ka.")
            return

    # 3. AI Assistant in Groups:
    if is_group and text:
        if text.startswith("/ask") or text.startswith("/suaal") or "@baahiyebot" in text.lower():
            clean_q = text.replace("/ask", "").replace("/suaal", "").replace("@baahiyebot", "").replace("@Baahiyebot", "").strip()
            if clean_q:
                ai_ans = get_career_ai_response(clean_q)
                html_ans = ai_ans.replace("**", "<b>", 1)
                while "**" in html_ans:
                    html_ans = html_ans.replace("**", "</b>", 1)
                    html_ans = html_ans.replace("**", "<b>", 1)
                send_message(chat_id, f"💡 <b>Jawaabta Kaaliyaha AI:</b>\n\n{html_ans}")
            else:
                send_message(chat_id, "💡 Fadlan qor su'aashaada adoo adeegsanaya: <code>/ask [su'aashaada]</code>")
            return
        # Don't respond to general group chatter unless invoked
        return

    if not text:
        return

    print(f"[*] Incoming message from {chat_id} ({first_name}): {text}", flush=True)
    text_lower = text.lower()

    # Handle Referral & Start parameters
    if text_lower.startswith("/start"):
        parts = text.split()
        if len(parts) > 1:
            param = parts[1].strip()
            if param.startswith("ref_"):
                referrer = param.replace("ref_", "")
                if referrer.isdigit():
                    get_user_record(user_id, referrer_id=int(referrer))
                handle_start(chat_id, first_name)
                return
            elif param == "tg_admin":
                handle_tg_admin(chat_id, user_id)
                return
            elif param in ["group_admin", "groups"]:
                handle_tg_groups(chat_id)
                return
            elif param in ["channel_admin", "channels"]:
                handle_tg_channels(chat_id)
                return
            elif param in ["quiz", "quize"]:
                handle_quiz_step1(chat_id)
                return
            elif param == "ref":
                handle_tg_referral(chat_id, user_id)
                return
        get_user_record(user_id)
        handle_start(chat_id, first_name)
        return

    elif text_lower in ["start", "bilaaw", "menu", "hi", "halo", "sxb", "salaam", "asc"]:
        handle_start(chat_id, first_name)
    elif text_lower in ["/quiz", "quiz", "quize", "shaqo raadi", "ii raadi shaqo", "ii raadi", "dooro", "xirfad"]:
        handle_quiz_step1(chat_id)
    elif text_lower in ["/admin", "/tg_admin", "maamul", "maamulka", "telegram", "fasal", "channel"]:
        handle_tg_admin(chat_id, user_id)
    elif text_lower in ["/ref", "referral", "keen", "share", "40 cisho"]:
        handle_tg_referral(chat_id, user_id)
    elif text_lower in ["/english", "english", "ingiriis", "cashar", "lesson"]:
        handle_tg_channels(chat_id)
    elif text_lower in ["/jobs", "shaqo", "shaqooyin", "jobs"]:
        handle_jobs(chat_id)
    elif text_lower in ["/cv", "resume", "wareysi"]:
        handle_cv(chat_id)
    elif text_lower in ["/academy", "/books", "/courses", "buug", "koorso", "isbar", "buugaag", "buugag", "soo dir"]:
        handle_academy(chat_id)
    elif text_lower in ["/booking", "ballan", "mentorship"]:
        handle_booking(chat_id)
    elif text_lower in ["/contact", "/support", "/help", "contact", "contacts", "xiriir", "xidhiidh", "taageero", "support", "help", "caawinaad", "human", "qof", "mfaratoon", "faratoon", "substack"]:
        handle_contact(chat_id)
    elif text_lower in ["/broadcast", "baahin"]:
        handle_broadcast(chat_id)
    elif any(w in text_lower for w in ["sida loo", "sidee loo", "sameeyaa", "repo", "source code", "shubo", "deploy", "dhis", "github", "opensource"]):
        reply_repo = f"""⭐ <b>Madashan waa 100% Free & Open Source (U fasaxan qof kasta):</b>

Repository-ga rasmiga ah waa bilaash oo qof kasta wuu ka faa'iideysan karaa ama horumarin karaa:
🔗 <a href='{GITHUB_REPO_URL}'>GitHub Repository</a>

🚀 <b>Ma rabtaa inaad barato sida nidaamkan oo kale loogu shubo loona dhiso iyadoo AI la adeegsanayo?</b>
Qofkii raba inuu barto sida loo dhiso loona shubo codsiyada casriga ah ee AI-ga, waxaad dooran kartaa <b>'Ballan Qabso'</b> (Live 1-on-1 Mentorship oo toos ah oo aad la yeelanayso <b>Mohamed Yasin</b>)."""
        send_message(chat_id, reply_repo, {
            "inline_keyboard": [
                [{"text": "📅 Qabso Ballan Live ah", "callback_data": "menu_booking"}],
                [{"text": "⭐ Eeg GitHub Repo", "url": GITHUB_REPO_URL}],
                [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
            ]
        })
    elif text_lower in ["/app", "miniapp", "app"]:
        send_message(chat_id, "🚀 <b>Guji badhanka hoose si aad u furto Web App-ka (isbar-ai.com):</b>", {
            "inline_keyboard": [
                [{"text": "📱 Fur isbar-ai.com", "web_app": {"url": WEB_APP_URL}}],
                [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
            ]
        })
    else:
        # Check spam
        is_spam, reason = is_spam_or_invalid(text)
        if is_spam:
            send_message(chat_id, reason)
            return

        # AI Career response
        ai_reply = get_career_ai_response(text)
        html_reply = ai_reply.replace("**", "<b>", 1)
        while "**" in html_reply:
            html_reply = html_reply.replace("**", "</b>", 1)
            html_reply = html_reply.replace("**", "<b>", 1)

        markup = {
            "inline_keyboard": [
                [{"text": "📱 Fur isbar-ai.com", "web_app": {"url": WEB_APP_URL}}],
                [{"text": "💼 Fursadaha Shaqada", "callback_data": "menu_jobs"}, {"text": "🔙 Menu-ga", "callback_data": "menu_main"}]
            ]
        }
        send_message(chat_id, html_reply, markup, parse_mode="HTML")

def run_bot_polling():
    print("\n=======================================================", flush=True)
    print("   Shaqo Baahiye Telegram Bot (@Baahiyebot)", flush=True)
    print("   Bot: @Baahiyebot (Clean & Modernized)", flush=True)
    print(f"   Domain: {PRIMARY_DOMAIN}", flush=True)
    print("=======================================================\n", flush=True)

    configure_bot_menu_button()

    offset = None
    while True:
        try:
            url = f"{API_URL}/getUpdates"
            params = {"timeout": 30}
            if offset:
                params["offset"] = offset

            res = requests.get(url, params=params, timeout=40)
            if res.status_code == 200:
                data = res.json()
                if data.get("ok"):
                    for update in data.get("result", []):
                        offset = update.get("update_id") + 1
                        if "message" in update:
                            process_message(update["message"])
                        elif "callback_query" in update:
                            process_callback_query(update["callback_query"])
            else:
                print(f"[!] getUpdates response code {res.status_code}: {res.text}", flush=True)
                time.sleep(5)
        except requests.exceptions.RequestException:
            time.sleep(2)
        except Exception as e:
            print(f"[!] Unexpected error in bot loop: {e}", flush=True)
            time.sleep(2)

if __name__ == "__main__":
    run_bot_polling()
