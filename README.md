# Excel Sürüm Karşılaştırma

İki Excel sürümünü (eski / güncel) karşılaştırıp değişiklikleri yan yana ve Word'deki
"değişiklikleri izle" görünümünde gösteren Streamlit uygulaması.

## Kurulum ve çalıştırma

```bash
pip install -r requirements.txt
streamlit run app.py
```

Soldaki panelden eski ve güncel dosyaları yükleyin. Proje klasöründe `eskiprogram.xlsx` ve
`Guncelprogram.xlsx` varsa **Örnek dosyaları kullan** düğmesi de görünür.

## Nasıl karşılaştırır?

- **Sütunlar:** Başlıkları farklı olsa bile (ör. `KAZANIM/ÖĞRENME ÇIKTISI/BÖLÜM` → `BÖLÜM`) başlık ve içerik benzerliğine göre eşlenir. Eşlemeyi ve karşılaştırılacak sütunları "Sütun eşleme" bölümünden değiştirebilirsiniz.
- **Dersler:** Ders adına göre karşılıklı getirilir. Derslerin dosyadaki sırası farklı olabilir; bu durum taşıma sayılmaz.
- **Programlar:** Aynı ders içinde SIRA NO 1'e döndüğünde yeni bir program bloğu başlar. Bloklar içerik benzerliğine göre eşleşir. Karşılığı olmayan blok tamamen silinmiş (üstü çizili) ya da eklenmiş gösterilir.
- **Satırlar:** Kazanım kodu yok sayılarak (kodlar yeniden numaralanmış olabilir) anahtar sütun ve diğer sütunların benzerliğine göre en iyi eşleşme bulunur. Eşik altında kalanlar silinen veya eklenen satır olur.
- **Taşıma:** Bir satırın başka üniteye/temaya geçmesi ya da ünite içinde yerinin değişmesi. Ünite adının değişmesi (`1. YAŞAM` → `1. TEMA: YAŞAM`) taşıma değil, metin farkıdır.
- **Metin farkı:** Kelime düzeyinde gösterilir. Büyük/küçük harf ve noktalama farkları da metin farkıdır.
- **Biçim farkı:** Yalnızca boşluk veya alt+enter (satır sonu) farkıdır. Kenar çubuğundaki anahtarla yok sayılabilir ya da gösterilebilir.

## Çıktılar

- **Yan yana:** Eski ve güncel sürüm aynı hizada gösterilir. Çoklu filtre, arama, yazı boyutu, tam ekran ve sayfalama vardır.
- **Değişiklikleri izle raporu:** Tek tablodur. Eklenenler yeşil, silinenler kırmızı ve üstü çizilidir. Taşınan satırlar eski yerinde mor çift üstü çizili, yeni yerinde mor çift altı çizili görünür. Son sütunda satırdaki farklar özetlenir. Rapor **HTML** ve **PDF (A4 yatay)** olarak indirilebilir.

## Testler

```bash
python -m pytest -q
```
