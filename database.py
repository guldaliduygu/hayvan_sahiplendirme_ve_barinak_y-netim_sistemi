import sqlite3
import hashlib
from datetime import datetime

# --- AYARLAR ---
DB_NAME = 'patity.db'


# --- BAĞLANTI YÖNETİMİ ---
def create_connection():
    """Veritabanı bağlantısı oluşturur."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    except sqlite3.Error as e:
        print(f"Veritabanı bağlantı hatası: {e}")
    return conn


def initialize_database():
    """Tabloları oluşturur ve eksik sütun varsa ekler (Migration)."""
    conn = create_connection()
    c = conn.cursor()

    # 1. KULLANICILAR
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT,
                role TEXT
                )''')

    # 2. HAYVANLAR
    c.execute('''CREATE TABLE IF NOT EXISTS animals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT, name TEXT, age INTEGER, gender TEXT, breed TEXT,
                health_status TEXT, disease_history TEXT DEFAULT 'Belirtilmemiş',
                sterilization_status TEXT DEFAULT 'Bilinmiyor',
                image_url TEXT, adoption_status TEXT DEFAULT 'Musait',
                description TEXT DEFAULT '',
                added_date TEXT
                )''')

    # 3. BAŞVURULAR (Detaylı Yapı)
    c.execute('''CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                animal_id INTEGER, 
                animal_name TEXT, 
                applicant_name TEXT,
                phone TEXT, 
                age TEXT,
                occupation TEXT,
                home_type TEXT,
                has_garden TEXT,
                balcony_net TEXT,
                other_pets TEXT,
                working_hours TEXT,
                message TEXT,
                status TEXT DEFAULT 'Bekliyor',
                application_date TEXT)''')

    # 4. BAĞIŞLAR
    c.execute('''CREATE TABLE IF NOT EXISTS donations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                donor_name TEXT, 
                amount INTEGER, 
                method TEXT,
                message TEXT, 
                date TEXT)''')

    # 5. DUYURULAR
    c.execute('''CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                description TEXT,
                image_url TEXT,
                date_added TEXT,
                display_order INTEGER DEFAULT 100
                )''')

    # 6. AYARLAR
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')

    conn.commit()
    conn.close()

    # MIGRATION: Eksik sütunları kontrol et ve ekle
    _migrate_columns()


def _migrate_columns():
    """Mevcut veritabanına sonradan eklenen sütunları güvenli şekilde ekler."""
    conn = create_connection()
    c = conn.cursor()

    # Eklenecek sütunlar: (Tablo, Sütun Adı, Tür)
    columns_to_check = [
        ('animals', 'description', 'TEXT DEFAULT ""'),
        ('animals', 'added_date', 'TEXT'),
        ('announcements', 'display_order', 'INTEGER DEFAULT 100'),
        ('applications', 'age', 'TEXT'),
        ('applications', 'occupation', 'TEXT'),
        ('applications', 'home_type', 'TEXT'),
        ('applications', 'has_garden', 'TEXT'),
        ('applications', 'balcony_net', 'TEXT'),
        ('applications', 'other_pets', 'TEXT'),
        ('applications', 'working_hours', 'TEXT'),
        ('applications', 'application_date', 'TEXT')  # Tarih sütunu
    ]

    for table, col, dtype in columns_to_check:
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {dtype}")
            print(f"✅ Tablo '{table}' güncellendi: '{col}' eklendi.")
        except sqlite3.OperationalError:
            pass  # Sütun zaten varsa hata verir, görmezden geliyoruz.

    # Eski 'date' sütununu 'application_date' olarak kopyalamayı dene (Varsa)
    try:
        # Eğer eski 'date' sütunu varsa ve 'application_date' boşsa kopyala
        c.execute("UPDATE applications SET application_date = date WHERE application_date IS NULL")
    except:
        pass

    conn.commit()
    conn.close()


# ==========================================
# FONKSİYONLAR
# ==========================================

# --- KULLANICI ---
def add_user(username, password, role="Kullanıcı"):
    conn = create_connection()
    c = conn.cursor()
    # Şifreleme (Hash)
    hashed_pw = hashlib.sha256(password.encode()).hexdigest()
    try:
        c.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', (username, hashed_pw, role))
        conn.commit()
        conn.close()
        return True, "Kayıt Başarılı"
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Bu kullanıcı adı zaten kullanılıyor."


def check_login(username, password, selected_role):
    conn = create_connection()
    c = conn.cursor()
    hashed_pw = hashlib.sha256(password.encode()).hexdigest()
    c.execute('SELECT role FROM users WHERE username=? AND password=? AND role=?', (username, hashed_pw, selected_role))
    data = c.fetchone()
    conn.close()
    return True if data else False


def get_staff_list():
    conn = create_connection()
    c = conn.cursor()
    c.execute("SELECT username, role FROM users WHERE role IN ('Veteriner', 'Barınak Yöneticisi')")
    data = c.fetchall()
    conn.close()
    return data


# --- HAYVANLAR ---
def add_animal(type, name, age, gender, breed, description, img):
    conn = create_connection()
    c = conn.cursor()
    date_now = datetime.now().strftime("%Y-%m-%d")
    c.execute(
        "INSERT INTO animals (type, name, age, gender, breed, health_status, disease_history, sterilization_status, image_url, description, added_date) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (type, name, age, gender, breed, "Muayene Bekliyor", "Belirtilmemiş", "Bilinmiyor", img, description, date_now))
    conn.commit()
    conn.close()


def get_animals(filter_type=None):
    conn = create_connection()
    c = conn.cursor()
    if filter_type and filter_type != "Tümü":
        c.execute("SELECT * FROM animals WHERE type=?", (filter_type,))
    else:
        c.execute("SELECT * FROM animals")
    data = c.fetchall()
    conn.close()
    return data


def delete_animal(id):
    conn = create_connection()
    c = conn.cursor()
    c.execute("DELETE FROM animals WHERE id=?", (id,))
    conn.commit()
    conn.close()


def update_animal_details(id, name, age, health, desc, img_url):
    conn = create_connection()
    c = conn.cursor()
    c.execute("UPDATE animals SET name=?, age=?, health_status=?, description=?, image_url=? WHERE id=?",
              (name, age, health, desc, img_url, id))
    conn.commit()
    conn.close()


def update_animal_health_vet(id, health_status, disease_history, sterilization_status):
    conn = create_connection()
    c = conn.cursor()
    c.execute("UPDATE animals SET health_status=?, disease_history=?, sterilization_status=? WHERE id=?",
              (health_status, disease_history, sterilization_status, id))
    conn.commit()
    conn.close()


def set_animal_adopted(animal_id):
    conn = create_connection()
    c = conn.cursor()
    c.execute("UPDATE animals SET health_status = 'Sahiplendirildi' WHERE id = ?", (animal_id,))
    conn.commit()
    conn.close()


# --- BAŞVURULAR (TEK VE GÜNCEL FONKSİYON) ---
def add_application(animal_id, animal_name, applicant_name, phone, age, occupation, home_type, has_garden, balcony_net,
                    other_pets, working_hours, message):
    conn = create_connection()
    c = conn.cursor()
    date_now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Eğer eski koddan gelen kısa çağrılar varsa onları karşılamak için varsayılan değerler atanabilir
    # Ancak main.py yeni haliyle tüm parametreleri gönderiyor.
    c.execute('''INSERT INTO applications (
        animal_id, animal_name, applicant_name, phone, age, occupation, 
        home_type, has_garden, balcony_net, other_pets, working_hours, message, status, application_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (animal_id, animal_name, applicant_name, phone, age, occupation,
               home_type, has_garden, balcony_net, other_pets, working_hours, message, "Bekliyor", date_now))

    conn.commit()
    conn.close()


def get_applications():
    conn = create_connection()
    c = conn.cursor()
    # En yeni başvurular üstte olsun
    c.execute("SELECT * FROM applications ORDER BY id DESC")
    data = c.fetchall()
    conn.close()
    return data


def update_application_status(app_id, new_status):
    conn = create_connection()
    c = conn.cursor()
    c.execute("UPDATE applications SET status = ? WHERE id = ?", (new_status, app_id))
    conn.commit()
    conn.close()


# --- DUYURULAR ---
def add_announcement(title, description, image_url, order):
    conn = create_connection()
    c = conn.cursor()
    date_now = datetime.now().strftime("%Y-%m-%d")
    c.execute("INSERT INTO announcements (title, description, image_url, display_order, date_added) VALUES (?,?,?,?,?)",
              (title, description, image_url, order, date_now))
    conn.commit()
    conn.close()


def get_announcements():
    conn = create_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM announcements ORDER BY display_order ASC")
    data = c.fetchall()
    conn.close()
    return data


def delete_announcement(id):
    conn = create_connection()
    c = conn.cursor()
    c.execute("DELETE FROM announcements WHERE id=?", (id,))
    conn.commit()
    conn.close()


def update_announcement_details(id, title, desc, img_url, order):
    conn = create_connection()
    c = conn.cursor()
    c.execute("UPDATE announcements SET title=?, description=?, image_url=?, display_order=? WHERE id=?",
              (title, desc, img_url, order, id))
    conn.commit()
    conn.close()


# --- BAĞIŞLAR ---
def add_donation(donor_name, amount, method="Web", message=""):
    conn = create_connection()
    c = conn.cursor()
    date = datetime.now().strftime("%Y-%m-%d")
    c.execute("INSERT INTO donations (donor_name, amount, method, message, date) VALUES (?, ?, ?, ?, ?)",
              (donor_name, amount, method, message, date))
    conn.commit()
    conn.close()


def get_donations():
    conn = create_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM donations ORDER BY id DESC")
    data = c.fetchall()
    conn.close()
    return data


# --- AYARLAR ---
def set_setting(key, value):
    conn = create_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def get_setting(key):
    conn = create_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT value FROM settings WHERE key=?", (key,))
        result = c.fetchone()
        return result[0] if result else None
    except:
        return None
    finally:
        conn.close()


# --- database.py EN ALTINA YAPIŞTIR ---

def fix_database_columns():
    """Eski veritabanına yeni sütunları ekler"""
    conn = create_connection()
    c = conn.cursor()

    # Eklenecek yeni sütunlar listesi
    new_columns = [
        "user_name TEXT",  # Eski applicant_name yerine
        "age TEXT",
        "occupation TEXT",
        "home_type TEXT",
        "has_garden TEXT",
        "balcony_net TEXT",
        "other_pets TEXT",
        "working_hours TEXT",
        "reason TEXT"  # Eski message yerine
    ]

    for col in new_columns:
        try:
            # Sütun eklemeyi dene
            col_name = col.split(" ")[0]
            c.execute(f"ALTER TABLE applications ADD COLUMN {col}")
            print(f"✅ Sütun eklendi: {col_name}")
        except sqlite3.OperationalError:
            # Sütun zaten varsa hata verir, pas geçiyoruz
            pass

    # ESKİ VERİLERİ KURTARMA (Migration)
    # Eğer eski tablon varsa, 'applicant_name' içindeki veriyi 'user_name'e kopyalayalım
    try:
        c.execute("UPDATE applications SET user_name = applicant_name WHERE user_name IS NULL")
        c.execute("UPDATE applications SET reason = message WHERE reason IS NULL")
    except:
        pass  # Eski sütunlar yoksa sorun değil

    conn.commit()
    conn.close()


# Bu fonksiyonu dosya çalıştığında otomatik çağıralım
fix_database_columns()


# --- database.py EN ALTINA YAPIŞTIR (Sorun çözülünce silebilirsin) ---

def fix_date_column_error():
    """Tarih sütunu hatasını (application_date) düzeltir"""
    try:
        conn = create_connection()
        c = conn.cursor()

        # 1. YÖNTEM: Sütun ismini değiştirmeyi dene (date -> application_date)
        try:
            c.execute("ALTER TABLE applications RENAME COLUMN date TO application_date")
            print("✅ Sütun ismi başarıyla 'application_date' yapıldı!")
        except Exception as e:
            # Eğer isim değiştirme hata verirse (belki eski versiyon sqlite vardır), yeni sütun ekle
            print(f"İsim değiştirilemedi ({e}), yeni sütun ekleniyor...")
            try:
                c.execute("ALTER TABLE applications ADD COLUMN application_date TEXT")
                # Eski tarihleri yeni sütuna kopyala
                c.execute("UPDATE applications SET application_date = date WHERE application_date IS NULL")
                print("✅ Yeni 'application_date' sütunu eklendi ve veriler kurtarıldı.")
            except:
                print("⚠️ Sütun zaten var veya başka bir hata oluştu.")

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Bağlantı hatası: {e}")


# Fonksiyonu çalıştır
fix_date_column_error()

# --- BAŞLANGIÇTA ÇALIŞTIR ---
# Dosya import edildiğinde tabloları kontrol et
initialize_database()