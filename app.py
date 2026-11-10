from flask import Flask, render_template
import sqlite3

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('database_tanaman.db')
    conn.row_factory = sqlite3.Row 
    return conn

@app.route('/')
def index():
    conn = get_db_connection()
    semua_buku = conn.execute('SELECT * FROM tanaman').fetchall()
    conn.close()
    
    # Mengelompokkan buku berdasarkan jenis_tanaman
    kategori_buku = {}
    for buku in semua_buku:
        kategori = buku['jenis_tanaman']
        if kategori not in kategori_buku:
            kategori_buku[kategori] = []
        kategori_buku[kategori].append(buku)
    
    return render_template('index.html', kategori_buku=kategori_buku)

@app.route('/buku/<int:buku_id>')
def baca_buku(buku_id):
    conn = get_db_connection()
    buku = conn.execute('SELECT * FROM tanaman WHERE id = ?', (buku_id,)).fetchone()
    conn.close()
    
    if buku is None:
        return "Buku tanaman tidak ditemukan", 404
        
    return render_template('detail.html', buku=buku)

if __name__ == '__main__':
    app.run(debug=True)