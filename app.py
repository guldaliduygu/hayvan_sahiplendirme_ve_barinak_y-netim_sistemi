import streamlit as st
import sqlite3
import time
import base64
from datetime import datetime
import re
import io
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai
import pandas as pd

# --- DATABASE DOSYASI İMPORTU ---
# (database.py dosyanızın yanınızda olduğundan emin olun)
import database as db

# --- API AYARLARI ---
API_KEY = "AIzaSyDGF9_YQI-dd5F-qQk5vZQPl3gBESYqf7o"

def get_user_donations(username):
    # Veritabanındaki tüm bağışları çek
    tum_bagislar = db.get_donations()

    kullanici_bagislari = []

    if tum_bagislar:
        for bagis in tum_bagislar:
            # bagis[1] -> Bağışçı Adı sütunu olduğunu varsayıyorum
            # Eğer kullanıcı adınla bağış yaparken girdiğin isim aynıysa eşleşir
            if bagis[1] == username:
                kullanici_bagislari.append({
                    'Miktar': f"{bagis[2]} TL",
                    'Yöntem': bagis[3],
                    'Tarih': bagis[4]
                })

    if kullanici_bagislari:
        return pd.DataFrame(kullanici_bagislari)
    else:
        return pd.DataFrame()


def get_user_applications(username):
    # 1. Veritabanından TÜM başvuruları iste
    tum_basvurular = db.get_applications()
    kullanici_basvurulari = []

    if tum_basvurular:
        for basvuru in tum_basvurular:
            # basvuru[2] -> Tablondaki "Ad Soyad" sütunu
            if basvuru[2] == username:
                kullanici_basvurulari.append({
                    'Hayvan': basvuru[1],  # Hayvan Adı
                    'Telefon': basvuru[3],  # Telefon
                    'Durum': basvuru[6],  # Durum (Bekliyor/Onaylandı)
                    'Tarih': basvuru[7]  # Tarih
                })

    if kullanici_basvurulari:
        return pd.DataFrame(kullanici_basvurulari)
    else:
        return pd.DataFrame()


# ==========================================
# 1. YARDIMCI SINIFLAR (UTILS & SERVICES)
# ==========================================

class Config:
    """Uygulama genel konfigürasyonlarını yönetir."""

    @staticmethod
    def init():
        # SIDEBAR VARSAYILAN OLARAK AÇIK GELSİN
        st.set_page_config(
            page_title="PATİTY",
            page_icon="🐾",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        try:
            genai.configure(api_key=API_KEY)
        except Exception:
            pass

        # --- OTOMATİK KURULUM VE ADMİN OLUŞTURMA ---
        try:
            # 1. Veritabanı tablolarını garantile (Yeni fonksiyon ismiyle)
            db.initialize_database()

            # 2. Admin kullanıcısını oluştur (Zaten varsa hata vermez, False döner)
            # Kullanıcı: admin / Şifre: Admin123! / Rol: Barınak Yöneticisi
            db.add_user("admin", "Admin123!", "Barınak Yöneticisi")
        except Exception as e:
            # Hata olsa bile (örn: db kilitliyse) uygulama çökmesin
            print(f"Başlangıç ayarları uyarısı: {e}")


class Utils:
    """Resim işleme, formatlama ve sertifika gibi yardımcı fonksiyonlar."""

    @staticmethod
    def process_image_upload(uploaded_file):
        if uploaded_file is not None:
            try:
                image = Image.open(uploaded_file)
                image.thumbnail((1200, 800))
                buffered = BytesIO()
                image = image.convert("RGB")
                image.save(buffered, format="JPEG", quality=90)
                b64 = base64.b64encode(buffered.getvalue()).decode()
                return f"data:image/jpeg;base64,{b64}"
            except:
                return None
        return None

    @staticmethod
    def create_certificate(donor_name):
        try:
            cert_data = db.get_setting('certificate_img')
            if cert_data:
                header, encoded = cert_data.split(',', 1)
                decoded_data = base64.b64decode(encoded)
                img = Image.open(io.BytesIO(decoded_data))
            else:
                raise FileNotFoundError
        except:
            img = Image.new('RGB', (800, 600), color=(255, 255, 255))

        draw = ImageDraw.Draw(img)
        W, H = img.size
        try:
            font_size = int(H / 20)
            font = ImageFont.truetype("arialbd.ttf", font_size)
        except:
            font = ImageFont.load_default()

        text = donor_name.replace("i", "İ").replace("ı", "I").upper()
        text_color = "white"

        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]

        x_pos = (W * 0.82) - (text_width / 2)
        y_pos = H * 0.26

        if x_pos < 0 or y_pos < 0:
            x_pos = (W - text_width) / 2
            y_pos = H / 2

        draw.text((x_pos, y_pos), text, fill=text_color, font=font)
        buf = io.BytesIO()
        img = img.convert("RGB")
        img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()

    @staticmethod
    def validate_password(password):
        if len(password) < 8: return False, "Şifre en az 8 karakter olmalı."
        if not re.search(r"[a-z]", password): return False, "Şifre en az bir küçük harf içermeli."
        if not re.search(r"[A-Z]", password): return False, "Şifre en az bir büyük harf içermeli."
        if not re.search(r"[0-9]", password): return False, "Şifre en az bir rakam içermeli."
        return True, ""

    @staticmethod
    def format_card_number():
        input_val = st.session_state.get('card_input', '')
        clean_val = re.sub(r'\D', '', input_val)[:16]
        groups = [clean_val[i:i + 4] for i in range(0, len(clean_val), 4)]
        st.session_state['card_input'] = "-".join(groups)

    @staticmethod
    def format_skt():
        input_val = st.session_state.get('skt_input', '')
        clean_val = re.sub(r'\D', '', input_val)[:4]
        if len(clean_val) > 2:
            st.session_state['skt_input'] = clean_val[:2] + '/' + clean_val[2:]
        else:
            st.session_state['skt_input'] = clean_val


class AIService:
    """Gemini AI entegrasyonu ve SQL üretimi."""

    @staticmethod
    def _get_best_model():
        """En uygun Gemini modelini bulur ve döndürür."""
        model = None
        try:
            # Kullanılabilir modelleri listele
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    # Genellikle 'flash' modelleri hızlı ve ücretsizdir, onu önceliklendiriyoruz
                    if 'flash' in m.name:
                        return genai.GenerativeModel(m.name)

            # Eğer döngüden bir şey çıkmazsa varsayılanı döndür
            return genai.GenerativeModel('gemini-1.5-flash')
        except Exception as e:
            # Hata durumunda varsayılanı zorla
            print(f"Model seçimi hatası: {e}")
            return genai.GenerativeModel('gemini-1.5-flash')

    @staticmethod
    def ask_ai_local(user_question):
        # 1. Veritabanı Şeması
        DB_SCHEMA = """
            Tablo: animals
            Sütunlar: id, type, name, age, gender, breed, health_status, disease_history, sterilization_status, image_url, added_date, description
        """

        # 2. Tür Zorlama
        user_lower = user_question.lower()
        forced_type = None
        if 'köpek' in user_lower and 'alerji' not in user_lower:
            forced_type = 'köpek'
        elif 'kedi' in user_lower and 'alerji' not in user_lower:
            forced_type = 'kedi'

        # 3. Model Seçimi (Artık yukarıdaki fonksiyonu kullanabiliriz veya burası kalabilir)
        # Buradaki mantığı da sadeleştirebiliriz ama mevcut kodunuz bozulmasın diye dokunmuyorum.
        model = None
        try:
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    model = genai.GenerativeModel(m.name)
                    break
            if model is None:
                model = genai.GenerativeModel('gemini-1.5-flash')
        except Exception as e:
            return f"Model hatası: {str(e)}"

        # 4. Prompt
        type_rule = f"AND LOWER(type) LIKE '%{forced_type}%'" if forced_type else ""

        system_prompt = f"""
        Sen 'Piti' adında, bu hayvan barınağının tatlı, yardımsever ve neşeli yapay zeka asistanısın.
        Veritabanı şeması: {DB_SCHEMA}

        GÖREV: Kullanıcının girdisine ("{user_question}") bak ve şu İKİ yoldan birini seç:

        YOL 1: SOHBET (SQL YOK)
        Eğer kullanıcı selam verdiyse veya konu dışıysa samimi cevap ver. SQL yazma.

        YOL 2: ARAMA (SQL GEREKLİ)
        Eğer kullanıcı hayvan arıyorsa:
        - SADECE SQL kodu ver.
        - Tablo: 'animals'.
        - Başlangıç: 'SELECT * FROM animals WHERE 1=1'
        - {type_rule}

        - AKILLI SQL KURALLARI:
          * YAŞ:
             - 'Yaşlı' -> age >= 10
             - 'Yavru'/'Bebek' -> age <= 1

          * KİŞİLİK (Negatif Filtreleme):
             - 'Sakin' -> (description LIKE '%sakin%' OR description LIKE '%uslu%') AND description NOT LIKE '%sakinleş%'

          * ALERJİ:
             - "kediye alerjim var" -> AND type != 'Kedi'
             - "köpeğe alerjim var" -> AND type != 'Köpek'

          * SAĞLIK DURUMU:
             - "hasta istemiyorum", "sağlıklı olsun" -> AND (health_status = 'Çok İyi' OR health_status = 'İyi')
             - "bakıma muhtaç", "hasta" -> AND (health_status LIKE '%Tedavi%' OR health_status LIKE '%Bakım%')

          * KISIRLAŞTIRMA DURUMU:
             - "kısır", "kısırlaştırılmış" -> AND sterilization_status = 'Kısırlaştırıldı'
             - "kısır olmayan", "kısırlaştırılmamış" -> AND (sterilization_status = 'Kısırlaştırılmadı' OR sterilization_status = 'Bilinmiyor')

          * RENK VE ÇAKIŞMA KONTROLÜ:
             - "Sarı" kedi -> LIKE '%sarı%' OR LIKE '%sarman%' OR LIKE '%tekir%'
             - ZIT RENK:
               1. Sadece "Siyah" arıyorsa -> AND (breed NOT LIKE '%Beyaz%' AND breed NOT LIKE '%White%')
               2. Sadece "Beyaz" arıyorsa -> AND (breed NOT LIKE '%Siyah%' AND breed NOT LIKE '%Kara%')
        """

        try:
            # 5. AI Cevabı
            response = model.generate_content(system_prompt)
            cleaned_response = response.text.strip().replace("```sql", "").replace("```", "").replace("sql", "").strip()

            if cleaned_response.lower().startswith("select"):
                conn = sqlite3.connect("patity.db")
                cursor = conn.cursor()
                try:
                    cursor.execute(cleaned_response)
                    found_animals = cursor.fetchall()
                except:
                    found_animals = []
                conn.close()

                if not found_animals:
                    return "😿 Aradığın kriterlere uygun bir dostumuz maalesef bulunamadı."

                return found_animals

            else:
                return cleaned_response

        except Exception as e:
            return f"Hata: {str(e)}"


