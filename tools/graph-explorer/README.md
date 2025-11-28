# Graph Explorer (Standalone)

Bu araç, SentryBOT deposunu **tarayıcıda** gezmek ve modüller arası ilişkileri görselleştirmek için tasarlanmış **tamamen istemci tarafı** bir HTML dosyasıdır.

**Yeni Özellikler:**
- **Tam Ekran:** Grafik artık tüm ekranı kaplar, sağ panel kaldırıldı.
- **Merkez Modu:** Gateway merkezde, modüller etrafında halka şeklinde, dosyalar ise dışarıya doğru "yıldız" (star) düzeninde sıralanır.
- **Modül Renkleri:** Üst çubuktaki modül isimlerine tıklayarak her modülün rengini kişiselleştirebilirsiniz.
- **Akıllı Sıralama:** Modüller, işlevsel kümelerine (AI, Donanım, Servis vb.) göre gruplanır.

## Kullanım

1. `tools/graph-explorer/index.html` dosyasını bir tarayıcıda açın.
2. **Veri Yükleme:**
   - Araç şu an **sentetik veri** ile çalışmaktadır (dosya sistemi erişimi olmadan demo modu).
   - Gerçek dosya yapısını görmek için `input type=file` (klasör seçme) özelliği eklenebilir veya `server.py` kullanılabilir.
3. **Kontroller (Üst Çubuk):**
   - **Hepsini Göster:** Tüm modülleri ve dosyalarını grafiğe ekler.
   - **Merkez Modu:** Düzenli, geometrik yerleşimi açar/kapatır.
   - **Sabit Modu:** Düğümleri sürükleyip bıraktığınız yerde sabitler.
   - **Sıfırla:** Grafiği temizler ve başlangıç durumuna döner.
4. **Renk Değiştirme:**
   - Üst bardaki modül ismine (örn. `ollama`) tıklayın.
   - Açılan renk seçiciden yeni rengi belirleyin.

## İpuçları
- **Merkez Modu** açıkken düğümleri sürükleyebilirsiniz; bıraktığınızda merkeze geri dönmeye çalışmazlar (sabitlenirler).
- Büyük grafiklerde performansı artırmak için gereksiz modülleri kapatın veya sayfayı yenileyin.

