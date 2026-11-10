import sqlite3
import pandas as pd

def jalankan_pipeline():
    url_csv = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vRxXsnDCKCgMpMfMTzda7RW3uECkWxi8OrH8u5M4NGc1kGfVKPdjv4sAfLApX1NQKpX3b-GWQ_IKTnZ/pub?output=csv'
    
    # Mengambil 7 kolom (0 sampai 6) sesuai format Excel baru
    df = pd.read_csv(url_csv, skiprows=2, usecols=[0, 1, 2, 3, 4, 5, 6], on_bad_lines='skip')
    df.columns = ['id', 'nama_tanaman', 'jumlah', 'lokasi', 'status', 'jenis_tanaman', 'foto']
    
    df = df.dropna(subset=['nama_tanaman'])
    df['id'] = pd.to_numeric(df['id'], errors='coerce').fillna(0).astype(int)
    df = df.fillna('')
    
    # Jika kategori kosong, beri nama default agar tidak error saat dikelompokkan
    df['jenis_tanaman'] = df['jenis_tanaman'].apply(lambda x: 'Lainnya' if x == '' else x)
    
    conn = sqlite3.connect('database_tanaman.db')
    df.to_sql('tanaman', conn, if_exists='replace', index=False)
    conn.close()

if __name__ == "__main__":
    jalankan_pipeline()