class StyleManager:
    """CSS ve Tema yönetimi."""

    @staticmethod
    def apply_styles(dark_mode):
        if dark_mode:
            colors = {
                "bg": "#0E1117", "text": "#FAFAFA", "brand": "#FF9F43",
                "card_bg": "#1E1E1E", "input_bg": "#262730", "border": "#333333",
                "shadow": "0 10px 30px rgba(0,0,0,0.5)"
            }
        else:
            colors = {
                "bg": "#F8F9FD", "text": "#2D3436", "brand": "#FF8F00",
                "card_bg": "#FFFFFF", "input_bg": "#FFFFFF", "border": "rgba(0,0,0,0.05)",
                "shadow": "0 10px 30px rgba(0,0,0,0.05)"
            }

        st.markdown(f"""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;500;700&display=swap');
            .stApp {{ background-color: {colors['bg']}; color: {colors['text']}; font-family: 'Poppins', sans-serif; }}
            #MainMenu, footer, header {{visibility: hidden;}}
            h1, h2, h3, h4, p, span, div, label {{ color: {colors['text']}; }}

            /* 1. GENEL BUTONLAR (Eski haline/Büyük haline döndü) */
            div.stButton > button:not([kind="primary"]) {{ 
                background: linear-gradient(135deg, {colors['brand']} 0%, #FF6F00 100%); 
                color: white !important; 
                border: none; 
                border-radius: 50px; 
                padding: 12px 30px; /* Normal büyük boy */
                font-weight: 600; 
                width: 100%; 
                box-shadow: 0 4px 15px rgba(255, 143, 0, 0.3); 
                transition: all 0.3s ease; 
            }}
            div.stButton > button:not([kind="primary"]):hover {{ transform: translateY(-2px); box-shadow: 0 8px 25px rgba(255, 143, 0, 0.5); }}

            /* 2. SADECE CHATBOT İÇİNDEKİ BUTONLAR (ÖZEL KURAL) */
            /* Popover içindeki butonları hedefliyoruz */
            [data-testid="stPopoverBody"] div.stButton > button {{
                padding: 4px 15px !important;  /* Çok ince yapıldı */
                font-size: 13px !important;    /* Yazı küçüldü */
                min-height: 0px !important;    /* Yükseklik zorlaması kalktı */
                height: auto !important;       /* İçeriğe göre daralsın */
                line-height: 1.2 !important;
                margin-top: -10px !important;  /* Kutuya daha yakın olsun */
            }}

            div.stButton > button[kind="primary"] {{ background: transparent !important; border: none !important; color: {colors['text']} !important; font-size: 40px !important; padding: 0 !important; }}
            .dashboard-card {{ background-color: {colors['card_bg']}; border-radius: 16px; padding: 20px; border-left: 5px solid {colors['brand']}; box-shadow: {colors['shadow']}; transition: transform 0.2s; }}
            .dashboard-card:hover {{ transform: translateY(-3px); }}
            .dash-value {{ font-size: 36px; font-weight: 800; color: {colors['brand']}; margin: 10px 0; }}
            .aesthetic-card {{ background-color: {colors['card_bg']}; border-radius: 24px; padding: 15px; box-shadow: {colors['shadow']}; border: 1px solid {colors['border']}; transition: all 0.3s; height: 100%; }}
            .aesthetic-card:hover {{ transform: translateY(-5px); border-color: {colors['brand']}; }}
            .card-img-wrapper {{ width: 100%; height: 250px; border-radius: 20px; overflow: hidden; margin-bottom: 15px; }}
            .card-img {{ width: 100%; height: 100%; object-fit: cover; transition: transform 0.5s; }}
            .aesthetic-card:hover .card-img {{ transform: scale(1.1); }}
            div[data-baseweb="input"] {{ background-color: {colors['input_bg']} !important; border-radius: 16px !important; }}
            .active-slide {{ width: 100%; height: 500px; border-radius: 24px; overflow: hidden; box-shadow: {colors['shadow']}; position: relative; }}
            .slide-img {{ width: 100%; height: 100%; object-fit: cover; }}
            .slide-overlay {{ position: absolute; bottom: 0; left: 0; right: 0; background: linear-gradient(0deg, rgba(0,0,0,0.9) 0%, rgba(0,0,0,0) 100%); padding: 40px 30px; color: white; }}
            .slide-title {{ font-size: 32px; font-weight: 700; color: white !important; }}
            .footer {{ margin-top: 100px; padding: 50px 0; border-top: 1px solid {colors['border']}; text-align: center; opacity: 0.6; }}
            .brand-logo {{ font-size: 32px; font-weight: 900; color: {colors['brand']} !important; letter-spacing: -1px; }}
            [data-testid="stPopover"] {{position: fixed !important; bottom: 30px !important; right: 30px !important; z-index: 99999 !important;}}
            [data-testid="stPopover"] > button {{background: linear-gradient(135deg, #FF9F43 0%, #FF6F00 100%) !important; color: white !important; border-radius: 50% !important; width: 70px !important; height: 70px !important; font-size: 35px !important; box-shadow: 0 4px 15px rgba(255, 143, 0, 0.5) !important;}}
        </style>
        """, unsafe_allow_html=True)
        return colors

# ==========================================
# 2. TEMEL SAYFA SINIFLARI (Base & Components)
# ==========================================

class BasePage:
    """Tüm sayfalar için ortak metodları içeren sınıf."""

    def __init__(self, colors):
        self.colors = colors

    def render_header(self):
        c1, c2, c3, c4 = st.columns([1.5, 3, 2, 1.5], gap="medium")
        with c1:
            try:
                with open("logo.png", "rb") as f:
                    data = base64.b64encode(f.read()).decode()
                st.markdown(f'<img src="data:image/png;base64,{data}" style="width: 200px; margin-top: -75px;">',
                            unsafe_allow_html=True)
            except:
                st.markdown('<div class="brand-logo">🐾 PATİTY</div>', unsafe_allow_html=True)
        with c2:
            col1, col2, col3 = st.columns(3)
            if col1.button("🏠 Anasayfa"): self.navigate("Anasayfa")
            if col2.button("🐾 Sahiplen"):
                st.session_state.filter_choice = "Tümü"
                self.navigate("Sahiplen")
            if col3.button("💖 Bağış"): self.navigate("Bağış")

        # --- AKILLI ARAMA KUTUSU ---
        with c3:
            # Kullanıcı enter'a bastığında bu fonksiyon çalışacak
            def search_callback():
                term = st.session_state.top_search_bar.lower().strip()
                st.session_state.top_search_bar = ""  # Kutuyu temizle

                if not term: return  # Boşsa işlem yapma

                # 1. SAYFA YÖNLENDİRMELERİ (NAVİGASYON)
                if "bağış" in term or "destek" in term or "para" in term:
                    st.session_state.page = "Bağış"

                elif "profil" in term or "hesap" in term or "giriş" in term:
                    if st.session_state.is_logged_in:
                        st.session_state.page = "Profil"
                    else:
                        st.session_state.page = "Login"

                elif "anasayfa" in term or "ev" in term:
                    st.session_state.page = "Anasayfa"

                elif "veteriner" in term:
                    if st.session_state.user_role == "Veteriner":
                        # Zaten veterinerse sayfayı yenilemesin, olduğu yerde kalsın
                        pass
                    else:
                        st.info("Veteriner girişi yapmalısınız.")
                        st.session_state.page = "Login"

                # 2. HAYVAN ARAMALARI
                else:
                    # Genel bir arama terimi ise (örn: "Tekir", "Pamuk", "Kedi")
                    st.session_state['global_search_term'] = term
                    st.session_state.page = "Sahiplen"

                    # Eğer "kedi" veya "köpek" yazdıysa filtreyi de hazırla
                    if "kedi" in term:
                        st.session_state.filter_choice = "Kedi"
                    elif "köpek" in term:
                        st.session_state.filter_choice = "Köpek"
                    else:
                        st.session_state.filter_choice = "Tümü"

            # Arama Kutusu (on_change ile enter'a basılınca yukarıdaki fonksiyonu çağırır)
            st.text_input("ara", placeholder="🔍 Site içi ara (Örn: Bağış, Kedi, Pamuk)...",
                          key="top_search_bar",
                          on_change=search_callback,
                          label_visibility="collapsed")

        with c4:
            sc1, sc2 = st.columns([1, 2])
            with sc1:
                if st.button("🌙" if st.session_state.dark_mode else "☀"):
                    st.session_state.dark_mode = not st.session_state.dark_mode
                    st.rerun()
            with sc2:
                if st.session_state.is_logged_in:
                    if st.button("👤 Profil"):
                        self.navigate("Profil")
                else:
                    if st.button("Giriş"): self.navigate("Login")
        st.markdown("---")

    def render_footer(self):
        st.markdown("""<div class="footer"><p><strong>PATİTY © 2025</strong><br>Minik dostlarımız için.</p></div>""",
                    unsafe_allow_html=True)

    def navigate(self, page_name):
        st.session_state.page = page_name
        st.rerun()


