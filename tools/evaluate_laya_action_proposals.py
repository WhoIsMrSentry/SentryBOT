#!/usr/bin/env python3
"""Offline-only calibration report for Laya typed action questions.

This tool runs model inference over fixed text examples. It never constructs a
ToolRegistry or calls a robot, gateway, Arduino, or action endpoint.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
from typing import Any, Dict, List

from modules.agent_core.services.laya_action_contract import (
    build_laya_action_proposal,
    get_laya_action_questions,
)


def _load_laya_agent() -> Any:
    # Keep parser-only evaluation usable without the optional Torch runtime.
    import laya
    return laya.load(_model_path(), device="cpu")
from modules.agent_core.services.laya_engine import LayaDecision, LayaEngine


CASES = (
    {"text": "Işıkları kırmızı yap", "target": "neopixel", "direct": True, "color": "red"},
    {"text": "Işıkları mavi yap", "target": "neopixel", "direct": True, "color": "blue"},
    {"text": "Işıkları yeşil yap", "target": "neopixel", "direct": True, "color": "green"},
    {"text": "Işıkları sarı yap", "target": "neopixel", "direct": True, "color": "yellow"},
    {"text": "Işıkları mor yap", "target": "neopixel", "direct": True, "color": "purple"},
    {"text": "Işıkları kapat", "target": "neopixel", "direct": True, "color": "off", "effect": "OFF", "emergency": False},
    {"text": "Işıkları sabit kırmızı yak", "target": "neopixel", "direct": True, "color": "red", "effect": "SOLID"},
    {"text": "Işıkları nefes efektiyle mavi yap", "target": "neopixel", "direct": True, "color": "blue", "effect": "BREATHE"},
    {"text": "Mavi rengi bana anlat", "target": "system2_chat", "direct": False, "color": "unspecified"},
    {"text": "Neden gökyüzü mavi?", "target": "system2_chat", "direct": False, "color": "unspecified"},
    {"text": "Işıkları ayarla", "target": "neopixel", "direct": True, "color": "unspecified"},
    {"text": "Kamerada ne görüyorsun?", "target": "camera", "direct": False, "color": "unspecified"},
    {"text": "Motorları acil durdur, çarpacaksın!", "target": "emergency_stop", "direct": True, "color": "unspecified", "emergency": True},
    {"text": "Dur hemen!", "target": "emergency_stop", "direct": True, "color": "unspecified", "emergency": True},
    # Additional Turkish paraphrases and negative controls. These are a broader
    # calibration set, not an independent held-out validation set.
    {"text": "LED'leri turuncu renge çevir", "target": "neopixel", "direct": True, "color": "orange"},
    {"text": "Robotun ışıkları beyaz olsun", "target": "neopixel", "direct": True, "color": "white"},
    {"text": "Işık rengini pembeye ayarla", "target": "neopixel", "direct": True, "color": "pink"},
    {"text": "Işıkları camgöbeği yap", "target": "neopixel", "direct": True, "color": "cyan"},
    {"text": "Işıkları turkuaz renkte yak", "target": "neopixel", "direct": True, "color": "teal"},
    {"text": "Işıklar magenta yansın", "target": "neopixel", "direct": True, "color": "magenta"},
    {"text": "LED'leri mor renkte yak", "target": "neopixel", "direct": True, "color": "purple"},
    {"text": "Işıkları yeşil renkte yak", "target": "neopixel", "direct": True, "color": "green"},
    {"text": "Işıkları söndür", "target": "neopixel", "direct": True, "color": "off", "effect": "OFF", "emergency": False},
    {"text": "LED ışıklarını kapalı duruma getir", "target": "neopixel", "direct": True, "color": "off", "effect": "OFF", "emergency": False},
    {"text": "Işıkları aç", "target": "neopixel", "direct": True, "color": "unspecified"},
    {"text": "Işıkları biraz kıs", "target": "neopixel", "direct": True, "color": "unspecified"},
    {"text": "Işık rengini değiştir", "target": "neopixel", "direct": True, "color": "unspecified"},
    {"text": "Kırmızı benim en sevdiğim renk", "target": "system2_chat", "direct": False, "color": "unspecified"},
    {"text": "Mavi rengin psikolojideki anlamı ne?", "target": "system2_chat", "direct": False, "color": "unspecified"},
    {"text": "Fotoğraftaki ışık ne renk?", "target": "camera", "direct": False, "color": "unspecified"},
    {"text": "Robotun ışıkları hakkında konuşalım", "target": "system2_chat", "direct": False, "color": "unspecified"},
    {"text": "Bana mor rengi tarif et", "target": "system2_chat", "direct": False, "color": "unspecified"},
)

# Separate, pre-labeled examples. Do not use these to select or rewrite question
# variants; report them only as a final comparison after calibration.
HOLDOUT_CASES = (
    {"text": "LED rengini turuncuya al", "color": "orange"},
    {"text": "Işıklar mor renkte parlasın", "color": "purple"},
    {"text": "Neon ışığı pembe olsun", "color": "pink"},
    {"text": "Işığı camgöbeğine ayarlayabilir misin?", "color": "cyan"},
    {"text": "Işık halkasını turkuaza çevir", "color": "teal"},
    {"text": "Ön LED'i macenta yak", "color": "magenta"},
    {"text": "Küçük ışığı sarı yapar mısın?", "color": "yellow"},
    {"text": "Işık şeridini beyaza ayarla", "color": "white"},
    {"text": "RGB ışıkları cyan yap", "color": "cyan"},
    {"text": "Işıkları kırmızıya çevirir misin?", "color": "red"},
    {"text": "Bütün ışıkları maviye ayarlasana", "color": "blue"},
    {"text": "LED'leri yeşile boya", "color": "green"},
    {"text": "Lambaları turuncuya çevirir misin?", "color": "orange"},
    {"text": "Işık rengini mora getir", "color": "purple"},
    {"text": "Işıkları kapalı yap", "color": "off"},
    {"text": "LED'i söndür", "color": "off"},
    {"text": "Robot ışıklarını açabilir misin?", "color": "unspecified"},
    {"text": "LED efektini nefes yap", "color": "unspecified"},
    {"text": "Bu ışık çok parlak", "color": "unspecified"},
    {"text": "Fotoğrafta kırmızı ışık var mı?", "color": "unspecified"},
    {"text": "LED kırmızı yanıyor mu?", "color": "unspecified"},
    {"text": "Mavi ışığı seviyorum", "color": "unspecified"},
    {"text": "Rengi kırmızı yapma", "color": "unspecified"},
    {"text": "Sence LED'leri kırmızı mı yapsam?", "color": "unspecified"},
    {"text": "Robotun gözleri kırmızı olsun", "color": "unspecified"},
    {"text": "Işıklar kapalı kalsın", "color": "off"},
    {"text": "Lütfen ışıkları kapatır mısın?", "color": "off"},
    {"text": "Işık söndü", "color": "unspecified"},
    {"text": "Mavi renkli LED nasıl görünür?", "color": "unspecified"},
    {"text": "Işıkları kırmızı yapmak güvenli mi?", "color": "unspecified"},
)

# Additional parser-development examples; scores on these are not final.
RULE_DEV_CASES = (
    {"text": "Öndeki ışıkları kırmızı renge ayarla", "color": "red"},
    {"text": "Sağ LED'i yeşil yap", "color": "green"},
    {"text": "Işık barını maviye boya", "color": "blue"},
    {"text": "LED lambayı sarıya çevir", "color": "yellow"},
    {"text": "Işıkları turuncu yak", "color": "orange"},
    {"text": "Üst ışık mor olsun", "color": "purple"},
    {"text": "LED ışığını pembeye ayarla", "color": "pink"},
    {"text": "Arka lambaları beyaz yap", "color": "white"},
    {"text": "Işık halkasını camgöbeği yap", "color": "cyan"},
    {"text": "Şeridi turkuaz renkte ayarla", "color": "teal"},
    {"text": "RGB LED'leri magenta yak", "color": "magenta"},
    {"text": "Işık halkasını kapalı hale getir", "color": "off"},
    {"text": "Tüm LED lambaları söndür", "color": "off"},
    {"text": "Lütfen ışıkları kapatır mısın?", "color": "off"},
    {"text": "Yukarıdaki kırmızı LED yanıp sönüyor", "color": "unspecified"},
    {"text": "Yeşil ışık yanıyor", "color": "unspecified"},
    {"text": "LED rengini değiştirmek için ne yapmalıyım?", "color": "unspecified"},
    {"text": "Fotoğrafın solunda sarı bir lamba görüyorum", "color": "unspecified"},
    {"text": "Işıkları yakmalı mıyım?", "color": "unspecified"},
    {"text": "LED'leri kırmızıya çevirmek zor mu?", "color": "unspecified"},
    {"text": "RGB standardı nedir?", "color": "unspecified"},
    {"text": "Turkuaz ile teal aynı renk mi?", "color": "unspecified"},
    {"text": "LED'i mavi yapmıştık", "color": "unspecified"},
    {"text": "Rengi sarı olan lamba hangisi?", "color": "unspecified"},
    {"text": "Kapalı LED daha iyi mi?", "color": "unspecified"},
    {"text": "Bu cihazın ışıkları kapandı", "color": "unspecified"},
    {"text": "Yarın ışıkları kırmızı yapsak mı?", "color": "unspecified"},
    {"text": "Robot gözlerini yeşil yap", "color": "unspecified"},
    {"text": "Neon ışığı turuncu yanıyor gibi", "color": "unspecified"},
    {"text": "LED'lerin rengi neden kırmızı?", "color": "unspecified"},
)

# Final untouched set. Freeze both the prompt variants and rule baseline before
# evaluating this split.
FINAL_HOLDOUT_CASES = (
    {"text": "Panel LED'lerini kırmızıya ayarla", "color": "red"},
    {"text": "Öndeki ışık yeşil renge dönsün", "color": "green"},
    {"text": "LED halkasını maviye çevir", "color": "blue"},
    {"text": "İkaz lambasını sarı yap", "color": "yellow"},
    {"text": "Robotun durum ışığını turuncu renge getir", "color": "orange"},
    {"text": "Üst göstergedeki ışık mor olsun", "color": "purple"},
    {"text": "Yan ışıklara pembe renk ver", "color": "pink"},
    {"text": "LED şeridinde beyazı seç", "color": "white"},
    {"text": "RGB bandını camgöbeğine ayarla", "color": "cyan"},
    {"text": "LED halkasını turkuaz yap", "color": "teal"},
    {"text": "Ön uyarı LED'ini magenta yak", "color": "magenta"},
    {"text": "Alt aydınlatmayı kapat", "color": "off"},
    {"text": "Panel ışığını söndür", "color": "off"},
    {"text": "Yan LED'leri kapalı hale getir", "color": "off"},
    {"text": "Paneldeki kırmızı gösterge yanıyor", "color": "unspecified"},
    {"text": "LED'in yeşil renkte olduğunu görüyorum", "color": "unspecified"},
    {"text": "Kırmızı ışık yandığında ne anlama gelir?", "color": "unspecified"},
    {"text": "Geçen hafta LED'i mavi yapmıştım", "color": "unspecified"},
    {"text": "Yarın ışıkları sarı yapsak mı?", "color": "unspecified"},
    {"text": "LED'ler turuncu yanıyor", "color": "unspecified"},
    {"text": "RGB ışıkta cyan rengi güzel duruyor", "color": "unspecified"},
    {"text": "Hangi renk ışıkları var?", "color": "unspecified"},
    {"text": "LED şeridi pembe olabilir mi?", "color": "unspecified"},
    {"text": "Masa lambası maviye dönmüş", "color": "unspecified"},
    {"text": "Mor LED'leri seviyorum", "color": "unspecified"},
    {"text": "Bu ışık beyaz değil", "color": "unspecified"},
    {"text": "Işıklar açık kalsın", "color": "unspecified"},
    {"text": "Aydınlatmayı azalt", "color": "unspecified"},
    {"text": "Göstergedeki sarı renk hata mı?", "color": "unspecified"},
    {"text": "RGB nedir?", "color": "unspecified"},
)

# Separate intent/safety split; expected labels are fixed before model inference.
INTENT_HOLDOUT_CASES = (
    {"text": "LED'leri yeşil yap", "target": "neopixel", "direct": True, "urgent": False, "emergency": False},
    {"text": "Sabit kırmızı LED animasyonunu etkinleştir", "target": "neopixel", "direct": True, "urgent": False, "emergency": False, "effect": "SOLID"},
    {"text": "Işıklar mavi nefes efektiyle yansın", "target": "neopixel", "direct": True, "urgent": False, "emergency": False, "effect": "BREATHE"},
    {"text": "Mor renkte nabız efekti uygula", "target": "neopixel", "direct": True, "urgent": False, "emergency": False, "effect": "PULSE"},
    {"text": "RGB ışık sistemini tamamen söndür", "target": "neopixel", "direct": True, "urgent": False, "emergency": False, "effect": "OFF"},
    {"text": "Başını sağa çevir", "target": "arduino_serial", "direct": True, "urgent": False, "emergency": False},
    {"text": "Pan kafayı aşağı indir", "target": "arduino_serial", "direct": True, "urgent": False, "emergency": False},
    {"text": "İleri doğru yürü", "target": "arduino_serial", "direct": True, "urgent": False, "emergency": False},
    {"text": "Motor hızını yavaşlat", "target": "arduino_serial", "direct": True, "urgent": False, "emergency": False},
    {"text": "Robotu 30 santim ileri sür", "target": "arduino_serial", "direct": True, "urgent": False, "emergency": False},
    {"text": "Motorları hemen durdur, önünde engel var!", "target": "emergency_stop", "direct": True, "urgent": True, "emergency": True},
    {"text": "Dur, düşeceksin!", "target": "emergency_stop", "direct": True, "urgent": True, "emergency": True},
    {"text": "Çarpışmayı önlemek için anında frenle!", "target": "emergency_stop", "direct": True, "urgent": True, "emergency": True},
    {"text": "Robotu acil olarak kapat!", "target": "emergency_stop", "direct": True, "urgent": True, "emergency": True},
    {"text": "Tehlike var, derhal hareketi kes!", "target": "emergency_stop", "direct": True, "urgent": True, "emergency": True},
    {"text": "Robot, 'Merhaba' de", "target": "speak", "direct": True, "urgent": False, "emergency": False},
    {"text": "Bana yüksek sesle günaydın söyle", "target": "speak", "direct": True, "urgent": False, "emergency": False},
    {"text": "Bir uyarı sesi çıkar", "target": "speak", "direct": True, "urgent": False, "emergency": False},
    {"text": "Adımı sesli olarak oku", "target": "speak", "direct": True, "urgent": False, "emergency": False},
    {"text": "Alarm sesi çal", "target": "speak", "direct": True, "urgent": False, "emergency": False},
    {"text": "Kamerayı aç ve önüne bak", "target": "camera", "direct": True, "urgent": False, "emergency": False},
    {"text": "Etrafına bak", "target": "camera", "direct": True, "urgent": False, "emergency": False},
    {"text": "Önünde ne görüyorsun?", "target": "camera", "direct": False, "urgent": False, "emergency": False},
    {"text": "Masadaki nesneyi kameradan tanı", "target": "camera", "direct": True, "urgent": False, "emergency": False},
    {"text": "Fotoğrafta kaç kişi var?", "target": "camera", "direct": False, "urgent": False, "emergency": False},
    {"text": "Yer çekimi nasıl çalışır?", "target": "system2_chat", "direct": False, "urgent": False, "emergency": False},
    {"text": "Bir uzay macerası hikayesi anlat", "target": "system2_chat", "direct": False, "urgent": False, "emergency": False},
    {"text": "Yarın için bana çalışma planı öner", "target": "system2_chat", "direct": False, "urgent": False, "emergency": False},
    {"text": "Merhaba, bugün keyfin nasıl?", "target": "system2_chat", "direct": False, "urgent": False, "emergency": False},
    {"text": "İki seçenek arasındaki farkı açıkla", "target": "system2_chat", "direct": False, "urgent": False, "emergency": False},
)

# New calibration-only split for the next target/urgency/effect iteration.
INTENT_DEV_CASES = (
    {"text": "LED rengini sarıya çek", "target": "neopixel", "direct": True, "urgent": False, "emergency": False},
    {"text": "Turkuaz ışık animasyonunu darbeli çalıştır", "target": "neopixel", "direct": True, "urgent": False, "emergency": False, "effect": "PULSE"},
    {"text": "LED'leri dalga animasyonuna al", "target": "neopixel", "direct": True, "urgent": False, "emergency": False, "effect": "WAVE"},
    {"text": "Şerit ışığını rastgele kırpışma efektiyle çalıştır", "target": "neopixel", "direct": True, "urgent": False, "emergency": False, "effect": "RANDOM_BLINK"},
    {"text": "Işığı beyaz yap ve sabit tut", "target": "neopixel", "direct": True, "urgent": False, "emergency": False, "effect": "SOLID"},
    {"text": "Kafayı sola doğru döndür", "target": "arduino_serial", "direct": True, "urgent": False, "emergency": False},
    {"text": "Robotu yavaşça geri yürüt", "target": "arduino_serial", "direct": True, "urgent": False, "emergency": False},
    {"text": "Pan motorunu on beş derece kaldır", "target": "arduino_serial", "direct": True, "urgent": False, "emergency": False},
    {"text": "Yürüyüşü başlat", "target": "arduino_serial", "direct": True, "urgent": False, "emergency": False},
    {"text": "Başını öne eğ", "target": "arduino_serial", "direct": True, "urgent": False, "emergency": False},
    {"text": "Önündeki duvara çarpacaksın, hemen dur!", "target": "emergency_stop", "direct": True, "urgent": True, "emergency": True},
    {"text": "Motorları anında kes, devriliyor!", "target": "emergency_stop", "direct": True, "urgent": True, "emergency": True},
    {"text": "Dur! Uçurumun kenarındasın!", "target": "emergency_stop", "direct": True, "urgent": True, "emergency": True},
    {"text": "Acil stop, robot!", "target": "emergency_stop", "direct": True, "urgent": True, "emergency": True},
    {"text": "Çarpışma riski var, hareketi hemen durdur!", "target": "emergency_stop", "direct": True, "urgent": True, "emergency": True},
    {"text": "Şunu yüksek sesle oku: sistem hazır", "target": "speak", "direct": True, "urgent": False, "emergency": False},
    {"text": "Kısa bir bip sesi çıkar", "target": "speak", "direct": True, "urgent": False, "emergency": False},
    {"text": "Neşeli bir melodi çal", "target": "speak", "direct": True, "urgent": False, "emergency": False},
    {"text": "Sessiz kal", "target": "speak", "direct": True, "urgent": False, "emergency": False},
    {"text": "Komutu sesli olarak tekrar et", "target": "speak", "direct": True, "urgent": False, "emergency": False},
    {"text": "Kameradan masayı tara", "target": "camera", "direct": True, "urgent": False, "emergency": False},
    {"text": "Solunda kim var?", "target": "camera", "direct": False, "urgent": False, "emergency": False},
    {"text": "Görüntüdeki rengi tespit et", "target": "camera", "direct": True, "urgent": False, "emergency": False},
    {"text": "Kamerayı kapat", "target": "camera", "direct": True, "urgent": False, "emergency": False},
    {"text": "Çevrende bir kedi var mı?", "target": "camera", "direct": False, "urgent": False, "emergency": False},
    {"text": "Motor komutlarının Arduino tarafındaki rolü nedir?", "target": "system2_chat", "direct": False, "urgent": False, "emergency": False},
    {"text": "LED renkleri hakkında kısa bir bilgi ver", "target": "system2_chat", "direct": False, "urgent": False, "emergency": False},
    {"text": "Bir robota konuşmayı öğretmek zor mu?", "target": "system2_chat", "direct": False, "urgent": False, "emergency": False},
    {"text": "SentryBOT için üç isim öner", "target": "system2_chat", "direct": False, "urgent": False, "emergency": False},
    {"text": "Tehlikeli durumlarda robotlar nasıl tepki vermeli?", "target": "system2_chat", "direct": False, "urgent": False, "emergency": False},
)


# Frozen-rule, evaluator-only audio holdout; do not use for parser tuning.
AUDIO_HOLDOUT_CASES = (
    {"text": "Robot, şu notu sesli oku", "speak": True},
    {"text": "Bir kez bip sesi ver", "speak": True},
    {"text": "Kısa bir alarm çal", "speak": True},
    {"text": "Bana bir türkü söyle", "speak": True},
    {"text": "Şimdi konuş ve kendini tanıt", "speak": True},
    {"text": "Bu cümleyi aynen tekrar et: test başarılı", "speak": True},
    {"text": "Lütfen sessiz kal", "speak": True},
    {"text": "İstiklal Marşı'nı sesli oku", "speak": True},
    {"text": "Robotlar neden bip sesi çıkarır?", "speak": False},
    {"text": "Alarm sesi gece beni uyandırdı", "speak": False},
    {"text": "Dün bana bir şarkı söyledi", "speak": False},
    {"text": "Konuşma sentezi nasıl çalışıyor?", "speak": False},
    {"text": "Sessiz kalmak bazen iyidir", "speak": False},
    {"text": "'Yardım et' sözünü İngilizceye çevir", "speak": False},
    {"text": "Sesli okuma özelliği var mı?", "speak": False},
    {"text": "Bir melodi çalmak için hangi donanım gerekir?", "speak": False},
    {"text": "Az önce ne söyledin?", "speak": False},
    {"text": "Robotun sesi çok yüksek", "speak": False},
    {"text": "Bana sesli komut örnekleri ver", "speak": False},
    {"text": "Bu alarmı kim çalmış?", "speak": False},
    {"text": "Şarkı söylemeyi seviyor musun?", "speak": False},
    {"text": "Konuşma tanıma ile metin tanıma arasındaki fark ne?", "speak": False},
    {"text": "Biraz önce sessiz kaldı", "speak": False},
    {"text": "Müzik çalar bozulmuş", "speak": False},
    {"text": "Yüksek ses insanı rahatsız edebilir", "speak": False},
    {"text": "Bip sesi dosyasını nerede bulurum?", "speak": False},
    {"text": "Dün okuduğun metni hatırlıyor musun?", "speak": False},
    {"text": "Bana kısa bir hikâye anlat", "speak": False},
    {"text": "Robotun neden konuşmadığını açıkla", "speak": False},
    {"text": "Alarmı kapattım ama sesi sürüyor", "speak": False},
)

if (
    {case["text"] for case in CASES}
    | {case["text"] for case in HOLDOUT_CASES}
    | {case["text"] for case in RULE_DEV_CASES}
    | {case["text"] for case in FINAL_HOLDOUT_CASES}
    | {case["text"] for case in INTENT_HOLDOUT_CASES}
    | {case["text"] for case in AUDIO_HOLDOUT_CASES}
) & {
    case["text"] for case in INTENT_DEV_CASES
}:
    raise RuntimeError("Intent development examples must be disjoint from calibration and holdout sets.")


def _rule_based_color(text: str) -> str:
    """Conservative evaluator-only baseline; abstain unless intent is explicit."""
    # Turkish uppercase I is dotless ı; normalize it before Unicode casefolding.
    normalized = str(text or "").replace("I", "ı").casefold()
    has_light = re.search(r"\b(?:ışık\w*|ışığ\w*|lamba\w*|led\w*|neon\w*|rgb|aydınlat\w*)\b", normalized)
    has_action = re.search(
        r"\b(?:yap\w*|ayarla\w*|yak\w*|parla\w*|çevir\w*|getir\w*|al\w*|"
        r"boya\w*|ver\w*|seç\w*|olsun|kapat\w*|söndür\w*|sönük\w*|kapalı\s+(?:kalsın|yap|hale\s+getir))\b",
        normalized,
    )
    if not has_light or not has_action:
        return "unspecified"
    if re.search(
        r"\b(?:yapma|istemiyorum|istemem|olmasın|sence|acaba|yapsam|yapayım|"
        r"yapmalı\s+mıyım|yapsak|yapmış\w*|ayarlamış\w*|çevirmiş\w*|"
        r"gerekir\s+mi|güvenli\s+mi)\b",
        normalized,
    ):
        return "unspecified"

    colors = {
        "red": r"\bkırmızı\w*\b",
        "green": r"\byeşil\w*\b",
        "blue": r"\bmavi\w*\b",
        "yellow": r"\bsarı\w*\b",
        "orange": r"\bturuncu\w*\b",
        "purple": r"\bmor\w*\b",
        "pink": r"\bpembe\w*\b",
        "cyan": r"\b(?:camgöbeği|camgöbeğine|cyan)\b",
        "teal": r"\b(?:turkuaz\w*|teal)\b",
        "magenta": r"\b(?:macenta\w*|magenta)\b",
        "white": r"\bbeyaz\w*\b",
    }
    matches = [choice for choice, pattern in colors.items() if re.search(pattern, normalized)]
    wants_off = bool(re.search(
        r"\b(?:kapat\w*|söndür\w*|sönük\w*|kapalı\s+(?:kalsın|yap|hale\s+getir))\b",
        normalized,
    ))
    if wants_off:
        return "off" if not matches else "unspecified"
    return matches[0] if len(matches) == 1 else "unspecified"


def _rule_based_explicit_audio(text: str) -> bool:
    """Evaluator-only parser for literal speech/sound commands; never dispatches."""
    normalized = str(text or "").replace("I", "ı").casefold()
    command_patterns = (
        r"\boku\b", r"\bokur musun\b", r"\bsöyle\b", r"\bsöyler misin\b",
        r"\bses çıkar\w*", r"\b(?:bip|alarm|melodi|şarkı) sesi?\s+(?:çal|ver|çıkar)\w*",
        r"\bmelodi çal\w*", r"\bşarkı söyle\w*", r"\bçal\b", r"\bkonuş\b",
        r"\btekrar et\b", r"\bsessiz kal\b",
        r"[\"'“][^\"'”]+[\"'”]\s+(?:de|diye söyle)\b",
    )
    return any(re.search(pattern, normalized) for pattern in command_patterns)


def _evaluate_audio_parser_cases(cases: Any) -> Dict[str, Any]:
    """Measure the frozen literal parser without loading Laya or invoking tools."""
    tp = fp = fn = tn = 0
    for case in cases:
        expected = bool(case["speak"])
        predicted = _rule_based_explicit_audio(case["text"])
        tp += expected and predicted
        fp += not expected and predicted
        fn += expected and not predicted
        tn += not expected and not predicted
    total = len(cases)
    return {
        "sample_count": total,
        "accuracy": round((tp + tn) / total, 3) if total else None,
        "precision": round(tp / (tp + fp), 3) if tp + fp else None,
        "recall": round(tp / (tp + fn), 3) if tp + fn else None,
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
    }


def _evaluate_holdout(agent: Any, cases: Any) -> Dict[str, Any]:
    variant_names = ("current", "tr_explicit", "en_explicit", "joint")
    totals = {name: 0 for name in variant_names}
    explicit_correct = {name: 0 for name in variant_names}
    explicit_accepted = {name: 0 for name in variant_names}
    explicit_accepted_correct = {name: 0 for name in variant_names}
    explicit_count = unspecified_count = 0
    unspecified_correct = {name: 0 for name in variant_names}
    unspecified_confident_fp = {name: 0 for name in variant_names}
    rule_correct = rule_explicit_correct = rule_unspecified_correct = 0

    for case in cases:
        expected = case["color"]
        answers = _answers_for(agent, case["text"])
        predictions = {
            "current": answers.get("action_color", {}),
            "tr_explicit": answers.get("action_color_tr_explicit", {}),
            "en_explicit": answers.get("action_color_en_explicit", {}),
            "joint": answers.get("action_lights_joint", {}),
        }
        for name, answer in predictions.items():
            choice = answer.get("choice")
            confidence = float(answer.get("confidence", 0.0))
            mapped_choice = choice
            if name == "joint":
                mapped_choice = "off" if choice == "turn_off" else (
                    choice[4:] if isinstance(choice, str) and choice.startswith("set_") else "unspecified"
                )
            totals[name] += mapped_choice == expected
            if expected == "unspecified":
                unspecified_correct[name] += mapped_choice == "unspecified"
                if mapped_choice != "unspecified" and confidence >= 0.85:
                    unspecified_confident_fp[name] += 1
            else:
                explicit_count += int(name == "current")
                is_correct = mapped_choice == expected
                explicit_correct[name] += is_correct
                if confidence >= 0.85:
                    explicit_accepted[name] += 1
                    explicit_accepted_correct[name] += is_correct
        if expected == "unspecified":
            unspecified_count += 1
        rule_choice = _rule_based_color(case["text"])
        rule_correct += rule_choice == expected
        if expected == "unspecified":
            rule_unspecified_correct += rule_choice == "unspecified"
        else:
            rule_explicit_correct += rule_choice == expected

    total = len(cases)
    return {
        "sample_count": total,
        "explicit_color_or_off_count": explicit_count,
        "unspecified_count": unspecified_count,
        "model_top_choice_accuracy": {name: round(value / total, 3) for name, value in totals.items()},
        "model_explicit_accuracy": {name: round(value / explicit_count, 3) for name, value in explicit_correct.items()},
        "model_explicit_confidence_coverage": {name: round(value / explicit_count, 3) for name, value in explicit_accepted.items()},
        "model_accepted_explicit_accuracy": {
            name: round(explicit_accepted_correct[name] / count, 3) if count else None
            for name, count in explicit_accepted.items()
        },
        "model_unspecified_specificity": {name: round(value / unspecified_count, 3) for name, value in unspecified_correct.items()},
        "model_unspecified_high_confidence_false_positives": unspecified_confident_fp,
        "rule_based_accuracy": round(rule_correct / total, 3),
        "rule_based_explicit_accuracy": round(rule_explicit_correct / explicit_count, 3),
        "rule_based_unspecified_specificity": round(rule_unspecified_correct / unspecified_count, 3),
    }


def _evaluate_intent_cases(agent: Any, cases: Any, *, selected_candidate_only: bool = False) -> Dict[str, Any]:
    engine = LayaEngine()
    total = len(cases)
    target_names = {
        "current": "target_module",
        "tr_explicit": "target_module_explicit",
    }
    if not selected_candidate_only:
        target_names["en_explicit"] = "target_module_en_explicit"
    target_stats = {
        name: {
            "correct": 0, "accepted": 0, "accepted_correct": 0,
            "by_class": {case["target"]: {"count": 0, "correct": 0} for case in cases},
            "emergency_correct": 0, "emergency_fp": 0, "emergency_fn": 0,
        }
        for name in target_names
    }
    direct_correct = direct_accepted = direct_accepted_correct = 0
    urgent_correct = urgent_fp = urgent_fn = 0
    audio_tp = audio_fp = audio_fn = audio_tn = 0
    rule_audio_tp = rule_audio_fp = rule_audio_fn = rule_audio_tn = 0
    audio_refiners = {
        threshold: {
            "correct": 0,
            "by_class": {case["target"]: {"count": 0, "correct": 0} for case in cases},
        }
        for threshold in (0.60, 0.80, 0.90)
    }
    effect_names = ("current",) if selected_candidate_only else ("current", "explicit")
    effect_stats = {name: {"count": 0, "correct": 0, "accepted": 0, "accepted_correct": 0}
                    for name in effect_names}

    for case in cases:
        answers = _answers_for(agent, case["text"], include_candidates=not selected_candidate_only)
        direct = answers.get("is_direct_command", {})
        urgency = answers.get("urgency", {})
        is_direct = direct.get("choice") == "direct_action"
        direct_confidence = float(direct.get("confidence", 0.0))
        urgency_score = float(urgency.get("score", urgency.get("value", 0.0)))
        urgency_confidence = float(urgency.get("confidence", 0.0))
        audio_answer = answers.get("explicit_audio_request", {})
        audio_confidence = float(audio_answer.get("confidence", 0.0))
        expected_audio = case["target"] == "speak"
        predicted_audio = audio_answer.get("choice") == "explicit_audio"
        audio_tp += predicted_audio and expected_audio
        audio_fp += predicted_audio and not expected_audio
        audio_fn += not predicted_audio and expected_audio
        audio_tn += not predicted_audio and not expected_audio
        rule_audio = _rule_based_explicit_audio(case["text"])
        rule_audio_tp += rule_audio and expected_audio
        rule_audio_fp += rule_audio and not expected_audio
        rule_audio_fn += not rule_audio and expected_audio
        rule_audio_tn += not rule_audio and not expected_audio

        for threshold, stats in audio_refiners.items():
            refined_target = answers.get("target_module", {}).get("choice")
            if audio_confidence >= threshold and refined_target in {"speak", "system2_chat"}:
                refined_target = "speak" if predicted_audio else "system2_chat"
            refined_correct = refined_target == case["target"]
            stats["correct"] += refined_correct
            stats["by_class"][case["target"]]["count"] += 1
            stats["by_class"][case["target"]]["correct"] += refined_correct
        direct_is_correct = is_direct == case["direct"]
        direct_correct += direct_is_correct
        if direct_confidence >= engine.confidence_threshold:
            direct_accepted += 1
            direct_accepted_correct += direct_is_correct

        urgent = (
            urgency_score >= engine.high_urgency_threshold
            and urgency_confidence >= engine.high_urgency_confidence_threshold
        )
        urgent_correct += urgent == case["urgent"]
        urgent_fp += urgent and not case["urgent"]
        urgent_fn += not urgent and case["urgent"]

        for name, answer_key in target_names.items():
            target = answers.get(answer_key, {})
            target_choice = target.get("choice")
            target_confidence = float(target.get("confidence", 0.0))
            correct = target_choice == case["target"]
            stats = target_stats[name]
            stats["correct"] += correct
            stats["by_class"][case["target"]]["count"] += 1
            stats["by_class"][case["target"]]["correct"] += correct
            if target_confidence >= engine.confidence_threshold:
                stats["accepted"] += 1
                stats["accepted_correct"] += correct

            decision = LayaDecision(
                target_module=str(target_choice or "system2_chat"),
                module_confidence=target_confidence,
                is_direct_command=is_direct,
                direct_confidence=direct_confidence,
                affective_event="neutral",
                affect_confidence=0.0,
                urgency_score=urgency_score,
                urgency_confidence=urgency_confidence,
                inference_ms=0.0,
                emergency_threshold=engine.emergency_threshold,
                emergency_target_confidence_threshold=engine.emergency_target_confidence_threshold,
                emergency_direct_confidence_threshold=engine.emergency_direct_confidence_threshold,
                emergency_urgency_confidence_threshold=engine.emergency_urgency_confidence_threshold,
            )
            emergency = decision.is_emergency
            stats["emergency_correct"] += emergency == case["emergency"]
            stats["emergency_fp"] += emergency and not case["emergency"]
            stats["emergency_fn"] += not emergency and case["emergency"]

        if "effect" in case:
            effect_answers = (("current", "action_effect"),) if selected_candidate_only else (
                ("current", "action_effect"), ("explicit", "action_effect_explicit")
            )
            for name, answer_key in effect_answers:
                answer = answers.get(answer_key, {})
                effect_stats[name]["count"] += 1
                correct = answer.get("choice") == case["effect"]
                effect_stats[name]["correct"] += correct
                if float(answer.get("confidence", 0.0)) >= 0.85:
                    effect_stats[name]["accepted"] += 1
                    effect_stats[name]["accepted_correct"] += correct

    return {
        "sample_count": total,
        "target_variants": {
            name: {
                "accuracy": round(stats["correct"] / total, 3),
                "accuracy_by_class": {
                    cls: round(values["correct"] / values["count"], 3)
                    for cls, values in stats["by_class"].items()
                },
                "confidence_coverage": round(stats["accepted"] / total, 3),
                "accepted_accuracy": round(stats["accepted_correct"] / stats["accepted"], 3) if stats["accepted"] else None,
                "emergency_accuracy": round(stats["emergency_correct"] / total, 3),
                "emergency_false_positives": stats["emergency_fp"],
                "emergency_false_negatives": stats["emergency_fn"],
            }
            for name, stats in target_stats.items()
        },
        "direct_accuracy": round(direct_correct / total, 3),
        "direct_confidence_coverage": round(direct_accepted / total, 3),
        "direct_accepted_accuracy": round(direct_accepted_correct / direct_accepted, 3) if direct_accepted else None,
        "explicit_audio_binary": {
            "accuracy": round((audio_tp + audio_tn) / total, 3),
            "precision": round(audio_tp / (audio_tp + audio_fp), 3) if audio_tp + audio_fp else None,
            "recall": round(audio_tp / (audio_tp + audio_fn), 3) if audio_tp + audio_fn else None,
            "false_positives": audio_fp,
            "false_negatives": audio_fn,
        },
        "rule_based_explicit_audio": {
            "accuracy": round((rule_audio_tp + rule_audio_tn) / total, 3),
            "precision": round(rule_audio_tp / (rule_audio_tp + rule_audio_fp), 3) if rule_audio_tp + rule_audio_fp else None,
            "recall": round(rule_audio_tp / (rule_audio_tp + rule_audio_fn), 3) if rule_audio_tp + rule_audio_fn else None,
            "false_positives": rule_audio_fp,
            "false_negatives": rule_audio_fn,
        },
        "speak_chat_refinement": {
            f"confidence_{threshold:.2f}": {
                "target_accuracy": round(stats["correct"] / total, 3),
                "accuracy_by_class": {
                    cls: round(values["correct"] / values["count"], 3)
                    for cls, values in stats["by_class"].items()
                },
            }
            for threshold, stats in audio_refiners.items()
        },
        "urgency_accuracy": round(urgent_correct / total, 3),
        "urgency_false_positives": urgent_fp,
        "urgency_false_negatives": urgent_fn,
        "effect_variants": {
            name: {
                "sample_count": stats["count"],
                "accuracy": round(stats["correct"] / stats["count"], 3) if stats["count"] else None,
                "confidence_coverage": round(stats["accepted"] / stats["count"], 3) if stats["count"] else None,
                "accepted_accuracy": round(stats["accepted_correct"] / stats["accepted"], 3) if stats["accepted"] else None,
            }
            for name, stats in effect_stats.items()
        },
    }


def _model_path() -> str:
    root = os.path.expanduser("~/.cache/huggingface/hub/models--convaiinnovations--laya/snapshots")
    candidates = glob.glob(os.path.join(root, "*", "multilingual"))
    for candidate in candidates:
        if os.path.isfile(os.path.join(candidate, "model.safetensors")):
            return candidate
    raise FileNotFoundError("Cached Laya multilingual model weights were not found.")


def _answers_for(agent: Any, text: str, *, include_candidates: bool = True) -> Dict[str, Any]:
    current_color = get_laya_action_questions()["action_color"]
    color_criteria = {
        "red": "kırmızı / red",
        "green": "yeşil / green",
        "blue": "mavi / blue",
        "yellow": "sarı / yellow",
        "orange": "turuncu / orange",
        "purple": "mor / purple",
        "pink": "pembe / pink",
        "cyan": "camgöbeği / cyan",
        "teal": "turkuaz / teal",
        "magenta": "macenta / magenta",
        "white": "beyaz / white",
        "off": "kapalı / off",
        "unspecified": "renk açıkça söylenmedi / no explicit color",
    }
    variants = {
        "target_module_explicit": {
            "type": "choice",
            "instructions": (
                "Sınıfı kullanıcının istediği sonuca göre seç. speak yalnız robotun açıkça ses üretmesi, "
                "belirli söz söylemesi veya ses çalması istenince seçilir. Genel sohbet, bilgi, tavsiye "
                "ve hikâye talepleri system2_chat'tir; yanıtın sesli verilecek olması bunu speak yapmaz. "
                "Kamera/görme istekleri camera, ışık/LED ayarı neopixel, hareket motor komutları "
                "arduino_serial, yakın tehlike veya hemen dur komutu emergency_stop'tur."
            ),
            "criteria": {
                "neopixel": "Açık ışık, LED, renk, parlaklık veya animasyon ayarı",
                "arduino_serial": "Açık kafa, pan/tilt, motor veya hareket komutu; acil değil",
                "emergency_stop": "Açık acil durdurma, yakın tehlike veya çarpışma riski",
                "speak": "Açık TTS/konuşma/ses/alarm üretme komutu",
                "camera": "Kamerayı kullanma, görme, bakma veya görüntüde nesne/yüz tanıma",
                "system2_chat": "Genel soru, diyalog, bilgi, tavsiye, açıklama veya hikâye; donanım eylemi yok",
            },
        },
        "target_module_en_explicit": {
            "type": "choice",
            "instructions": (
                "Choose the user's primary requested intent. Select speak only when the user explicitly asks "
                "the robot to say/read/sing words or produce/play a sound. General questions, conversation, "
                "advice, reasoning, and stories are system2_chat even if the answer will be spoken aloud. "
                "Visual observation is camera; light control is neopixel; movement is arduino_serial; "
                "immediate danger or stopping is emergency_stop."
            ),
            "criteria": {
                "neopixel": "Explicitly change robot LEDs, light color, brightness, or animation",
                "arduino_serial": "Explicit head, motor, pan/tilt, or movement command; not an emergency",
                "emergency_stop": "Explicit emergency stop, imminent danger, or collision risk",
                "speak": "Explicit request for audible speech, reading, singing, alarm, or sound playback",
                "camera": "Use camera, look, observe, or identify something in an image or scene",
                "system2_chat": "General chat, question, information, advice, reasoning, or story; no explicit hardware/audio action",
            },
        },
        "explicit_audio_request": {
            "type": "choice",
            "instructions": (
                "Kullanıcı robottan açıkça ses üretmesini mi istiyor? Yalnız konuş, oku, söyle, tekrar et, "
                "şarkı söyle veya alarm/bip çal gibi açık ses komutlarında evet seç. Genel soru, sohbet, "
                "tavsiye, açıklama veya hikâye isteği tek başına ses komutu değildir."
            ),
            "criteria": {
                "explicit_audio": "Robotun belirli söz, okuma, şarkı, alarm, bip veya başka bir ses üretmesi açıkça isteniyor",
                "no_explicit_audio": "Genel cevap, sohbet, tavsiye, açıklama veya hikâye; açık ses üretme komutu yok",
            },
        },
        "action_effect_explicit": {
            "type": "choice",
            "instructions": (
                "Yalnızca kullanıcının ışıklara uygulamak istediği animasyon efektini seç. "
                "Işık kapatma açıkça istenmişse OFF; efekt adı yoksa unspecified seç. "
                "Renk, ışık komutu olmayan metin veya genel aç/kıs isteği efekti belirlemez."
            ),
            "criteria": {
                **{
                    effect: f"Kullanıcının açıkça istediği {effect.lower()} ışık efekti"
                    for effect in ("COMET", "PULSE", "WAVE", "SOLID", "BREATHE", "RANDOM_BLINK", "TWINKLE", "OFF")
                },
                "unspecified": "Açıkça bir animasyon efekti veya kapatma isteği yok",
            },
        },
        "action_color_tr_explicit": {
            "type": "choice",
            "instructions": "Yalnızca robot ışıkları için kullanıcının açıkça istediği rengi seç. Işık komutu yoksa veya renk belirtilmediyse unspecified seç.",
            "criteria": color_criteria,
        },
        "action_color_en_explicit": {
            "type": "choice",
            "instructions": "Which exact color does the user explicitly ask the robot to set its lights to? Select unspecified if there is no light-setting command or no explicit color.",
            "criteria": color_criteria,
        },
        "action_lights_joint": {
            "type": "choice",
            "instructions": "Kullanıcının robot ışıkları için açıkça istediği tek eylemi seç. Işık komutu veya açık renk yoksa no_light_action seç.",
            "criteria": {
                **{
                    f"set_{color}": f"Robot ışıklarını {description} yap / set the robot lights to {color}"
                    for color, description in {
                        "red": "kırmızı", "green": "yeşil", "blue": "mavi", "yellow": "sarı",
                        "orange": "turuncu", "purple": "mor", "pink": "pembe", "cyan": "camgöbeği",
                        "teal": "turkuaz", "magenta": "macenta", "white": "beyaz",
                    }.items()
                },
                "turn_off": "Robot ışıklarını kapat / turn the robot lights off",
                "no_light_action": "Işık komutu yok veya açık renk belirtilmemiş / no light command or no explicit color",
            },
        },
    }
    if not include_candidates:
        # Frozen for the final comparison: production baseline plus the single
        # Turkish target candidate selected using development data.
        variants = {key: value for key, value in variants.items() if key == "target_module_explicit"}
    questions = {
        **LayaEngine.SENTRYBOT_QUESTIONS,
        **get_laya_action_questions(),
        **variants,
    }
    result = agent.system_one({"text": text}, questions)
    answers = result.get("answers") if isinstance(result, dict) else None
    return answers if isinstance(answers, dict) else {}


def evaluate(*, include_color_holdout: bool = True) -> Dict[str, Any]:
    agent = _load_laya_agent()
    gate_engine = LayaEngine()
    policy = {
        "enabled": True,
        "allowed_actions": ["set_lights"],
        "confidence_threshold": 0.85,
        "default_light_effect": "BREATHE",
    }
    rows: List[Dict[str, Any]] = []
    target_ok = direct_ok = color_ok = effect_ok = proposals = 0
    confident_target_ok = confident_direct_ok = 0
    confident_target_count = confident_direct_count = 0
    explicit_target_ok = {"tr": 0, "en": 0}
    explicit_target_accepted = {"tr": 0, "en": 0}
    explicit_target_accepted_ok = {"tr": 0, "en": 0}
    explicit_target_by_class = {
        name: {case["target"]: {"count": 0, "correct": 0} for case in CASES}
        for name in explicit_target_ok
    }
    color_variant_ok = {"current": 0, "tr_explicit": 0, "en_explicit": 0}
    color_variant_accepted = {"current": 0, "tr_explicit": 0, "en_explicit": 0}
    color_variant_accepted_ok = {"current": 0, "tr_explicit": 0, "en_explicit": 0}
    color_variant_unspecified_ok = {"current": 0, "tr_explicit": 0, "en_explicit": 0}
    color_variant_unspecified_confident_fp = {"current": 0, "tr_explicit": 0, "en_explicit": 0}
    unspecified_count = 0
    joint_total_ok = joint_explicit_ok = joint_explicit_accepted = 0
    joint_explicit_accepted_ok = joint_unspecified_ok = joint_confident_fp = 0
    emergency_ok = color_count = effect_count = 0
    explicit_effect_variant_ok = explicit_effect_variant_accepted = explicit_effect_variant_accepted_ok = 0

    for case in CASES:
        answers = _answers_for(agent, case["text"])
        target = answers.get("target_module", {})
        target_variants = {
            "tr": answers.get("target_module_explicit", {}),
            "en": answers.get("target_module_en_explicit", {}),
        }
        direct = answers.get("is_direct_command", {})
        urgency = answers.get("urgency", {})
        color = answers.get("action_color", {})
        effect = answers.get("action_effect", {})
        effect_explicit = answers.get("action_effect_explicit", {})
        joint = answers.get("action_lights_joint", {})
        target_choice = target.get("choice")
        direct_choice = direct.get("choice")
        actual_direct = direct_choice == "direct_action"
        target_ok += target_choice == case["target"]
        direct_ok += actual_direct == case["direct"]
        target_accepted = float(target.get("confidence", 0.0)) >= gate_engine.confidence_threshold
        direct_accepted = float(direct.get("confidence", 0.0)) >= gate_engine.confidence_threshold
        if target_accepted:
            confident_target_count += 1
            confident_target_ok += target_choice == case["target"]
        if direct_accepted:
            confident_direct_count += 1
            confident_direct_ok += actual_direct == case["direct"]
        for name, target_explicit in target_variants.items():
            is_correct = target_explicit.get("choice") == case["target"]
            explicit_target_ok[name] += is_correct
            class_metrics = explicit_target_by_class[name][case["target"]]
            class_metrics["count"] += 1
            class_metrics["correct"] += is_correct
            if float(target_explicit.get("confidence", 0.0)) >= gate_engine.confidence_threshold:
                explicit_target_accepted[name] += 1
                explicit_target_accepted_ok[name] += is_correct
        color_predictions = {
            "current": color,
            "tr_explicit": answers.get("action_color_tr_explicit", {}),
            "en_explicit": answers.get("action_color_en_explicit", {}),
        }
        if case["color"] != "unspecified":
            color_count += 1
            color_ok += color.get("choice") == case["color"]
            for name, prediction in color_predictions.items():
                is_correct = prediction.get("choice") == case["color"]
                color_variant_ok[name] += is_correct
                if float(prediction.get("confidence", 0.0)) >= policy["confidence_threshold"]:
                    color_variant_accepted[name] += 1
                    color_variant_accepted_ok[name] += is_correct
            expected_joint = "turn_off" if case["color"] == "off" else f"set_{case['color']}"
            joint_correct = joint.get("choice") == expected_joint
            joint_explicit_ok += joint_correct
            if float(joint.get("confidence", 0.0)) >= policy["confidence_threshold"]:
                joint_explicit_accepted += 1
                joint_explicit_accepted_ok += joint_correct
        else:
            unspecified_count += 1
            for name, prediction in color_predictions.items():
                color_variant_unspecified_ok[name] += prediction.get("choice") == "unspecified"
                if (
                    prediction.get("choice") != "unspecified"
                    and float(prediction.get("confidence", 0.0)) >= policy["confidence_threshold"]
                ):
                    color_variant_unspecified_confident_fp[name] += 1
            joint_unspecified_ok += joint.get("choice") == "no_light_action"
            if (
                joint.get("choice") != "no_light_action"
                and float(joint.get("confidence", 0.0)) >= policy["confidence_threshold"]
            ):
                joint_confident_fp += 1
        expected_joint = (
            "no_light_action"
            if case["color"] == "unspecified"
            else "turn_off" if case["color"] == "off" else f"set_{case['color']}"
        )
        joint_total_ok += joint.get("choice") == expected_joint
        if case.get("effect"):
            effect_count += 1
            effect_ok += effect.get("choice") == case["effect"]
            explicit_effect_variant_ok += effect_explicit.get("choice") == case["effect"]
            if float(effect_explicit.get("confidence", 0.0)) >= policy["confidence_threshold"]:
                explicit_effect_variant_accepted += 1
                explicit_effect_variant_accepted_ok += effect_explicit.get("choice") == case["effect"]

        decision = LayaDecision(
            target_module=str(target_choice or "system2_chat"),
            module_confidence=float(target.get("confidence", 0.0)),
            is_direct_command=actual_direct,
            direct_confidence=float(direct.get("confidence", 0.0)),
            affective_event="neutral",
            affect_confidence=0.0,
            urgency_score=float(urgency.get("score", 0.0)),
            urgency_confidence=float(urgency.get("confidence", 0.0)),
            inference_ms=0.0,
            emergency_threshold=gate_engine.emergency_threshold,
            emergency_target_confidence_threshold=gate_engine.emergency_target_confidence_threshold,
            emergency_direct_confidence_threshold=gate_engine.emergency_direct_confidence_threshold,
            emergency_urgency_confidence_threshold=gate_engine.emergency_urgency_confidence_threshold,
        )
        proposal = build_laya_action_proposal(
            target_module=decision.target_module,
            module_confidence=decision.module_confidence,
            is_direct_command=decision.is_direct_command,
            direct_confidence=decision.direct_confidence,
            answers=answers,
            policy=policy,
        )
        proposals += proposal is not None
        emergency_ok += decision.is_emergency == case.get("emergency", False)
        rows.append({
            "text": case["text"],
            "expected": {k: case[k] for k in ("target", "direct", "color", "effect", "emergency") if k in case},
            "predicted": {
                "target": target_choice,
                "target_confidence": target.get("confidence"),
                "target_explicit_tr": target_variants["tr"].get("choice"),
                "target_explicit_tr_confidence": target_variants["tr"].get("confidence"),
                "target_explicit_en": target_variants["en"].get("choice"),
                "target_explicit_en_confidence": target_variants["en"].get("confidence"),
                "direct": direct_choice,
                "direct_confidence": direct.get("confidence"),
                "color": color.get("choice"),
                "color_confidence": color.get("confidence"),
                "color_tr_explicit": answers.get("action_color_tr_explicit", {}).get("choice"),
                "color_en_explicit": answers.get("action_color_en_explicit", {}).get("choice"),
                "joint_action": joint.get("choice"),
                "joint_confidence": joint.get("confidence"),
                "effect": effect.get("choice"),
                "effect_confidence": effect.get("confidence"),
                "effect_explicit": effect_explicit.get("choice"),
                "effect_explicit_confidence": effect_explicit.get("confidence"),
                "emergency": decision.is_emergency,
                "proposal_created": proposal is not None,
            },
        })

    total = len(CASES)
    report = {
        "model_path": _model_path(),
        "sample_count": total,
        "target_accuracy": round(target_ok / total, 3),
        "confident_target_coverage": round(confident_target_count / total, 3),
        "confident_target_accuracy": round(confident_target_ok / confident_target_count, 3) if confident_target_count else None,
        "explicit_target_accuracy": {name: round(value / total, 3) for name, value in explicit_target_ok.items()},
        "explicit_target_accuracy_by_class": {
            name: {
                cls: round(values["correct"] / values["count"], 3)
                for cls, values in classes.items()
            }
            for name, classes in explicit_target_by_class.items()
        },
        "explicit_target_confident_coverage": {
            name: round(value / total, 3) for name, value in explicit_target_accepted.items()
        },
        "explicit_target_accepted_accuracy": {
            name: round(explicit_target_accepted_ok[name] / count, 3) if count else None
            for name, count in explicit_target_accepted.items()
        },
        "direct_accuracy": round(direct_ok / total, 3),
        "confident_direct_coverage": round(confident_direct_count / total, 3),
        "confident_direct_accuracy": round(confident_direct_ok / confident_direct_count, 3) if confident_direct_count else None,
        "explicit_color_accuracy": round(color_ok / color_count, 3),
        "explicit_color_variant_accuracy": {
            name: round(count / color_count, 3)
            for name, count in color_variant_ok.items()
        },
        "explicit_color_confidence_coverage": {
            name: round(count / color_count, 3)
            for name, count in color_variant_accepted.items()
        },
        "accepted_explicit_color_accuracy": {
            name: round(color_variant_accepted_ok[name] / count, 3) if count else None
            for name, count in color_variant_accepted.items()
        },
        "unspecified_color_specificity": {
            name: round(count / unspecified_count, 3)
            for name, count in color_variant_unspecified_ok.items()
        },
        "unspecified_confident_false_positives": color_variant_unspecified_confident_fp,
        "joint_action_accuracy": round(joint_total_ok / total, 3),
        "joint_explicit_color_accuracy": round(joint_explicit_ok / color_count, 3),
        "joint_explicit_color_confidence_coverage": round(joint_explicit_accepted / color_count, 3),
        "joint_accepted_explicit_color_accuracy": round(joint_explicit_accepted_ok / joint_explicit_accepted, 3) if joint_explicit_accepted else None,
        "joint_no_color_specificity": round(joint_unspecified_ok / unspecified_count, 3),
        "joint_no_color_confident_false_positives": joint_confident_fp,
        "explicit_effect_accuracy": round(effect_ok / effect_count, 3),
        "explicit_effect_variant_accuracy": round(explicit_effect_variant_ok / effect_count, 3) if effect_count else None,
        "explicit_effect_variant_confidence_coverage": round(explicit_effect_variant_accepted / effect_count, 3) if effect_count else None,
        "explicit_effect_variant_accepted_accuracy": round(explicit_effect_variant_accepted_ok / explicit_effect_variant_accepted, 3) if explicit_effect_variant_accepted else None,
        "emergency_decision_accuracy": round(emergency_ok / total, 3),
        "proposals_created": proposals,
        "rows": rows,
    }
    if include_color_holdout:
        report["holdout"] = _evaluate_holdout(agent, HOLDOUT_CASES)
        report["holdout_note"] = "The rule baseline was adjusted after examining errors in HOLDOUT_CASES; its scores there are diagnostic, not independent validation."
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-only", action="store_true", help="Omit per-prompt rows.")
    parser.add_argument("--question-dev-only", action="store_true", help="Evaluate the existing calibration set only.")
    parser.add_argument("--final-holdout-only", action="store_true", help="Evaluate only the untouched final holdout.")
    parser.add_argument("--intent-holdout-only", action="store_true", help="Evaluate only target/direct/urgency/effect labels.")
    parser.add_argument("--intent-dev-only", action="store_true", help="Calibrate intent/effect prompts on the development split.")
    parser.add_argument("--audio-parser-holdout-only", action="store_true", help="Evaluate the frozen literal audio parser on its separate holdout; no model/tools are loaded.")
    args = parser.parse_args()
    if sum((args.final_holdout_only, args.intent_holdout_only, args.intent_dev_only, args.question_dev_only, args.audio_parser_holdout_only)) > 1:
        parser.error("Choose only one holdout-only mode.")
    if args.audio_parser_holdout_only:
        report = {
            "audio_parser_holdout": _evaluate_audio_parser_cases(AUDIO_HOLDOUT_CASES),
            "holdout_note": "Frozen evaluator-only literal parser; do not tune against this set. It has no hardware or tool dispatch path.",
        }
    elif args.intent_dev_only:
        agent = _load_laya_agent()
        report = {
            "model_path": _model_path(),
            "intent_development": _evaluate_intent_cases(agent, INTENT_DEV_CASES),
            "holdout_note": "Development split only. Use the separate intent holdout once after selecting a candidate.",
        }
    elif args.question_dev_only:
        report = evaluate(include_color_holdout=False)
        report.pop("rows", None)
    elif args.intent_holdout_only:
        agent = _load_laya_agent()
        report = {
            "model_path": _model_path(),
            "intent_holdout": _evaluate_intent_cases(agent, INTENT_HOLDOUT_CASES, selected_candidate_only=True),
            "holdout_note": "One frozen Turkish target candidate selected on development data is compared with baseline. Do not tune against this split.",
        }
    elif args.final_holdout_only:
        agent = _load_laya_agent()
        report = {
            "model_path": _model_path(),
            "holdout": _evaluate_holdout(agent, FINAL_HOLDOUT_CASES),
            "holdout_note": "This final set is disjoint from the calibration and parser-development examples. Do not tune the parser against it.",
        }
    else:
        report = evaluate()
        if args.summary_only:
            report.pop("rows", None)
    print(json.dumps(report, ensure_ascii=True, indent=2))
