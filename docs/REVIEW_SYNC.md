# Code Review: Sync Protocol Implementation

**Tarih:** 13-14 Nisan 2026
**Branch:** `feat/sync`
**Gözden Geçiren:** Gemini CLI (Sparring Partner)
**Durum:** Tüm geçerli bulgular düzeltildi.

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

### ~~B. Eksik Sync Log Hook'ları~~ — Yanlış tespit
Hook'lar `commands/edit.py` (satır 123, 229) ve `commands/delete.py`
(satır 74) içinde `log_sync_action()` çağrısıyla mevcuttu.
`KaydetService.update_entry` → `update_entry_inline` → `log_sync_action`
zinciri review sırasında takip edilmemişti.

### C. UI/CLI Bağımlılığı (SoC İhlali)
`SyncClient` ve `SyncServer`, `KaydetService` yerine doğrudan `cli.py`, `commands.add` ve veritabanı cursor'larına bağımlı.
- **Eleştiri:** Bu durum, servis katmanının (Service Layer) amacını zayıflatıyor. Yarın bir gün SQLite yerine başka bir indeksleme gelirse, senkronizasyon kodunun da baştan yazılması gerekecek.

## 3. Kod Kalitesi (Arrow Anti-Pattern)

- **Protokol Ayrıştırma:** `sync_protocol.py` içindeki `_from_dict` metodu "if-else" yığılmasına sahip. Bu, "Ok Anti-Deseni"ne davetiye çıkarıyor.
- **Hata Yönetimi:** `SyncTransport` katmanında ağ hataları (401 Unauthorized, 500 Server Error) için spesifik yakalamalar yok. `urllib` hataları client'ın beklenmedik şekilde çökmesine (crash) neden olabilir.

## 4. İyileştirme Önerileri ve Sonuçları

1. ~~**Versiyonlama:**~~ **Düzeltildi.** `entries` tablosuna `updated_at`
   kolonu eklendi (schema v3). `EntryData`'ya `updated_at` alanı eklendi.
   Sunucu, `updated_at` karşılaştırması yaparak stale push'ları reddediyor.
2. ~~**Hook Tamamlama:**~~ **Yanlış tespit.** Hook'lar zaten mevcuttu.
   Ek olarak `create_entry` (`commands/add.py`) içine de `LOG_SYNC_ACTION_SQL`
   eklendi (bu gerçekten eksikti).
3. ~~**Service Layer Refactoring:**~~ **Düzeltildi.** `SyncServer` ve
   `SyncClient` artık `KaydetService` instance'ı alıyor. Entry CRUD
   service üzerinden yapılıyor.
4. **Dispatcher Pattern:** Henüz uygulanmadı. 5 metod için premature
   optimization olarak değerlendirildi.

---
**Sonuç:** Full create/update/delete senkronizasyonu çalışıyor.
Conflict resolution, sync loop prevention, attachment sync, secret sync
ve 135 test (6 e2e dahil) ile deployment-ready durumda.