# ==========================================
# 3. SAYFA SINIFLARI (Sayfa Mantığı)
# ==========================================

class HomePage(BasePage):
    def render(self):
        self.render_header()
        st.markdown(
            "<h2 style='text-align:center; font-weight:800; font-size:2rem; margin-bottom:20px;'>📢 Duyurular & Etkinlikler</h2>",
            unsafe_allow_html=True)
        self._render_slider()

        st.markdown(
            "<br><br><h2 style='text-align:center; font-weight:800; font-size:2.5rem;'>Dostlarımızı Tanıyın</h2><br>",
            unsafe_allow_html=True)
        col1, col2 = st.columns(2, gap="large")

        cat_img = db.get_setting(
            'home_cat_img') or "[https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?w=600&q=80](https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?w=600&q=80)"
        dog_img = db.get_setting(
            'home_dog_img') or "[https://images.unsplash.com/photo-1543466835-00a7907e9de1?w=600&q=80](https://images.unsplash.com/photo-1543466835-00a7907e9de1?w=600&q=80)"

        with col1:
            st.markdown(
                f"""<div class="aesthetic-card"><div class="card-img-wrapper"><img src="{cat_img}" class="card-img"></div><div><div style="font-weight:700; font-size:1.5rem; margin-bottom:5px;">Kedilerimiz</div><div style="font-size:0.9rem; opacity:0.7; margin-bottom:20px;">Sıcak bir kucak bekleyen minik dostlar.</div></div></div>""",
                unsafe_allow_html=True)
            if st.button("İncele 🐾", key="btn_cat"):
                st.session_state.filter_choice = "Kedi"
                self.navigate("Sahiplen")
        with col2:
            st.markdown(
                f"""<div class="aesthetic-card"><div class="card-img-wrapper"><img src="{dog_img}" class="card-img"></div><div><div style="font-weight:700; font-size:1.5rem; margin-bottom:5px;">Köpeklerimiz</div><div style="font-size:0.9rem; opacity:0.7; margin-bottom:20px;">Sadık yol arkadaşınızla tanışın.</div></div></div>""",
                unsafe_allow_html=True)
            if st.button("İncele 🐕", key="btn_dog"):
                st.session_state.filter_choice = "Köpek"
                self.navigate("Sahiplen")
        self.render_footer()

    def _render_slider(self):
        anns = db.get_announcements()
        if not anns:
            anns = [(0, "Hoşgeldiniz!", "Duyurularınızı buradan takip edin.",
                     "[https://images.unsplash.com/photo-1450778869180-41d0601e046e?w=1200&q=80](https://images.unsplash.com/photo-1450778869180-41d0601e046e?w=1200&q=80)",
                     "")]

        idx = st.session_state.slider_index
        if idx >= len(anns):
            idx = 0
        elif idx < 0:
            idx = len(anns) - 1
        st.session_state.slider_index = idx

        curr = anns[idx]
        col_l, col_c, col_r = st.columns([1, 10, 1], vertical_alignment="center")
        with col_l:
            if st.button("❮", key="prev_slide", type="primary"):
                st.session_state.slider_index -= 1;
                st.rerun()
        with col_c:
            st.markdown(
                f"""<div class="active-slide"><img src="{curr[3]}" class="slide-img"><div class="slide-overlay"><p class="slide-title">{curr[1]}</p><p class="slide-desc">{curr[2]}</p></div></div>""",
                unsafe_allow_html=True)
            dots = "".join([
                               f'<span style="display:inline-block; width:10px; height:10px; background:{self.colors["brand"] if i == idx else "#ccc"}; border-radius:50%; margin:0 5px;"></span>'
                               for i in range(len(anns))])
            st.markdown(f'<div style="text-align:center; margin-top:15px;">{dots}</div>', unsafe_allow_html=True)
        with col_r:
            if st.button("❯", key="next_slide", type="primary"):
                st.session_state.slider_index += 1;
                st.rerun()


