import os
import threading
from flask import Flask
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# 1. إنشاء خادم ويب خفيف لمنع الاستضافة المجانية من إيقاف البوت
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is alive and running!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# 2. قراءة التوكين الخاص بالبوت من متغيرة البيئة للتأمين
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

def get_nhtsa_details(vin):
    """جلب بيانات السيارة الأساسية مجاناً من المنصة الحكومية الأمريكية"""
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvalues/{vin}?format=json"
    try:
        res = requests.get(url, timeout=10).json()['Results'][0]
        make = res.get('Make', 'غير معروف')
        model = res.get('Model', 'غير معروف')
        year = res.get('ModelYear', 'غير معروف')
        displacement = res.get('DisplacementL', '')
        cylinders = res.get('EngineCylinders', '')
        engine = f"{displacement}L {cylinders} Cylinders".strip() if displacement else "غير محدد"
        return make, model, year, engine
    except Exception:
        return "غير معروف", "غير معروف", "غير معروف", "غير معروف"

def scrape_bidfax_data(vin):
    """كشط صور المزاد مجاناً من أرشيف BidFax"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    search_url = f"https://bidfax.info/?do=search&subaction=search&story={vin}"
    photos = []
    try:
        response = requests.get(search_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        first_result = soup.select_one('a.title') or soup.select_one('.post-title a')
        if first_result:
            car_page_url = first_result['href']
            car_page_res = requests.get(car_page_url, headers=headers, timeout=10)
            car_soup = BeautifulSoup(car_page_res.text, 'html.parser')
            img_tags = car_soup.select('.full-link') or car_soup.select('.fotorama img')
            for img in img_tags:
                src = img.get('href') or img.get('src')
                if src and src.startswith('http'):
                    photos.append(src)
    except Exception as e:
        print(f"Error scraping: {e}")
    return photos[:5] # استخراج أول 5 صور فقط

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """التعامل مع رسائل المستخدم وإرجاع التقرير"""
    vin = update.message.text.strip().upper()
    
    # التأكد من صحة طول رقم الشاصي القياسي (17 خانة)
    if len(vin) != 17:
        await update.message.reply_text("❌ عذراً، رقم الشاصي (VIN) يجب أن يتكون من 17 خانة.")
        return

    await update.message.reply_text("🔍 جاري البحث في أرشيف المزادات والمصادر المتاحة...")
    
    # جلب البيانات
    make, model, year, engine = get_nhtsa_details(vin)
    photos = scrape_bidfax_data(vin)

    # تجهيز التقرير
    report = f"🚗 **تقرير السيارة برقم الشاصي:**\n\n" \
             f"• **الشركة:** {make}\n" \
             f"• **الموديل:** {model}\n" \
             f"• **سنة الصنع:** {year}\n" \
             f"• **المحرك:** {engine}\n" \
             f"• **رقم الشاصي:** `{vin}`"

    await update.message.reply_text(report, parse_mode='Markdown')

    # إرسال الصور في حال توفرها
    if photos:
        await update.message.reply_text("📷 **صور السيارة من المزاد:**")
        for photo_url in photos:
            try:
                await update.message.reply_photo(photo_url)
            except Exception:
                continue
    else:
        await update.message.reply_text("⚠️ لم نتمكن من العثور على صور المزاد لهذه السيارة في الأرشيف المجاني.")

if __name__ == '__main__':
    # تشغيل خادم الويب في الخلفية
    threading.Thread(target=run_web_server, daemon=True).start()
    
    # تشغيل بوت تليجرام
    bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("البوت يعمل الآن...")
    bot_app.run_polling()