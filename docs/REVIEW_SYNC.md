# Code Review: Sync Protocol Implementation (v0.1)

**Tarih:** 13 Nisan 2026
**Branch:** `feat/sync`
**Gözden Geçiren:** Gemini CLI (Sparring Partner)

## 1. Mimari Değerlendirme (Zen & SoC)

Senkronizasyon mekanizması, "Sync at Home" (LAN/SSID) kısıtlamasından kurtularak daha esnek bir **JSON over HTTP/Stdin** protokolüne evrilmiş. Bu, projenin platform bağımsızlığı (Zen-Agnostic) ilkesiyle tam örtüşüyor.

### Başarılar:
- **Zero-Dependency Transport:** `HttpTransport` içinde `urllib.request` kullanımı, harici kütüphane bağımlılığını (requests vb.) ortadan kaldırarak "sıfır sürtünme" vaadini koruyor.
- **Identity Management:** `EntryData` içinde `source_file` + `timestamp` ikilisinin doğal anahtar (natural key) olarak kullanılması, cihazlar arası değişken ID sorununu (renormalization) zarifçe çözüyor.
- **Secrets:** Şifrelenmiş verilerin (secrets) sunucu tarafından çözülemeden (opaque blob) taşınması, gizlilik ve AI entegrasyonu (ZEN-AI-PARITY) dengesini mükemmel kurmuş.

## 2. Kritik Riskler ve Hatalar

### A. Veri Kaybı Riski (Conflict Resolution)
Mevcut `SyncServer._upsert_entry` implementasyonu, gelen her push isteğini "sorgusuz sualsiz" kabul ediyor.
- **Risk:** Sunucu tarafında bir `modification_timestamp` kontrolü yok. Eğer telefondaki veri eskiyse (henüz pull yapılmamışsa), push edildiğinde desktop'taki daha güncel veriyi ezebilir.
- **Senaryo:** Hafta sonu mobilden atılan not, pazartesi sabahı desktop'ta güncellenmişse; telefonun ilk sync denemesi desktop'taki güncel halini silebilir.

### B. Eksik Sync Log Hook'ları (En Önemli Teknik Borç)
Senkronizasyonun "delta" çalışmasını sağlayan `sync_log` tablosuna sadece `database.add_entry` metodu yazıyor.
- **Hata:** `KaydetService` içindeki `update_entry` ve `delete_entry` metodları `sync_log` tablosuna kayıt atmıyor.
- **Sonuç:** Bir kaydın güncellenmesi veya silinmesi diğer cihazlara asla ulaşmayacak. Sistem şu an sadece "Yeni Kayıt" (Create-only) senkronizasyonu yapıyor.

### C. UI/CLI Bağımlılığı (SoC İhlali)
`SyncClient` ve `SyncServer`, `KaydetService` yerine doğrudan `cli.py`, `commands.add` ve veritabanı cursor'larına bağımlı.
- **Eleştiri:** Bu durum, servis katmanının (Service Layer) amacını zayıflatıyor. Yarın bir gün SQLite yerine başka bir indeksleme gelirse, senkronizasyon kodunun da baştan yazılması gerekecek.

## 3. Kod Kalitesi (Arrow Anti-Pattern)

- **Protokol Ayrıştırma:** `sync_protocol.py` içindeki `_from_dict` metodu "if-else" yığılmasına sahip. Bu, "Ok Anti-Deseni"ne davetiye çıkarıyor.
- **Hata Yönetimi:** `SyncTransport` katmanında ağ hataları (401 Unauthorized, 500 Server Error) için spesifik yakalamalar yok. `urllib` hataları client'ın beklenmedik şekilde çökmesine (crash) neden olabilir.

## 4. İyileştirme Önerileri (Yol Haritası)

1. **Versiyonlama:** `EntryData` ve veritabanı şemasına `updated_at` (float/ISO string) eklenmeli. Sunucu, sadece daha yeni olan veriyi kabul etmeli.
2. **Hook Tamamlama:** `database.log_sync_action` çağrısı, `edit` ve `delete` operasyonlarının sonuna (aynı transaction içinde) eklenmeli.
3. **Service Layer Refactoring:** `SyncClient` ve `SyncServer` sınıfları veritabanına doğrudan dokunmak yerine `KaydetService` metodlarını kullanmalı.
4. **Dispatcher Pattern:** `sync_protocol.py` içindeki manuel mapping, bir dispatcher sözlüğü (dict) ile modernize edilmeli.

---
**Karar:** Mevcut haliyle "Create-only" (sadece yeni kayıt ekleme) senkronizasyonu için başarılı bir MVP. Ancak güncelleme ve silme senkronizasyonu için yukarıdaki kritik eksikliklerin giderilmesi şart.