class AdoptionPage(BasePage):
    def render(self):
        self.render_header()

        # Detay sayfası mı Liste sayfası mı?
        if 'selected_animal' in st.session_state:
            self._render_detail_view()
        else:
            self._render_list_view()

        self.render_footer()

    def _render_list_view(self):
        # --- 1. ÜST BAŞLIK ALANI ---
        c_back, c_title = st.columns([1, 6], vertical_alignment="center")
        with c_back:
            if st.button("← Geri", key="back_from_adopt_main", use_container_width=True):
                self.navigate("Anasayfa")
        with c_title:
            st.markdown(f"<h2 style='margin:0;'>🏡 Yuva Arayan Canlar</h2>", unsafe_allow_html=True)

        st.markdown("---")

        # --- 2. SOL MENÜ (SIDEBAR) FİLTRELERİ ---
        with st.sidebar:
            st.header("🌪️ Detaylı Filtrele")
            st.markdown("Aradığın dostu bulmak için kriterleri seç.")
            st.markdown("---")

            # --- DÜZELTME BURADA: key="filter_choice" EKLENDİ ---
            # Artık Anasayfada 'Kedi' butonuna basınca burası otomatik 'Kedi' olarak gelecek.
            tur_opts = ["Tümü", "Kedi", "Köpek"]
            sel_tur = st.selectbox("🐾 Tür", tur_opts, key="filter_choice")

            # Cinsiyet
            sel_gender = st.radio("⚧ Cinsiyet", ["Farketmez", "Dişi", "Erkek"], horizontal=True)

            # Yaş Slider
            sel_age = st.slider("🎂 Maksimum Yaş", 0, 20, 20)

            st.markdown("---")

            # Kısırlık
            sel_steril = st.selectbox("✂ Kısırlık Durumu", ["Farketmez", "Kısırlaştırılmış", "Kısırlaştırılmamış"])

            # Sağlık
            health_opts = ["Farketmez", "Çok İyi", "İyi", "Bakıma Muhtaç", "Tedavi Görüyor"]
            sel_health = st.multiselect("🩺 Sağlık Durumu", health_opts, default=[], placeholder="Seçiniz...")

            st.markdown("---")

            # Sıralama
            sel_sort = st.selectbox("🔃 Sıralama", ["En Yeniler", "En Eskiler", "Gençten Yaşlıya", "Yaşlıdan Gence"])

            if st.button("Filtreleri Temizle", use_container_width=True):
                # Filtreleri sıfırlamak için session state'i resetliyoruz
                st.session_state.filter_choice = "Tümü"
                st.rerun()

        # --- 3. ANA EKRAN: ARAMA VE LİSTELEME ---

        # Arama Çubuğu
        default_search = st.session_state.pop('global_search_term', '')
        search_term = st.text_input("🔍 Hızlı Arama", value=default_search,
                                    placeholder="İsim, ırk veya özellik yazıp Enter'a basın...",
                                    label_visibility="collapsed")

        st.markdown("<br>", unsafe_allow_html=True)

        # --- 4. FİLTRELEME MANTIĞI ---
        try:
            all_animals = db.get_animals(None)
        except:
            all_animals = []

        filtered_animals = []

        if all_animals:
            for animal in all_animals:
                # [0:id, 1:type, 2:name, 3:age, 4:gender, 5:breed, 6:health, 7:disease, 8:sterilization, 9:img, 10:date, 11:desc]

                # Sahiplendirilenleri Gizle
                if animal[6] == 'Sahiplendirildi': continue

                # Tür Filtresi (Artık sel_tur anasayfadan gelen veriyi kullanıyor)
                if sel_tur != "Tümü" and animal[1] != sel_tur: continue

                # Cinsiyet
                if sel_gender != "Farketmez" and animal[4] != sel_gender: continue

                # Yaş
                try:
                    if int(animal[3]) > sel_age: continue
                except:
                    pass

                # Kısırlık
                if sel_steril == "Kısırlaştırılmış" and "Kısırlaştırıldı" not in (animal[8] or ""): continue
                if sel_steril == "Kısırlaştırılmamış" and "Kısırlaştırılmadı" not in (animal[8] or ""): continue

                # Sağlık
                if sel_health:
                    if animal[6] not in sel_health: continue

                # Arama Kelimesi
                if search_term:
                    term = search_term.lower()
                    full_text = f"{animal[2]} {animal[5]} {animal[11]}".lower()
                    if term not in full_text: continue

                filtered_animals.append(animal)

        # --- 5. SIRALAMA ---
        if sel_sort == "En Yeniler":
            filtered_animals.sort(key=lambda x: x[0], reverse=True)
        elif sel_sort == "En Eskiler":
            filtered_animals.sort(key=lambda x: x[0])
        elif sel_sort == "Gençten Yaşlıya":
            filtered_animals.sort(key=lambda x: int(x[3]) if str(x[3]).isdigit() else 99)
        elif sel_sort == "Yaşlıdan Gence":
            filtered_animals.sort(key=lambda x: int(x[3]) if str(x[3]).isdigit() else 0, reverse=True)

        # --- 6. SONUÇLARI GÖSTER ---
        if not filtered_animals:
            st.warning("😿 Aradığınız kriterlere uygun bir dostumuz bulunamadı.")
            st.info("👈 Sol taraftaki filtreleri değiştirmeyi deneyebilirsin.")
        else:
            st.caption(f"Şu an **{len(filtered_animals)}** dostumuz listeleniyor.")

            cols = st.columns(3)
            for idx, animal in enumerate(filtered_animals):
                with cols[idx % 3]:
                    img_url = animal[9] or "https://via.placeholder.com/300"

                    st.markdown(f"""
                    <div class="aesthetic-card" style="margin-bottom:15px; cursor:pointer;">
                        <div class="card-img-wrapper" style="height:220px; position:relative;">
                            <img src="{img_url}" class="card-img">
                            <div style="position:absolute; top:10px; right:10px; background:rgba(0,0,0,0.6); color:white; padding:4px 8px; border-radius:10px; font-size:12px;">
                                {animal[1]}
                            </div>
                        </div>
                        <div style="padding:10px;">
                            <div style="font-weight:700; font-size:1.3rem; color:{self.colors['brand']};">{animal[2]}</div>
                            <div style="font-size:0.9rem; opacity:0.8; margin-bottom:5px;">
                                {animal[5]} • {animal[3]} Yaş
                            </div>
                            <div style="font-size:0.8rem; display:flex; gap:10px;">
                                <span style="background:rgba(255, 159, 67, 0.1); padding:2px 6px; border-radius:4px;">{animal[4]}</span>
                                <span style="background:rgba(46, 204, 113, 0.1); padding:2px 6px; border-radius:4px; color:#27ae60;">{animal[6]}</span>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    if st.button(f"İncele 🐾", key=f"view_{animal[0]}", use_container_width=True):
                        st.session_state['selected_animal'] = animal
                        st.rerun()

    def _render_detail_view(self):
        # DETAY SAYFASI (Minik Geri Butonlu Hali)
        a = st.session_state['selected_animal']

        c_back, c_space = st.columns([1, 6])
        with c_back:
            if st.button("⬅ Listeye Dön", key="back_to_list"):
                del st.session_state['selected_animal']
                st.rerun()

        st.markdown("---")

        disease = a[7] or "Belirtilmemiş"
        ster = a[8] or "Bilinmiyor"
        desc = a[11] or "Hikayesi henüz eklenmemiş."
        img_url = a[9] or "https://via.placeholder.com/600"

        c_img, c_info = st.columns([1.5, 2], gap="large")
        with c_img:
            st.image(img_url, use_column_width=True, caption=f"{a[2]}")
        with c_info:
            st.markdown(
                f"""<div style="background:{self.colors['card_bg']}; padding:25px; border-radius:15px; border:1px solid {self.colors['border']}; margin-bottom:20px;"><h1 style="color:{self.colors['brand']}; margin:0; font-size: 2.5rem;">{a[2]}</h1><p style="opacity:0.8; font-size: 1.1rem;">{a[1]} • {a[5]}</p><hr style="opacity:0.2;"><div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;"><div><strong>🎂 Yaş:</strong> {a[3]}</div><div><strong>⚧ Cinsiyet:</strong> {a[4]}</div><div><strong>🩺 Sağlık:</strong> {a[6]}</div><div><strong>✂ Kısırlaştırma:</strong> {ster}</div></div></div>""",
                unsafe_allow_html=True)
            st.subheader("📜 Hikayesi")
            st.markdown(
                f"""<div style="font-size: 15px; line-height: 1.6; color: {self.colors['text']}; opacity: 0.9;">{desc}</div>""",
                unsafe_allow_html=True)

        st.markdown("<br><hr><br>", unsafe_allow_html=True)
        st.subheader("📝 Sahiplenme Başvuru Formu")
        st.info("Minik dostumuzun ömürlük yuvası olmak için lütfen formu eksiksiz doldurunuz.")

        if st.session_state.is_logged_in:
            with st.form("basvuru_form"):
                st.markdown("**1. Kişisel Bilgiler**")
                c1, c2 = st.columns(2)
                name = c1.text_input("Adınız Soyadınız", value=st.session_state.get('username', ''))
                phone = c2.text_input("Telefon Numaranız", placeholder="05XX...", max_chars=11)
                c3, c4 = st.columns(2)
                age = c3.number_input("Yaşınız", min_value=18, max_value=90, step=1)
                occupation = c4.text_input("Mesleğiniz")
                st.markdown("---")
                st.markdown("**2. Yaşam Alanı**")
                col_ev1, col_ev2 = st.columns(2)
                home_type = col_ev1.selectbox("Oturduğunuz Ev Tipi",
                                              ["Apartman Dairesi", "Müstakil", "Bahçeli Ev", "Site İçi"])
                has_garden = col_ev2.radio("Bahçe veya Balkon var mı?", ["Var", "Yok"], horizontal=True)
                balcony_net = st.radio("Pencerelerde/Balkonda kedi/köpek filesi var mı?",
                                       ["Var", "Yok", "Taktıracağım"], horizontal=True)
                st.markdown("---")
                st.markdown("**3. Bakım ve Tecrübe**")
                other_pets = st.text_input("Evde yaşayan başka evcil hayvan var mı?")
                working_hours = st.selectbox("Evde günde kaç saat yalnız kalacak?",
                                             ["Hiç", "1-3 Saat", "4-8 Saat", "9+ Saat"])
                msg = st.text_area("Neden sahiplenmek istiyorsunuz?", height=100)
                st.markdown("<br>", unsafe_allow_html=True)
                submitted = st.form_submit_button("Başvuruyu Gönder", use_container_width=True)
                if submitted:
                    clean_phone = phone.replace(" ", "")
                    if not name or not phone or not occupation:
                        st.error("Lütfen ad, telefon ve meslek alanlarını doldurunuz.")
                    elif not re.match(r"^05\d{9}$", clean_phone):
                        st.error("Lütfen geçerli bir telefon numarası giriniz.")
                    else:
                        db.add_application(a[0], a[2], name, clean_phone, str(age), occupation, home_type, has_garden,
                                           balcony_net, other_pets, working_hours, msg)
                        st.success("Başvurunuz başarıyla alındı!")
                        time.sleep(3)
                        del st.session_state['selected_animal']
                        st.rerun()
        else:
            st.warning("⚠️ Başvuru formunu görebilmek için lütfen giriş yapınız.")
            if st.button("Giriş Yap", key="login_btn_detail"): self.navigate("Login")


class DonationPage(BasePage):
    def render(self):
        self.render_header()
        step = st.session_state.get('donation_step')

        if step == 'certificate':
            self._render_certificate()
        elif step == 'payment':
            self._render_payment()
        else:
            self._render_form()
        self.render_footer()

    def _render_form(self):
        st.markdown(
            f"<h2 style='text-align:center; color:{self.colors['brand']};'>𐙚 Bağış Yaparak Canlara Destek Ol</h2><br>",
            unsafe_allow_html=True)
        col_form, col_info = st.columns([1.2, 1], gap="large")
        with col_form:
            bc1, bc2 = st.columns(2)
            if bc1.button("Tek Seferlik",
                          use_container_width=True): st.session_state.donation_frequency = "Tek Seferlik"
            if bc2.button("Aylık Düzenli", use_container_width=True): st.session_state.donation_frequency = "Aylık"

            st.subheader(f"{st.session_state.donation_frequency} Bağış Bilgileri")
            amount = st.number_input("Tutar (TL)", min_value=50, step=50,
                                     value=st.session_state.get('donation_amount', 100))
            if amount / 50 > 0:
                msg = "her ay" if st.session_state.donation_frequency == "Aylık" else ""
                st.markdown(
                    f"""<div class="impact-box">ฅ ฅ Bu tutarla {msg} yaklaşık <strong>{int(amount / 50)} minik dostumuzun</strong> günlük mama ihtiyacını karşılıyorsunuz.</div>""",
                    unsafe_allow_html=True)

            st.markdown("---")
            c1, c2 = st.columns(2)
            name = c1.text_input("Ad")
            surname = c2.text_input("Soyad")
            email = st.text_input("E-posta")
            is_gift = st.checkbox("🎁 Hediye olarak bağış yap")
            gift_name = st.text_input("Hediye Edilecek Kişi") if is_gift else ""

            if st.button("Devam Et", use_container_width=True):
                if name and surname and email and re.match(r"[^@]+@[^@]+\.[^@]+", email):
                    st.session_state.update({'donation_step': 'payment', 'donation_amount': amount,
                                             'donor_name': gift_name if is_gift and gift_name else f"{name} {surname}"})
                    st.rerun()
                else:
                    st.error("Bilgileri eksiksiz ve doğru giriniz.")

        with col_info:
            img_src = db.get_setting(
                'donation_img') or "[https://images.unsplash.com/photo-1535930749574-1399327ce78f?w=800&q=80](https://images.unsplash.com/photo-1535930749574-1399327ce78f?w=800&q=80)"
            st.markdown(
                f"""<div class="aesthetic-card"><div class="card-img-wrapper" style="height:300px;"><img src="{img_src}" class="card-img"></div><div style="text-align:left;"><h3 style="color:{self.colors['brand']}">Neden Bağış?</h3><p>Giderlerimiz tamamen sizin desteklerinizle karşılanmaktadır.</p></div></div>""",
                unsafe_allow_html=True)

    def _render_payment(self):
        c1, c2, c3 = st.columns([1, 1.5, 1])
        with c2:
            if st.button("← Geri Dön"): st.session_state['donation_step'] = None; st.rerun()
            st.markdown(
                f"""<div class="aesthetic-card"><h3 style="color:{self.colors['brand']}; text-align:center;"> Güvenli Ödeme</h3><p style="text-align:center;">Tutar: <strong>{st.session_state['donation_amount']} TL</strong></p></div>""",
                unsafe_allow_html=True)
            st.text_input("Kart Numarası", placeholder="XXXX-XXXX-XXXX-XXXX", max_chars=19, key="card_input",
                          on_change=Utils.format_card_number)
            r1, r2 = st.columns(2)
            r1.text_input("SKT", placeholder="12/25", max_chars=5, key="skt_input", on_change=Utils.format_skt)
            r2.text_input("CVC", type="password", placeholder="***", max_chars=3)

            if st.button("Ödemeyi Tamamla", use_container_width=True):
                db.add_donation(st.session_state.get('donor_name'), st.session_state.get('donation_amount'), "Web")
                st.session_state['donation_step'] = 'certificate'
                st.rerun()

    def _render_certificate(self):
        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            st.markdown(
                f"""<div class="aesthetic-card"><h2 style="color:{self.colors['brand']}; text-align:center;">Teşekkürler!</h2></div>""",
                unsafe_allow_html=True)
            cert_data = Utils.create_certificate(st.session_state.get('donor_name', 'Bağışçı'))
            st.image(cert_data, caption="Sertifikanız", use_column_width=True)
            st.download_button("İndir 📥", cert_data, "sertifika.png", "image/png", use_container_width=True)
            if st.button("Anasayfa"): st.session_state['donation_step'] = None; self.navigate("Anasayfa")


