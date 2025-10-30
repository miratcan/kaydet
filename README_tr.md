# Kaydet — Düşünceleriniz, Tek Komut Uzağınızda

[![PyPI versiyonu](https://img.shields.io/pypi/v/kaydet.svg)](https://pypi.org/project/kaydet/)
[![İndirmeler](https://img.shields.io/pypi/dm/kaydet.svg)](https://pypi.org/project/kaydet/)
[![Python](https://img.shields.io/pypi/pyversions/kaydet.svg)](https://pypi.org/project/kaydet/)
[![Lisans](https://img.shields.io/github/license/miratcan/kaydet.svg)](LICENSE)

> Toplantı bitti. Bir sonraki bildirim gelmeden önce on iki saniyeniz var.  
> `kaydet "Prod hatasını kapattım, cache TTL düzeltildi. #work"`  
> Not alındı. Akış bozulmadı.

Kaydet, sorgulanabilir kişisel veritabanınız—sıfır sürtünmeyle.
Okuduğunuz bir günlük değil, sorguladığınız bir veritabanı.
Düşünceler yakalayın, işleri takip edin, hayatı kaydedin—terminalinizden, düz metinde.

**[📥 Hemen Kurun](#kaydete-adım-atın)** • **[⚡ Hızlı Rehber](#günlük-araç-takımı)** • **[🤖 Yapay Zeka Eşlikçileri](#yapay-zeka-eşlikçileri-dinliyor)**

## Demo

Kaydet’in hareketini izleyin:

<a href="https://asciinema.org/a/Rlcc9GaTQEEfTlUIicvHxm8iC" target="_blank"><img src="https://asciinema.org/a/Rlcc9GaTQEEfTlUIicvHxm8iC.svg" /></a>

## Kaydet’e Adım Atın

Boş bir terminal, akıp giden bir düşünce, tek bir komut. Kaydet’in sizden istediği sadece bu.

### Yolunuzu Seçin

```bash
# GitHub'dan en güncel hâliyle
pip install git+https://github.com/miratcan/kaydet.git
```

```bash
# Araçlarınızı izole tutmak isterseniz
pipx install git+https://github.com/miratcan/kaydet.git
```

```bash
# Model Context Protocol desteğiyle yapay zekaya açılmak için
pip install "git+https://github.com/miratcan/kaydet.git#egg=kaydet[mcp]"
```

## Kaydet’i Farklı Kılan Nedir?

### Notion Ağırken
- Terminalden çıkmadan çalışırsınız. Pencere, farenin peşinden koşma yok.
- Girdiler düz metin dosyalarına iner; `git`, senkronizasyon ve `grep` sizin kontrolünüzdedir.

### Düz Metin Yalnızken
- Kaydet her kayıtta etiketleri, metaveriyi ve kelimeleri ayıklar; hepsini SQLite indeksine işler.
- Arama anlık ve naziktir: `kaydet --search "status:done project:kaydet"`.

### Günlük Uygulamaları Meraklıyken
- Tüm verileriniz diskinizde kalır. Telemetri yok, bilinmeyen sunucu yok.
- Editörü siz belirlersiniz: `vim`, `nvim`, `nano`, `code`… neyi çağırırsanız.

### Yapay Zeka Yoldaşınız Olsun İsterseniz
- Dahili MCP sunucusu arşivinizi Claude ve benzeri asistanlara açar.
- JSON çıktılar otomasyonlara ve betiklerinize hazır veri sağlar.

## Terminalden Sahneler

Kaydet, oynadığınız her rolü kaydeder. İşte birkaç sahne.

### 💼 Leyla’nın İş Günlüğü
Gönderiyor, ispatını saklıyor.

```bash
kaydet "Staging kimlik doğrulama hatası düzeltildi #work commit:38edf60 pr:76 status:done time:2h"
kaydet "Onboarding metinlerini güncelledim #kaydet status:wip project:kaydet"

# Sonra
kaydet --search commit:38edf60
kaydet --search "status:done project:kaydet"
```

### 📚 Umut’un TÖÖ Defteri
Öğrendiğini uzaklaştırmadan kaydeder.

```bash
kaydet "TÖÖ: pytest --cov-report=html taranabilir kapsam raporu üretir #til topic:testing stack:python"
kaydet --search "topic:testing"
```

### ⏱️ Defne’nin Odak Defteri
Her derin çalışma bloğunu zamanlar, haftasını veriler yönetir.

```bash
kaydet "Analitik ETL için derin çalışma #focus time:2.5h intensity:high project:analytics"
kaydet "Emre ile eşli çalışma #pair time:1.5h intensity:medium project:kaydet"

# Uzayan seansları bul
kaydet --search "time:>2"
```

### 💡 Efe’nin Fikir Bahçesi
İlhamı saklar, yarına bırakır.

```bash
kaydet "Şifrelenmiş dışa aktarma prototipi #idea area:security priority:high"
kaydet "Stripe geçiş rehberini okudum #research area:payments source:stripe-docs"

kaydet --search "area:security"
```

### 😊 Duru’nun Duygu Günlüğü
Hisleri bağlamıyla birlikte saklar, dönüp bakmayı kolaylaştırır.

```bash
kaydet "Sabah koşusu harikaydı #wellness mood:energized sleep:7h"
kaydet "Öğlen toplantı öncesi enerji düşüktü #mood mood:tired caffeine:2cups"

kaydet --search "mood:energized"
```

### 💰 Selim’in Masraf Notları
Fişleri ortaya çıkar çıkmaz kaydeder.

```bash
kaydet "Müşteri öğle yemeği #expense amount:650 currency:TRY client:bbrain billable:yes"
kaydet "Domain yenilemesi #expense amount:120 currency:USD project:kaydet billable:no"

kaydet --search "billable:yes"
```

## Hızlı Bakışta Öne Çıkanlar
- **Terminal yerlisi** – tek tuşla çağırın, `$EDITOR` tercihinize saygı duyar.
- **Düz metin güvencesi** – dayanıklı, senkronize edilebilir veri dosyaları.
- **Akıllı yapı** – etiket, metaveri ve sayılar otomatik indekslenir.
- **Nazik hatırlatmalar** – uzun süre yazmadığınızda isteğe bağlı uyarı.
- **Taşınabilir** – Python 3.10+ olan her yerde çalışır.

## Günlük Araç Takımı

```bash
# Bugüne hızlı bir not ekle
kaydet "Yan projede ilerleme var #coding time:3h"

# Hashtag ve metadata'yı tek string'de yaz
kaydet "Arkadaşlarla akşam yemeği #aile #şükran mood:mutlu"

# Sevdiğiniz editörde devam edin
kaydet --editor

# Arşiv klasörünü hemen açın
kaydet --folder

# Bakım
kaydet --tags             # etiket ve sayıları listele
kaydet --doctor           # dosyalara dokunduysanız indeksi yenile
kaydet --browse           # isteğe bağlı Textual tarayıcısını aç

# Arşivde avlanın
kaydet --search şükran
kaydet --search "status:done"
kaydet --search "time:>1"

# Geçmiş girdileri ID ile düzenle ya da sil (ID’ler arama sonucunda görünür)
kaydet --edit 42
kaydet --delete 42 --yes   # onay istemeden sil
```

> Etkileşimli gezinme arayüzü için `pip install "kaydet[browse]"` komutunu çalıştırın.

### İstatistikler Nasıl Görünür?

```
Eylül 2025
Pt Sa Ça Pe Cu Ct Pz
 1[  ]  2[  ]  3[  ]  4[  ]  5[  ]  6[  ]  7[  ]
 8[  ]  9[  ] 10[  ] 11[  ] 12[  ] 13[  ] 14[  ]
...
Bu ay toplam: 12 girdi
```

### Girdiler Nasıl Yazılır?

```
14:25 [132]: Senkronizasyon yardımcılarını refaktorettim. #focus
```

Her not, tarihle adlandırılmış bir dosyada (ör. `~/.kaydet/2024-02-19.txt`) yaşar. Kaydet dosyayı günceller, SQLite indeksini tazeler ve ID'leri sabit tutar—ister düzenleyin ister silin.

Satır içi hashtag'ler (`#aile`) ve metaveri (`project:work`, `time:45m`) birlikte saklanır. Arama her ikisini de kullanabilir.

## Kaydet’i Size Göre Ayarlayın

Kaydet ayarlarını `~/.config/kaydet/config.ini` dosyasına yazar (veya `XDG_CONFIG_HOME` ile tanımladığınız yere). İlk çalıştırmada dosya oluşur, sonrası size ait.

```ini
[SETTINGS]
DAY_FILE_PATTERN = %Y-%m-%d.txt
DAY_TITLE_PATTERN = %Y/%m/%d - %A
LOG_DIR = /Users/siz/.kaydet
EDITOR = nvim +'startinsert'
REMIND_AFTER_HOURS = 4
```

### Alan Notları
- İstediğiniz zaman `kaydet --editor` diyerek editörü zorlayabilirsiniz.
- `anahtar:değer` desenindeki her şey sorgulanabilir metaveridir (`kaydet --search "status:done"`).
- `2h`, `90m`, `3.5` gibi süreler sayısallaştırılır (`kaydet --search "time:>2"`).
- Satır içi ve açık etiketler aynı indeks altında birleşir (`kaydet --tags`).
- Dosyaları manuel değiştirdiniz mi? `kaydet --doctor` ID’leri onarır, arama tablolarını yeniler.

## Yapay Zeka Eşlikçileri Dinliyor

`kaydet-mcp` komutunu çalıştırın; asistanlarınız kişisel veritabanınızı sorgulasın. Artık şu araçlar mevcut:

- `add_entry` – yeni kaydın ID’si, dosya yolu ve zaman damgasını JSON olarak döner
- `update_entry`, `delete_entry` – editör açmadan düzenleme veya silme
- `search_entries`, `list_recent_entries`, `entries_by_tag`
- `list_tags`, `get_stats` (isteğe bağlı `year` / `month` parametreleriyle)

### Diyalog Örnekleri

#### 🔎 Sprint Retrosu
```
Sen: "Geçen sprint ne gönderdim?"

YZ: *#work girdilerini tarar*
"Sprint özeti:
- Analitik toplu işlemler dağıtıldı (commit 38edf60)
- Onboarding kopyası güncellendi (status:done)
- Auth hatası incelendi (status:wip)"
```

#### 📚 Öğrenme Güncesi
```
Sen: "Geçen ay test hakkında ne çalışmıştım?"

YZ: *topic:testing girdilerini süzer*
"Öne çıkanlar:
- Pytest kapsam bayrakları ve HTML raporu (3 Eylül)
- Hypothesis ile özelliğe dayalı test (11 Eylül)"
```

#### 💪 Fitness Nabzı
```
Sen: "Bu ay geçen aydan daha fazla mı spor yaptım?"

YZ: *#fitness girdilerini sayar*
"Bu ay: 18 girdi (haftalık ortalama 4,5)
Geçen ay: 12 girdi (haftalık ortalama 3)
%50 artış. En sık aktivite: koşu (8 girdi)."
```

#### 🎯 Üretkenlik Desenleri
```
Sen: "Çalışma alışkanlıklarımda ne görüyorsun?"

YZ: *etiket ve zaman damgalarını eşler*
"Gözlemler:
- En yüksek odak: 09:00–11:00
- Derin çalışma Salı/Perşembe günleri yoğun
- Hata düzeltmeleri öğleden sonra
- #frontend görevlerinde mola sıklığı artıyor"
```

#### 💼 Toplantı Takipleri
```
Sen: "Tasarım ekibi toplantılarından hangi işler çıktı?"

YZ: *#meeting #design girdilerini bulur*
"Altı toplantı kaydedildi. Açık işler:
- Dashboard renk paletini netleştir (5 Eylül)
- Mobil taslakları gözden geçir (12 Eylül)
- Navigasyon geri bildirimi topla (19 Eylül)
- Kullanıcı testi planla (26 Eylül — beklemede)"
```

#### 🤝 Kişisel CRM
```
Sen: "Marketing'den John ile en son ne zaman görüştüm?"

YZ: *'John' ve #marketing etiketlerini arar*
"20 Eylül:
'Q4 kampanyası için John ile kısa sync. Cuma'ya kadar brief gönderecek. Haftaya hatırlat. #marketing #john'"
```

#### 💡 Fikir Arşivi
```
Sen: "Kaydet için kaydettiğim tüm özellik fikirlerini göster."

YZ: *#kaydet #idea girdilerini listeler*
"Sekiz fikir bulundu:
- Günlük dosyaları için şifreleme (2 Eylül)
- PDF dışa aktarma (10 Eylül)
- Mobil eşlikçi uygulama (15 Eylül)
- Sesli nottan metne giriş (18 Eylül)
..."
```

#### ✍️ Eller Serbest Kayıt
```
Sen: "Girdi ekle: Dashboard yeniden tasarımını bitirdim.
Responsive düzen sandığımdan uzun sürdü.
Sonuçtan memnunum. #work #frontend #design"

YZ: ✅ 14:32'de kaydedildi
```

### Kısa Komutlar Hâlâ Geçerli
- "Bir girdi ekle: Bugün auth hatasını düzelttim #work"
- "Kayıtlarımda 'Apollo projesi'ni ara"
- "Bu ayki istatistiklerim ne?"
- “Tüm etiketleri listele”
- “Geçen haftaki #fitness girdilerini göster”

### Her Şey JSON Olabilir

```bash
kaydet --search work --format json
kaydet --tags --format json
kaydet --stats --format json
```

## Geliştirme

Kaydet’i yakından incelemek isterseniz depoyu klonlayıp kaynağından çalıştırabilirsiniz:

```bash
git clone https://github.com/miratcan/kaydet.git
cd kaydet
pip install -e .

# İsteğe bağlı araçlar
pip install -e .[dev]
ruff check src
black --check src
```

CLI’yi kaynak kodundan `python -m kaydet` ile başlatabilirsiniz.

## Katkıda Bulunun

Hata raporları, özellik önerileri ve pull request'ler hoş karşılanır.  
Bir issue açın, PR gönderin veya Kaydet’i nasıl kullandığınızı anlatın; birlikte daha hızlı gelişiriz.

## Lisans

Kaydet, esnek [MIT Lisansı](LICENSE) ile dağıtılır.  
Sürüm notları için [CHANGELOG.md](CHANGELOG.md) dosyasına bakın.

---

<div align="center">

💡 **Kaydet’i faydalı buldunuz mu?**

[⭐ Depoyu yıldızlayın](https://github.com/miratcan/kaydet) ki daha çok kişi keşfetsin.

Concerta ile yazıldı – [Mirat Can Bayrak](https://github.com/miratcan)

</div>
