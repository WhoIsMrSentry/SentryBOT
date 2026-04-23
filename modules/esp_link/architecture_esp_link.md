# architecture_esp_link

## Sorumluluk
`esp_link` modülü Pi tarafında ESP köprüsüne erişen hafif istemci katmanıdır.

## Akış
1. Üst modül (`arduino_serial`) komut payload'unu üretir.
2. `arduino_serial`, komutu ESP bridge HTTP endpointine iletir.
3. ESP bridge, komutu UART ile Mega'ya aktarır.
4. Mega NDJSON ACK/ERR döner.
5. ESP bridge cevabı HTTP JSON olarak Pi'ye geri iletir.

## Tasarım Kararları
- Komut şeması tek kaynak olarak `modules/arduino_serial/contract.py` kalır.
- Pi tarafında komut çağrıları değişmeden kalabilsin diye taşıma değişikliği `arduino_serial` içinde yapılır.
- `esp_link` modülü bağımsız sağlık kontrolü ve gerektiğinde doğrudan proxy sağlar.