class LoginPage(BasePage):
    def render(self):
        self.render_header()
        st.markdown("<br><br>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 1, 1])
        with c2:
            st.markdown(f"<h1 style='text-align:center; color:{self.colors['brand']};'>PATİTY'ye Hoşgeldiniz</h1>",
                        unsafe_allow_html=True)
            tab1, tab2 = st.tabs(["Giriş Yap", "Kullanıcı Kaydı"])

            with tab1:
                role = st.selectbox("Giriş Türü", ["Kullanıcı", "Veteriner", "Barınak Yöneticisi"])
                user = st.text_input("Kullanıcı Adı", key="login_user")
                pw = st.text_input("Şifre", type="password", key="login_pass")
                if st.button("Giriş Yap", use_container_width=True):
                    if user and pw and db.check_login(user, pw, role):
                        st.session_state.is_logged_in = True
                        st.session_state['username'] = user
                        st.session_state.user_role = role
                        st.success(f"Hoşgeldin {role}!");
                        time.sleep(1);
                        self.navigate("Anasayfa")
                    else:
                        st.error("Hatalı giriş!")

            with tab2:
                st.info("Sadece Kullanıcı kaydı yapılabilir.")
                nu = st.text_input("Kullanıcı Adı", key="reg_user")
                np = st.text_input("Şifre", type="password", key="reg_pass")
                np2 = st.text_input("Şifre Tekrar", type="password", key="reg_pass2")
                if st.button("Kayıt Ol", use_container_width=True):
                    if np != np2:
                        st.error("Şifreler uyuşmuyor")
                    else:
                        valid, msg = Utils.validate_password(np)
                        if not valid:
                            st.error(msg)
                        elif db.add_user(nu, np, "Kullanıcı")[0]:
                            st.success("Başarılı!");
                        else:
                            st.error("Hata oluştu")
        self.render_footer()

class AdminPage(BasePage):
    def render(self):
        # --- TASARIM (CSS) ---
        st.markdown(f"""
        <style>
            section[data-testid="stSidebar"] {{
                background-color: {self.colors['card_bg']};
                border-right: 1px solid {self.colors['border']};
            }}
            div[role="radiogroup"] label {{
                padding: 12px 10px !important; border-radius: 8px; margin-bottom: 4px; border: 1px solid transparent; transition: all 0.2s;
            }}
            div[role="radiogroup"] label:hover {{
                background-color: rgba(255, 143, 0, 0.08); color: {self.colors['brand']} !important;
            }}
            .metric-box {{
                text-align: center; padding: 15px; background: {self.colors['card_bg']};
                border-radius: 12px; border: 1px solid {self.colors['border']};
                box-shadow: 0 2px 5px rgba(0,0,0,0.02);
            }}
            /* BİLDİRİM KARTLARI */
            .notif-card {{
                padding: 15px; border-radius: 10px; margin-bottom: 10px; display: flex; align-items: center; gap: 15px;
                border-left: 4px solid #ccc; background-color: {self.colors['card_bg']}; transition: transform 0.2s;
            }}
            .notif-card:hover {{ transform: translateX(5px); }}
            .notif-new {{ border-left: 4px solid {self.colors['brand']}; background: linear-gradient(90deg, {self.colors['card_bg']} 0%, rgba(255, 159, 67, 0.05) 100%); }}
            .notif-icon {{ font-size: 20px; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; border-radius: 50%; background: rgba(0,0,0,0.05); }}
            .notif-content {{ flex-grow: 1; }}
            .notif-time {{ font-size: 12px; opacity: 0.6; white-space: nowrap; }}
            .badge-new {{ background-color: #e74c3c; color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; margin-left: 5px; }}
        </style>
        """, unsafe_allow_html=True)

        # --- SOL MENÜ ---
        with st.sidebar:
            st.markdown(
                f"<div style='text-align:center; margin-bottom:20px;'><h2 style='color:{self.colors['brand']}; margin:0;'>🛡 Yönetim</h2></div>",
                unsafe_allow_html=True)
            menu = ["📊 Genel Bakış", "📝 Başvurular", "💖 Bağışlar", "📢 Duyurular", "🐾 İlan Yönetimi", "🖼 Görseller",
                    "👥 Personel"]
            choice = st.radio("Menü", menu, label_visibility="collapsed")
            st.markdown("---")
            c1, c2 = st.columns(2)
            if c1.button("👁 Site"): st.session_state.page = "Anasayfa"; st.rerun()
            if c2.button("🚪 Çıkış"):
                st.session_state.is_logged_in = False
                st.session_state.user_role = "Misafir"
                st.session_state.page = "Anasayfa"
                st.rerun()

        # --- BAŞLIK ---
        try:
            today_str = datetime.now().strftime("%d %B %Y")
        except:
            today_str = ""
        st.markdown(
            f"<div style='display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid {self.colors['border']}; padding-bottom:15px; margin-bottom:20px;'><h1 style='margin:0; font-size:28px;'>{choice}</h1><span style='opacity:0.6;'>{today_str}</span></div>",
            unsafe_allow_html=True)

        # --- YÖNLENDİRME ---
        if choice == "📊 Genel Bakış":
            self._page_dashboard()
        elif choice == "📝 Başvurular":
            self._page_applications()
        elif choice == "💖 Bağışlar":
            self._page_donations()
        elif choice == "📢 Duyurular":
            self._page_announcements()
        elif choice == "🐾 İlan Yönetimi":
            self._page_animals()
        elif choice == "🖼 Görseller":
            self._page_images()
        elif choice == "👥 Personel":
            self._page_staff()

    # --- YARDIMCI METODLAR ---
    def get_combined_activity_feed(self):
        activities = []
        for app in db.get_applications():
            activities.append(
                {"type": "basvuru", "date": app[7], "msg": f"<b>{app[3]}</b>, {app[2]} için başvurdu.", "icon": "📝",
                 "color": "#3498db"})
        for don in db.get_donations():
            activities.append(
                {"type": "bagis", "date": don[4], "msg": f"<b>{don[1]}</b>, {don[2]} TL bağışladı.", "icon": "💰",
                 "color": "#2ecc71"})
        for ani in db.get_animals(None):
            date_val = ani[10] if len(ani) > 10 else "2024-01-01"
            activities.append(
                {"type": "hayvan", "date": date_val, "msg": f"Yeni kayıt: <b>{ani[2]}</b> ({ani[1]})", "icon": "🩺",
                 "color": "#e74c3c"})
        try:
            activities.sort(key=lambda x: x['date'], reverse=True)
        except:
            pass
        return activities

    # --- SAYFALAR ---

    def _page_dashboard(self):
        try:
            apps = db.get_applications();
            dons = db.get_donations();
            all_animals = db.get_animals(None);
            anns = db.get_announcements()
            active_animals = [a for a in all_animals if a[6] != 'Sahiplendirildi']
            n_app = sum(1 for a in apps if a[6] == "Bekliyor")
            n_don = sum(d[2] for d in dons)
        except:
            n_app, n_don, active_animals, anns = 0, 0, [], []

        c1, c2, c3, c4 = st.columns(4)
        met_data = [("📩 Bekleyen", n_app, "#e74c3c"), ("💰 Kasa", f"₺{n_don:,}", "#2ecc71"),
                    ("🐾 Mevcut Canlar", len(active_animals), self.colors['brand']), ("👥 Ziyaretçi", "128", "#9b59b6")]
        for c, (t, v, clr) in zip([c1, c2, c3, c4], met_data):
            with c: st.markdown(
                f"<div class='metric-box'><div style='font-size:13px; opacity:0.7;'>{t}</div><div style='font-size:24px; font-weight:bold; color:{clr}'>{v}</div></div>",
                unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        c_feed, c_stats = st.columns([2, 1], gap="large")

        with c_feed:
            st.subheader("🔔 Son Hareketler")
            all_activities = self.get_combined_activity_feed()
            if 'activity_limit' not in st.session_state: st.session_state.activity_limit = 5
            curr_acts = all_activities[:st.session_state.activity_limit]
            today = datetime.now().strftime("%Y-%m-%d")

            if not curr_acts:
                st.info("Hareket yok.")
            else:
                for act in curr_acts:
                    is_new = today in str(act['date'])
                    bdg = "<span class='badge-new'>YENİ</span>" if is_new else ""
                    cls = "notif-new" if is_new else ""
                    st.markdown(
                        f"""<div class="notif-card {cls}"><div class="notif-icon" style="color:{act['color']}">{act['icon']}</div><div class="notif-content"><div style="font-size:14px;">{act['msg']} {bdg}</div><div class="notif-time">🕒 {act['date']}</div></div></div>""",
                        unsafe_allow_html=True)
                if len(all_activities) > st.session_state.activity_limit:
                    if st.button("🔽 Daha Fazla"): st.session_state.activity_limit += 5; st.rerun()

        with c_stats:
            st.subheader("🩺 Sağlık Durumu")
            if active_animals:
                cats = sum(1 for a in active_animals if a[1] == "Kedi")
                dogs = sum(1 for a in active_animals if a[1] == "Köpek")
                sick = sum(1 for a in active_animals if "Tedavi" in a[6] or "Bakım" in a[6])
                if sick > 0:
                    st.error(f"⚠️ **{sick}** hayvan tedavi sürecinde.")
                else:
                    st.success("Tüm hayvanlar stabil.")
                st.markdown("---")
                st.bar_chart({"Kedi": cats, "Köpek": dogs})
            else:
                st.info("Veri yok.")

    def _page_applications(self):
        apps = db.get_applications();
        all_animals = db.get_animals(None)
        pending = [a for a in apps if a[6] == "Bekliyor"]
        history = [a for a in apps if a[6] != "Bekliyor"]

        if 'inspect_app_id' not in st.session_state: st.session_state.inspect_app_id = None

        if st.session_state.inspect_app_id is not None:
            sel_app = next((a for a in apps if a[0] == st.session_state.inspect_app_id), None)
            if sel_app:
                linked = next((x for x in all_animals if x[0] == sel_app[1]), None)
                if st.button("← Geri", use_container_width=True): st.session_state.inspect_app_id = None; st.rerun()
                st.markdown("---")
                c_left, c_right = st.columns([2, 1], gap="large")
                with c_left:
                    st.markdown("### 👤 Başvuran")
                    st.markdown(
                        f"""<div style="background:{self.colors['card_bg']}; padding:20px; border-radius:12px; border:1px solid {self.colors['border']};"><div style="display:flex; justify-content:space-between;"><div><small>Ad Soyad</small><br><b>{sel_app[3]}</b></div><div><small>Tarih</small><br>{sel_app[7]}</div></div><br><div><small>İletişim</small><br><b style="color:{self.colors['brand']};">{sel_app[4]}</b></div></div>""",
                        unsafe_allow_html=True)
                    st.markdown("### 📝 Mesaj");
                    st.info(f"\"{sel_app[5]}\"")
                    st.markdown("### ⚖️ Karar")
                    ca, cb = st.columns(2)
                    if ca.button("✅ ONAYLA", use_container_width=True):
                        db.update_application_status(sel_app[0], "Onaylandı")
                        db.set_animal_adopted(sel_app[1])
                        st.success("Onaylandı!");
                        st.session_state.inspect_app_id = None;
                        time.sleep(1);
                        st.rerun()
                    if cb.button("❌ REDDET", use_container_width=True):
                        db.update_application_status(sel_app[0], "Reddedildi")
                        st.error("Reddedildi.");
                        st.session_state.inspect_app_id = None;
                        time.sleep(1);
                        st.rerun()
                with c_right:
                    st.markdown("### 🐾 Talip Olunan")
                    if linked:
                        st.image(linked[9] or "https://via.placeholder.com/400", use_column_width=True)
                        st.markdown(f"<div style='text-align:center;'><h3>{linked[2]}</h3><p>{linked[1]}</p></div>",
                                    unsafe_allow_html=True)
            else:
                st.error("Hata"); st.session_state.inspect_app_id = None; st.rerun()
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Bekleyen", len(pending));
            c2.metric("Onaylanan", len([x for x in history if x[6] == "Onaylandı"]))
            c3.metric("Reddedilen", len([x for x in history if x[6] == "Reddedildi"]))
            st.markdown("<br>", unsafe_allow_html=True)
            t1, t2 = st.tabs(["⏳ Bekleyenler", "🗂 Geçmiş"])
            with t1:
                if not pending: st.info("Bekleyen yok.")
                for a in pending:
                    c1, c2, c3, c4 = st.columns([2, 2, 2, 1.5], vertical_alignment="center")
                    c1.write(a[3]);
                    c2.write(a[2]);
                    c3.write(a[7])
                    if c4.button("İncele", key=f"v_{a[0]}", use_container_width=True): st.session_state.inspect_app_id = \
                    a[0]; st.rerun()
                    st.divider()
            with t2:
                if history:
                    import pandas as pd
                    st.dataframe(pd.DataFrame(
                        [{"Ad": h[3], "Hayvan": h[2], "Durum": h[6], "Tarih": h[7]} for h in history]).iloc[::-1],
                                 use_container_width=True, hide_index=True)
                else:
                    st.warning("Kayıt yok.")

    def _page_donations(self):
        c_list, c_chart = st.columns([1, 1], gap="large")
        try:
            dons = db.get_donations()
        except:
            dons = []

        with c_list:
            st.markdown("##### 📋 Bağış Listesi")
            if not dons:
                st.info("Kayıt yok.")
            else:
                with st.container(height=500):
                    for d in dons:
                        try:
                            st.markdown(
                                f"""<div style="border-bottom:1px solid #333; padding:10px; display:flex; justify-content:space-between;"><div><b>{d[1]}</b><br><small>{d[4]}</small></div><div style="color:#2ecc71;">₺{d[2]}</div></div>""",
                                unsafe_allow_html=True)
                        except:
                            continue

        with c_chart:
            st.markdown("##### 📊 Analiz")
            if dons:
                try:
                    cd = {}
                    for d in dons:
                        val = float(d[2]) if d[2] else 0
                        cd[d[4]] = cd.get(d[4], 0) + val
                    st.bar_chart(cd, color="#2ecc71")
                    st.metric("Toplam", f"₺{sum(cd.values()):,.2f}")
                except:
                    st.warning("Grafik hatası.")
            else:
                st.info("Veri yok.")

    def _page_announcements(self):
        c_form, c_list = st.columns(2, gap="large")

        with c_form:
            st.markdown("##### ➕ Duyuru Ekle")
            # --- DÜZELTME BURADA: clear_on_submit=True ---
            # Bu sayede 'Yayınla'ya basınca form temizlenir.
            with st.form("add_ann", clear_on_submit=True):
                t = st.text_input("Başlık")
                d = st.text_area("İçerik")
                o = st.number_input("Sıra", 1, 100, 1)
                f = st.file_uploader("Görsel")
                if st.form_submit_button("Yayınla", use_container_width=True):
                    img = Utils.process_image_upload(f) or "https://via.placeholder.com/800"
                    db.add_announcement(t, d, img, o)
                    st.success("Yayınlandı!");
                    time.sleep(1);
                    st.rerun()

        with c_list:
            st.markdown("##### 📢 Düzenle / Sil")
            anns = db.get_announcements()
            if not anns: st.info("Duyuru yok.")
            for a in anns:
                with st.expander(f"#{a[5]} - {a[1]}"):
                    st.image(a[3], use_column_width=True)
                    nt = st.text_input("Başlık", a[1], key=f"nt_{a[0]}")
                    nd = st.text_area("İçerik", a[2], key=f"nd_{a[0]}")
                    no = st.number_input("Sıra", value=int(a[5]), min_value=1, key=f"no_{a[0]}")
                    c_sv, c_del = st.columns(2)
                    if c_sv.button("💾", key=f"sv_{a[0]}", use_container_width=True):
                        db.update_announcement_details(a[0], nt, nd, a[3], no)
                        st.success("Güncellendi!");
                        time.sleep(0.5);
                        st.rerun()
                    if c_del.button("🗑", key=f"dl_{a[0]}", use_container_width=True):
                        db.delete_announcement(a[0]);
                        st.rerun()

    def _page_animals(self):
        c_form, c_list = st.columns(2, gap="large")

        # --- 1. İLAN EKLEME FORMU ---
        with c_form:
            st.markdown("##### ➕ İlan Ekle")
            with st.form("add_animal", clear_on_submit=True):
                nm = st.text_input("Adı *")
                tp = st.selectbox("Tür", ["Kedi", "Köpek"])
                ag = st.number_input("Yaş", 0, 25, 1)
                gn = st.selectbox("Cinsiyet", ["Dişi", "Erkek"])
                br = st.text_input("Cins (Örn: Tekir, Golden)")
                fl = st.file_uploader("Fotoğraf")
                ds = st.text_area("Hikaye / Açıklama")

                if st.form_submit_button("Kaydet", use_container_width=True):
                    img = Utils.process_image_upload(fl) or "https://via.placeholder.com/400"
                    db.add_animal(tp, nm, ag, gn, br, ds, img)
                    st.success("Eklendi!");
                    time.sleep(1);
                    st.rerun()

            # --- YENİ EKLENEN KISIM: TOPLU GÖRSEL ANALİZ ---
            st.markdown("---")
            st.markdown("##### 🧠 Yapay Zeka Görsel Tarama")
            st.info("Var olan fotoğrafları tarayarak renk ve tür bilgilerini veritabanına işler.")

            if st.button("✨ Tüm Arşivi Tara ve Güncelle", use_container_width=True):
                # İlerleme çubuğu
                progress_text = "Fotoğraflar inceleniyor. Lütfen bekleyin..."
                my_bar = st.progress(0, text=progress_text)

                all_animals = db.get_animals(None)
                total = len(all_animals)

                # --- DÜZELTME BURADA YAPILDI ---
                # Eskiden: model = genai.GenerativeModel('gemini-1.5-flash') (Hata veren yer)
                # Şimdi: Senin güçlü modellerini otomatik bulan fonksiyonu çağırıyoruz.
                model = AIService._get_best_model()

                if not model:
                    st.error("Model bulunamadı! Lütfen API anahtarını kontrol et.")
                else:
                    for i, animal in enumerate(all_animals):
                        # animal[9] -> Resim URL/Base64
                        # animal[11] -> Mevcut Açıklama
                        img_data = animal[9]
                        current_desc = animal[11] or ""
                        animal_name = animal[2]

                        # Eğer resim varsa ve daha önce analiz edilmemişse
                        if img_data and "görsel_analiz" not in current_desc:
                            try:
                                # 1. Base64 verisini Görüntüye Çevir
                                if "base64," in img_data:
                                    _, encoded = img_data.split(",", 1)
                                    image_bytes = base64.b64decode(encoded)
                                    img = Image.open(io.BytesIO(image_bytes))

                                    # 2. Gemini'ye Sor
                                    prompt = """
                                    Bu resimdeki hayvanın fiziksel özelliklerini (Rengi, deseni, cinsi, tüy yapısı) 
                                    Türkçe olarak, virgülle ayrılmış anahtar kelimeler halinde yaz. 
                                    Örnek çıktı: Sarı, Tekir, Yeşil Gözlü, Tüylü
                                    """
                                    response = model.generate_content([prompt, img])
                                    ai_tags = response.text.strip()

                                    # 3. Mevcut açıklamaya ekle
                                    new_desc = f"{current_desc}\n\n[Görsel Özellikleri: {ai_tags}]"

                                    # 4. Veritabanını Güncelle
                                    db.update_animal_details(
                                        animal[0], animal[2], animal[3], animal[6], new_desc, animal[9]
                                    )
                                    # Hata almamak için kısa bir bekleme
                                    time.sleep(1.5)

                            except Exception as e:
                                print(f"Hata ({animal_name}): {e}")

                        # İlerleme çubuğunu güncelle
                        percent = int(((i + 1) / total) * 100)
                        my_bar.progress(percent, text=f"{animal_name} inceleniyor... (%{percent})")

                    my_bar.empty()
                    st.success("🎉 Tüm arşiv tarandı! Artık 'Sarı kedi' veya 'Siyah köpek' diye arama yapabilirsiniz.")
                    time.sleep(2)
                    st.rerun()

        # --- 2. İLAN LİSTESİ ---
        with c_list:
            st.markdown("##### 📋 İlanlar")
            src = st.text_input("🔍 Ara")
            all_a = db.get_animals(None)
            act_a = [x for x in all_a if x[6] != 'Sahiplendirildi']
            adopted = [x for x in all_a if x[6] == 'Sahiplendirildi']
            if src: act_a = [x for x in act_a if src.lower() in x[2].lower()]

            if not act_a: st.info("İlan yok.")
            for a in act_a:
                icon = "🐱" if a[1] == "Kedi" else "🐶"
                with st.expander(f"{icon} {a[2]}"):
                    st.image(a[9] or "https://via.placeholder.com/300", width=120)
                    nn = st.text_input("Ad", a[2], key=f"n_{a[0]}")
                    na = st.number_input("Yaş", value=int(a[3]), key=f"ag_{a[0]}")
                    ho = ["Muayene Bekliyor", "Çok İyi", "İyi", "Tedavi Görüyor", "Bakıma Muhtaç", "Sahiplendirildi"]
                    try:
                        h_idx = ho.index(a[6])
                    except:
                        h_idx = 0
                    nh = st.selectbox("Durum", ho, index=h_idx, key=f"st_{a[0]}")
                    nd = st.text_area("Hikaye", a[11], key=f"ds_{a[0]}")
                    c_up, c_dl = st.columns(2)
                    if c_up.button("Güncelle", key=f"up_{a[0]}", use_container_width=True):
                        db.update_animal_details(a[0], nn, na, nh, nd, a[9])
                        st.success("Güncellendi!");
                        st.rerun()
                    if c_dl.button("Sil", key=f"dl_{a[0]}", use_container_width=True):
                        db.delete_animal(a[0]);
                        st.rerun()

            st.markdown("---")
            with st.expander(f"🗄️ Sahiplendirilenler Arşivi ({len(adopted)})"):
                for old in adopted:
                    st.markdown(f"✅ **{old[2]}** - {old[1]}")
                    if st.button("Sil", key=f"del_old_{old[0]}"): db.delete_animal(old[0]); st.rerun()

    def _page_images(self):
        st.info("ℹ️ Görselleri buradan güncelleyebilirsiniz.")
        c1, c2 = st.columns(2, gap="large")
        with c1:
            st.markdown("### 🐱 Kedi")
            st.image(db.get_setting('home_cat_img') or "https://via.placeholder.com/400", use_column_width=True)
            f = st.file_uploader("Yükle", key="u_cat")
            if f and st.button("Kaydet (Kedi)", key="b_cat"):
                db.set_setting('home_cat_img', Utils.process_image_upload(f));
                st.success("Tamam");
                time.sleep(0.5);
                st.rerun()
        with c2:
            st.markdown("### 🐶 Köpek")
            st.image(db.get_setting('home_dog_img') or "https://via.placeholder.com/400", use_column_width=True)
            f = st.file_uploader("Yükle", key="u_dog")
            if f and st.button("Kaydet (Köpek)", key="b_dog"):
                db.set_setting('home_dog_img', Utils.process_image_upload(f));
                st.success("Tamam");
                time.sleep(0.5);
                st.rerun()
        st.markdown("---")
        c3, c4 = st.columns(2, gap="large")
        with c3:
            st.markdown("### 💖 Bağış")
            st.image(db.get_setting('donation_img') or "https://via.placeholder.com/400", use_column_width=True)
            f = st.file_uploader("Yükle", key="u_don")
            if f and st.button("Kaydet (Bağış)", key="b_don"):
                db.set_setting('donation_img', Utils.process_image_upload(f));
                st.success("Tamam");
                time.sleep(0.5);
                st.rerun()
        with c4:
            st.markdown("### 📜 Sertifika")
            curr = db.get_setting('certificate_img')
            if curr:
                st.image(curr, use_column_width=True)
            else:
                st.warning("Yok.")
            f = st.file_uploader("Yükle", key="u_cert")
            if f and st.button("Kaydet (Sertifika)", key="b_cert"):
                db.set_setting('certificate_img', Utils.process_image_upload(f));
                st.success("Tamam");
                time.sleep(0.5);
                st.rerun()

    def _page_staff(self):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### ➕ Ekle")
            # --- DÜZELTME BURADA: clear_on_submit=True ---
            with st.form("stf", clear_on_submit=True):
                r = st.selectbox("Rol", ["Veteriner", "Barınak Yöneticisi"])
                u = st.text_input("Kullanıcı Adı")
                p = st.text_input("Şifre", type="password")
                if st.form_submit_button("Ekle", use_container_width=True):
                    db.add_user(u, p, r);
                    st.success("Eklendi");
                    st.rerun()
        with c2:
            st.markdown("##### 📋 Liste")
            for s in db.get_staff_list(): st.info(f"{s[0]} ({s[1]})")

class VeterinaryPage(BasePage):
    def render(self):
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        with c1:
            st.markdown(f"<h2 style='margin:0; color:{self.colors['brand']};'>🩺 Veteriner Paneli</h2>",
                        unsafe_allow_html=True)
        with c2:
            if st.button("Çıkış Yap"):
                st.session_state.is_logged_in = False
                st.session_state.user_role = "Misafir"
                self.navigate("Anasayfa")
        st.markdown("---")

        search = st.text_input("🔍 Hasta Ara")
        animals = db.get_animals(None)
        if search: animals = [a for a in animals if search.lower() in a[2].lower()]

        cols = st.columns(2)
        for idx, a in enumerate(animals):
            with cols[idx % 2]:
                with st.container():
                    st.markdown(
                        f"""<div style="background:{self.colors['card_bg']}; padding:15px; border-radius:12px; border:1px solid {self.colors['border']}; margin-bottom:15px; display:flex; gap:15px;"><img src="{a[9] or '[https://via.placeholder.com/150](https://via.placeholder.com/150)'}" style="width:100px; height:100px; object-fit:cover; border-radius:10px;"><div><h3>{a[2]}</h3><p>{a[6]}</p></div></div>""",
                        unsafe_allow_html=True)
                    with st.expander("🩺 Muayene Gir"):
                        with st.form(key=f"vet_{a[0]}"):
                            opts = ["Muayene Bekliyor", "Çok İyi", "İyi", "Tedavi Görüyor", "Bakıma Muhtaç"]
                            nh = st.selectbox("Durum", opts, index=opts.index(a[6]) if a[6] in opts else 0)
                            nd = st.text_area("Tanı", value=a[7] or "")
                            ns = st.selectbox("Kısırlaştırma", ["Bilinmiyor", "Kısırlaştırıldı", "Kısırlaştırılmadı"],
                                              index=0)
                            if st.form_submit_button("Kaydet"):
                                db.update_animal_health_vet(a[0], nh, nd, ns)
                                st.success("Kaydedildi");
                                st.rerun()

class ProfilePage(BasePage):
    def render(self):
        self.render_header()

        st.markdown("<br>", unsafe_allow_html=True)

        col_title, col_logout = st.columns([4, 1], gap="medium", vertical_alignment="center")

        # --- DÜZELTME BURADA YAPILDI ---
        # Artık 'login_user' değil, yukarıda kaydettiğimiz 'username'i çekiyoruz
        active_username = st.session_state.get('username', 'Misafir')

        with col_title:
            st.markdown(f"""
            <h2 style='color:{self.colors['brand']}; margin:0; padding:0; font-size: 2rem;'>
                👤 Kullanıcı Profili
            </h2>
            <div style='font-size: 1.5rem; font-weight: 500; margin-top: 5px; color: {self.colors['text']};'>
                Hoşgeldin, <span style='font-weight: 700; color:{self.colors['brand']}'>{active_username}</span> 👋
            </div>
            """, unsafe_allow_html=True)

        with col_logout:
            if st.button("Çıkış Yap", key="logout_btn_top", use_container_width=True):
                st.session_state.is_logged_in = False
                st.session_state.user_role = "Misafir"
                # Çıkış yapınca username'i de silebiliriz
                if 'username' in st.session_state:
                    del st.session_state['username']
                st.session_state.page = "Anasayfa"
                st.rerun()

        st.markdown("---")

        tab1, tab2 = st.tabs(["Başvurularım", "Geçmiş Bağışlar"])

        with tab1:
            st.markdown("<br>", unsafe_allow_html=True)
            # Fonksiyona doğru ismi gönderiyoruz
            df_app = get_user_applications(active_username)

            if not df_app.empty:
                with st.container():
                    st.dataframe(
                        df_app,
                        use_container_width=True,
                        hide_index=True,
                        column_config={"Durum": st.column_config.TextColumn("Durum", width="medium")}
                    )
            else:
                st.info(f"Sayın {active_username}, henüz bir sahiplendirme başvurunuz bulunmuyor.")
                if st.button("Hemen Sahiplen", key="go_adopt_profile"):
                    self.navigate("Sahiplen")

        with tab2:
            st.markdown("<br>", unsafe_allow_html=True)
            df_don = get_user_donations(active_username)

            if not df_don.empty:
                try:
                    total = df_don['Miktar'].astype(str).str.replace(' TL', '').str.replace(',', '').astype(float).sum()
                    st.metric(label="Toplam Katkınız", value=f"₺{total:,.2f}")
                except:
                    pass
                st.dataframe(df_don, use_container_width=True, hide_index=True)
            else:
                st.warning("Henüz bir bağış kaydınız yok. Minik bir destekle başlayabilirsiniz! 🍲")
                if st.button("Bağış Yap", key="go_donate_profile"):
                    self.navigate("Bağış")

        self.render_footer()

# ==========================================
# 4. UYGULAMA YÖNETİCİSİ (Main App Class)
# ==========================================

class PatityApp:
    def __init__(self):
        Config.init()
        self._init_session_state()
        self.colors = StyleManager.apply_styles(st.session_state.dark_mode)

    def _init_session_state(self):
        defaults = {
            'page': "Anasayfa", 'filter_choice': "Tümü", 'user_role': "Misafir",
            'is_logged_in': False, 'dark_mode': False, 'slider_index': 0,
            'donation_frequency': "Tek Seferlik", 'donation_step': None,
            'card_input': "", 'skt_input': "", 'donation_amount': 100,
            'donor_name': "",

            # --- DEĞİŞİKLİK BURADA ---
            # Eskiden burası [] idi. Şimdi içine ilk mesajı koyduk.
            'messages': [{
                "role": "assistant",
                "content": "Merhaba! Ben Piti 🐾 Sana nasıl yardımcı olabilirim? (Örn: 'Sakin kedi var mı?', 'Yavru köpekleri göster')"
            }]
        }
        for k, v in defaults.items():
            if k not in st.session_state: st.session_state[k] = v

    def render_chatbot(self):
        # 1. İkon ve Başlık
        with st.popover("🤖", use_container_width=False):
            st.markdown(
                f"""<div style="text-align:center;"><h3 style="color:#FF9F43; margin:0;">Piti 🐾</h3><p style="font-size:12px;">Yapay zeka asistanı.</p></div><hr>""",
                unsafe_allow_html=True)

            # 2. Mesaj Alanı
            chat_cont = st.container(height=450)  # Yüksekliği artırdık
            with chat_cont:
                for idx, msg in enumerate(st.session_state.messages):
                    with st.chat_message(msg["role"], avatar="🤖" if msg["role"] == "assistant" else "👤"):

                        if isinstance(msg["content"], list):
                            st.markdown("🎉 **İşte Senin İçin Bulduklarım:**")
                            for animal in msg["content"]:
                                name = animal[2]
                                age = animal[3]
                                breed = animal[5]
                                desc = animal[11] if len(animal) > 11 and animal[11] else "..."

                                # HTML KART TASARIMI (BÜYÜTÜLMÜŞ VERSİYON V2)
                                # padding: 22px (Daha geniş iç boşluk)
                                # font-size: 18px (Daha büyük başlık)
                                card_html = f"""
                                <div style="
                                    background-color: rgba(255, 159, 67, 0.08); 
                                    padding: 22px; 
                                    border-radius: 15px; 
                                    margin-bottom: 5px; 
                                    border-left: 5px solid #FF9F43;
                                    box-shadow: 0 2px 5px rgba(0,0,0,0.05);">
                                    <div style="font-size: 18px; font-weight: bold; color: #FF9F43; margin-bottom: 8px;">
                                        🐾 {name} <span style="font-size: 14px; color: #666; font-weight: normal;">({age} Yaş, {breed})</span>
                                    </div>
                                    <div style="font-size: 15px; opacity: 0.9; line-height: 1.6; color: inherit;">
                                        📝 <i>{desc[:100]}...</i>
                                    </div>
                                </div>
                                """
                                st.markdown(card_html, unsafe_allow_html=True)

                                unique_key = f"chat_btn_{idx}_{animal[0]}"

                                # Butonun kendisi StyleManager ile küçülecek
                                if st.button(f"🔍 {name} profiline git", key=unique_key):
                                    st.session_state['selected_animal'] = animal
                                    st.session_state.page = "Sahiplen"
                                    st.session_state.filter_choice = "Tümü"
                                    st.rerun()
                                st.markdown("<div style='margin-bottom: 15px;'></div>",
                                            unsafe_allow_html=True)  # Kartlar arası boşluk

                        else:
                            if msg["role"] == "assistant":
                                st.markdown(
                                    f"""<div style="background-color: rgba(255, 159, 67, 0.1); padding: 15px; border-radius: 12px; font-size: 15px;">{msg['content']}</div>""",
                                    unsafe_allow_html=True)
                            else:
                                st.markdown(msg["content"])

            # 3. Yeni Mesaj Girişi
            if prompt := st.chat_input("Sorunu yaz..."):
                st.session_state.messages.append({"role": "user", "content": prompt})

                with chat_cont:
                    st.chat_message("user", avatar="👤").markdown(prompt)
                    with st.chat_message("assistant", avatar="🤖"):
                        with st.spinner("Piti düşünüyor..."):
                            resp = AIService.ask_ai_local(prompt)

                            if isinstance(resp, list):
                                st.markdown("🎉 **Sonuçları listeliyorum...**")
                            else:
                                st.markdown(
                                    f"""<div style="background-color: rgba(255, 159, 67, 0.1); padding: 15px; border-radius: 12px; font-size: 15px;">{resp}</div>""",
                                    unsafe_allow_html=True)

                st.session_state.messages.append({"role": "assistant", "content": resp})
                st.rerun()
    def run(self):
        # LOGİN SAYFASI
        if st.session_state.page == "Login":
            st.markdown("""<style>[data-testid="stSidebar"] {display: none;}</style>""", unsafe_allow_html=True)
            LoginPage(self.colors).render()

        # YÖNETİCİ MODU
        elif st.session_state.is_logged_in and st.session_state.user_role == "Barınak Yöneticisi":
            # Site sayfalarını geziyorsa (Anasayfa, Sahiplen, Bağış)
            if st.session_state.page in ["Anasayfa", "Sahiplen", "Bağış"]:
                st.markdown("""<style>[data-testid="stSidebar"] {display: block;}</style>""", unsafe_allow_html=True)
                with st.sidebar:
                    st.header("🔧 Yönetici Modu")
                    st.info(f"Şu an **{st.session_state.page}** sayfasındasınız.")
                    if st.button("⬅ Panele Dön", use_container_width=True):
                        st.session_state.page = "Admin"
                        st.rerun()
                    st.markdown("---")
                    st.markdown("### 🧭 Site Gezintisi")
                    if st.button("🏠 Anasayfa", use_container_width=True): st.session_state.page = "Anasayfa"; st.rerun()
                    if st.button("🐾 Sahiplen", use_container_width=True): st.session_state.page = "Sahiplen"; st.rerun()
                    if st.button("💖 Bağış", use_container_width=True): st.session_state.page = "Bağış"; st.rerun()

                if st.session_state.page == "Anasayfa":
                    HomePage(self.colors).render()
                elif st.session_state.page == "Sahiplen":
                    AdoptionPage(self.colors).render()
                elif st.session_state.page == "Bağış":
                    DonationPage(self.colors).render()

            # Admin Panelindeyse
            else:
                st.markdown("""<style>[data-testid="stSidebar"] {display: block;}</style>""", unsafe_allow_html=True)
                AdminPage(self.colors).render()

        # VETERİNER MODU
        elif st.session_state.is_logged_in and st.session_state.user_role == "Veteriner":
            VeterinaryPage(self.colors).render()

        else:  # Normal Kullanıcı / Misafir
            if st.session_state.page == "Anasayfa":
                HomePage(self.colors).render()
            elif st.session_state.page == "Sahiplen":
                AdoptionPage(self.colors).render()
            elif st.session_state.page == "Bağış":
                DonationPage(self.colors).render()
            # YENİ EKLENEN KISIM BURASI:
            elif st.session_state.page == "Profil":
                ProfilePage(self.colors).render()
            # --------------------------
            else:
                HomePage(self.colors).render()

        self.render_chatbot()
# ==========================================
# 5. ÇALIŞTIRMA (Entry Point)
# ==========================================
if __name__ == "__main__":
    app = PatityApp()
    app.run()