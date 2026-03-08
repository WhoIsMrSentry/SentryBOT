# Guvenlik Politikasi

## Desteklenen Surumler
Guvenlik duzeltmeleri aktif gelistirme dali icin saglanir:

| Dal | Destek |
| --- | --- |
| `dev` | Evet |
| Diger dallar | Mumkun oldugunca |

## Zafiyet Bildirimi
Guvenlik aciklarini public issue olarak paylasmayin.

Bu depo icin GitHub private vulnerability reporting mekanizmasini kullanin.
Eger private bildirim kullanilamiyorsa, exploit detayi vermeden minimal bir issue acin ve bakimcidan guvenlik iletisimi talep edin.

Lutfen su bilgileri ekleyin:
- Etkilenen modul(ler) ve dosya yollari
- Yeniden uretim adimlari
- Beklenen ve gerceklesen davranis
- Etki degerlendirmesi
- Biliniyorsa gecici veya kalici oneri

## Yanit Hedefleri
- Ilk geri donus: 72 saat icinde
- Triage karari: 7 gun icinde
- Duzeltme zamanlamasi: ciddiyet ve donanim riski seviyesine gore

## Kapsam Notlari
SentryBOT, Raspberry Pi ve Arduino bilesenleri icerir.
Bildirimde etki alanini acikca belirtin:
- API/gateway davranisi
- Pi tarafi modul mantigi
- Arduino komut kontrati veya firmware etkilesimi
- Fiziksel guvenlik davranisi (hareket, guc, acil durdurma)

## Guvenli Test
Tehlikeli fiziksel testleri insanlara, hayvanlara veya hassas ekipmanlara yakin ortamlarda yapmayin.
Hareketle ilgili testlerde sinirli ortam ve acil durdurma hazirligi kullanin.
