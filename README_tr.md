# Kaydet — Düşünceleriniz, Tek Komut Uzağınızda

[![PyPI versiyonu](https://img.shields.io/pypi/v/kaydet.svg)](https://pypi.org/project/kaydet/)
[![İndirmeler](https://img.shields.io/pypi/dm/kaydet.svg)](https://pypi.org/project/kaydet/)
[![Python](https://img.shields.io/pypi/pyversions/kaydet.svg)](https://pypi.org/project/kaydet/)
[![Lisans](https://img.shields.io/github/license/miratcan/kaydet.svg)](LICENSE)

> 🚀 **Ultra hızlı komut satırı günlüğü** | 📦 **Düz metin, sıfır bağımlılık** | 🏷️ **Akıllı etiketleme** | 🤖 **Yapay zekaya hazır**

Kaydet, günlük düşüncelerinizi kendi makinenizdeki düz metin dosyalarında saklayan, hafif bir komut satırı günlüğüdür. Alışkın olduğunuz iş akışınıza dahil olmak için tasarlanmıştır: hızlı bir not için çağırın, daha uzun düşünceleriniz için editörünüze geçiş yapın veya nostaljik hissettiğinizde arşiv klasörünüzü açın.

**[📥 Şimdi Kurun](#kurulum)** • **[⚡ Hızlı Başlangıç](#hızlı-başlangıç)**

## Demo

<a href="https://asciinema.org/a/Rlcc9GaTQEEfTlUIicvHxm8iC" target="_blank"><img src="https://asciinema.org/a/Rlcc9GaTQEEfTlUIicvHxm8iC.svg" /></a>

## Kurulum

Doğrudan GitHub'dan kurun:

```bash
pip install git+https://github.com/miratcan/kaydet.git
```

İzole ortamlar için [pipx](https://github.com/pypa/pipx) kullanın:

```bash
pipx install git+https://github.com/miratcan/kaydet.git
```

Yapay zeka entegrasyonu için MCP desteği ile kurun:

```bash
pip install "git+https://github.com/miratcan/kaydet.git#egg=kaydet[mcp]"
```

## Neden Kaydet?

### vs. Notion, Obsidian, Logseq
- **🏃 Bağlam değiştirmek yok** — Terminalinizde kalın, GUI gerekmez
- **⚡ Anında yakalama** — Bir uygulama açıp menülerde gezinmek yerine tek komut
- **📂 Düz metin dosyaları** — Veritabanı yok, kilitlenme yok, `grep` ile aranabilir, `git` dostu

### vs. Düz Metin Dosyaları
- **🔍 Dahili arama** — `grep` sihirbazlığı olmadan girdileri anında bulun
- **🏷️ Otomatik etiketleme** — Hashtag'lerle düzenleyin, etikete göre otomatik arşivlenir
- **📊 İstatistikler ve içgörüler** — Takvim görünümü, girdi sayıları, aktivite takibi

### vs. Günlük Uygulamaları
- **🔒 Önce gizlilik** — Verileriniz asla makinenizden ayrılmaz
- **🎨 Editör özgürlüğü** — `vim`, `emacs`, `nano` veya sevdiğiniz herhangi bir editörü kullanın
- **🔧 Tamamen özelleştirilebilir** — Dosya adlandırma, zaman damgaları, dizin yapısı

### 🤖 Yapay Zekaya Hazır
- **MCP entegrasyonu** — Claude ve diğer yapay zeka asistanlarıyla kutudan çıktığı gibi çalışır
- **Doğal dil sorguları** — Karmaşık aramalar yerine "Geçen hafta ne üzerinde çalıştım?"
- **JSON API** — Programatik erişim ve otomasyon için yapılandırılmış çıktı
- **Akıllı özetler** — Yapay zekanın girdilerinizden desenleri ve içgörüleri analiz etmesine izin verin

## Kullanım Alanları

Basit bir günlüğün ötesinde, `kaydet`'in hızlı komut satırı erişimi, zaman damgaları ve güçlü etiketleme sisteminin birleşimi, onu çeşitli kayıt tutma ihtiyaçları için çok yönlü bir araç haline getirir.

### 💼 İş Günlüğü
Görevleri, ilerlemeyi ve toplantı notlarını takip edin. Projeye veya müşteriye göre sınıflandırmak için etiketleri kullanın.

```bash
kaydet "Geliştirme sunucusundaki kimlik doğrulama hatası düzeltildi. #proje-apollo"
kaydet "Tasarım ekibiyle yeni arayüz hakkında toplantı yapıldı. #toplantı #proje-apollo"
```

### 📚 Kişisel Bilgi Bankası (Bugün Ne Öğrendim)
Öğrendiğiniz yeni komutları, kod parçacıklarını veya ilginç bilgileri hızla kaydedin.

```bash
kaydet "BNÖ: `pytest --cov-report=html` komutu taranabilir bir kapsama raporu oluşturur. #python #test"
```

### 💪 Alışkanlık ve Spor Takibi
Antrenmanları, günlük alışkanlıkları veya zamanla takip etmek istediğiniz herhangi bir aktiviteyi kaydedin.

```bash
kaydet "5km koşu 28 dakikada tamamlandı. #spor #koşu"
kaydet "'Pragmatik Programcı' kitabından 20 sayfa okundu. #alışkanlık #okuma"
```

### ⏱️ Basit Zaman Takibi
Harcanan zaman hakkında bir fikir edinmek için görevlere ne zaman başlayıp ne zaman durduğunuzu kaydedin.

```bash
kaydet "BAŞLA: Kullanıcı kimlik doğrulama modülünü yeniden düzenleme. #proje-apollo"
kaydet "BİTTİ: Kullanıcı kimlik doğrulama modülünü yeniden düzenleme. #proje-apollo"
```

### 💡 Fikir Yakalayıcı
Terminaldeki iş akışınızı bozmadan fikirleri anında yakalayın.

```bash
kaydet "Yeni özellik fikri: günlük dosyaları için şifreleme ekle. #kaydet #fikir"
```

### 😊 Duygu Günlüğü
Günün farklı saatlerinde nasıl hissettiğinizi hızlıca not alın. Zamanla `#duygu` etiketlerinizi aratarak duygu durumunuzdaki desenleri görebilirsiniz.

```bash
kaydet "Bugün üretken ve odaklanmış hissediyorum. ✨ #duygu"
```

### 💰 Basit Masraf Takibi
İş harcamalarını veya seyahat masraflarını anında kaydedin. Düz metin formatı, daha sonra bu verileri işlemeyi kolaylaştırır.

```bash
kaydet "Müşteri ile öğle yemeği: 650.00 TL #masraf #müşteri-a"
```

### 🤝 Kişisel CRM
Profesyonel veya kişisel çevrenizdeki insanlarla olan etkileşimlerinizi takip edin.

```bash
kaydet "Ahmet Yılmaz'ı teklifi görüşmek için aradım. Cuma gününe kadar geri dönecek. #ahmet-yılmaz"
```

## Öne Çıkanlar
- **Terminal yerlisi** – kabuğunuzda kalır ve yapılandırdığınız editöre saygı duyar.
- **Verilerinize sahip çıkın** – basit zaman damgalı metin dosyaları, istediğiniz gibi senkronize etmek için mükemmeldir.
- **Yapılandırılabilir** – dosya adlandırmayı, başlıkları, editör komutunu ve depolama konumunu ayarlayın.
- **Nazik hatırlatıcılar** – bir süredir bir şey yazmadıysanız isteğe bağlı bir dürtme.
- **Çapraz platform** – Python 3.8+ çalışan her yerde çalışır.

## Hızlı Başlangıç
```bash
# Bugünün dosyasına kısa bir girdi ekle
kaydet "Yan proje üzerinde ilerleme kaydettim."

# Bir girdiyi kategorize etmek için satır içi hashtag'ler ekle
kaydet "Arkadaşlarla akşam yemeği #aile #şükran"

# Daha uzun bir not için favori editörünüze geçin
kaydet --editor

# Tüm günlük dosyalarını tutan klasörü aç
kaydet --folder

# Hızlı etiket yönetimi
kaydet --folder aile   # aç
kaydet --tags            # listele
kaydet --doctor          # etiket arşivlerini yeniden oluştur

# Geçmiş girdilerde bir kelime veya etiket parçası ara
kaydet --search şükran
```

Örnek `kaydet --stats` çıktısı:

```
Eylül 2025
Pz Sa Ça Pe Cu Ct Pz
 1[  ]  2[  ]  3[  ]  4[  ]  5[  ]  6[  ]  7[  ]
 8[  ]  9[  ] 10[  ] 11[  ] 12[  ] 13[  ] 14[  ]
...
Bu ayki toplam girdi: 12
```

Her girdi günlük bir dosyaya (örneğin `~/.kaydet/2024-02-19.txt`) yazılır ve geçerli saatle ön eklenir. Mevcut bir günlük dosyasını açmak yeni bir bölüm ekler; günün ilk girdisi, kolay gezinme için bir başlıkla dosyayı oluşturur.

Notları kategorize etmek için satır içi hashtag'ler (örneğin `#aile`) ekleyin — Kaydet bunları satır içinde tutar, girdiyi etiket başına bir klasöre (örneğin `~/.kaydet/aile/`) yansıtır, `kaydet --folder aile` aracılığıyla doğrudan etiket klasörlerini açmanıza olanak tanır, etiketleri `kaydet --tags` içinde gösterir, `kaydet --search` ile aranabilir hale getirir ve mevcut günlükleri `kaydet --doctor` ile geriye dönük olarak doldurabilir.

## Yapılandırma
Kaydet, ayarlarını `~/.config/kaydet/config.ini` içinde (veya `XDG_CONFIG_HOME` tarafından işaret edilen konumda) saklar. Dosya ilk çalıştırmada oluşturulur ve değerlerden herhangi birini değiştirebilirsiniz. Minimal bir örnek:

```ini
[SETTINGS]
DAY_FILE_PATTERN = %Y-%m-%d.txt
DAY_TITLE_PATTERN = %Y/%m/%d - %A
LOG_DIR = /Users/siz/.kaydet
EDITOR = nvim
```

- `DAY_FILE_PATTERN` günlük dosya adını kontrol eder.
- `DAY_TITLE_PATTERN` yeni dosyaların en üstüne yazılan başlığı ayarlar.
- `LOG_DIR` girdilerin yaşadığı dizini gösterir.
- `EDITOR` Kaydet'in uzun biçimli girdiler (`--editor`) için çalıştırdığı komuttur.

Herhangi bir düzenleme, Kaydet'i bir sonraki çağrışınızda etkili olur.

## Hatırlatıcılar
Son zamanlarda bir şey kaydetmediyseniz bir uyarı ister misiniz? Hatırlatıcı bayrağını kabuk başlangıcınıza (örneğin `~/.zshrc` içinde) ekleyin:

```bash
# ~/.zshrc
kaydet --reminder
```

Son girdi iki saatten eskiyse Kaydet şunu yazdırır:

```
Son Kaydet girdinizden bu yana iki saatten fazla zaman geçti. `kaydet --editor` ile neler yaptığınızı yakalayın.
```

## Yapay Zeka Entegrasyonu (MCP Sunucusu)

Kaydet, [Model Bağlam Protokolü (MCP)](https://modelcontextprotocol.io/)'nü destekleyerek MCP-uyumlu yapay zeka asistanlarının günlük girdilerinizle doğal dil kullanarak etkileşime girmesine olanak tanır.

**Desteklenen Yapay Zeka Araçları:**
- [Claude Desktop](https://claude.ai/download) - Anthropic'in masaüstü uygulaması
- [Cline](https://github.com/cline/cline) - VS Code AI asistanı
- [Codex](https://github.com/openai/codex) - OpenAI'ın kod asistanı
- Diğer tüm MCP-uyumlu araçlar

### Kurulum

```bash
pip install kaydet[mcp]
```

### Yapılandırma

#### Claude Desktop için
`~/.config/Claude/claude_desktop_config.json` dosyasına ekleyin:

```json
{
  "mcpServers": {
    "kaydet": {
      "command": "kaydet-mcp"
    }
  }
}
```

#### Cline (VS Code) için
Cline MCP ayarlarınıza ekleyin:

```json
{
  "mcpServers": {
    "kaydet": {
      "command": "kaydet-mcp"
    }
  }
}
```

#### Diğer MCP Araçları için
MCP sunucu yapılandırması için aracınızın belgelerine bakın. Komut olarak `kaydet-mcp` kullanın.

### Mevcut Araçlar

MCP sunucusu bu araçları yapay zeka asistanlarına sunar:

- **add_entry** - Yeni günlük girdileri ekleyin
- **search_entries** - Günlüğünüzde arama yapın
- **list_tags** - Tüm etiketlerinizi alın
- **get_stats** - Girdi istatistiklerini görüntüleyin

### Gerçek Dünya Kullanım Senaryoları

Yapılandırıldıktan sonra, günlüğünüzle doğal dil kullanarak etkileşime geçebilirsiniz:

#### 📊 **Proje Retrospektifleri**
```
Siz: "Geçen ay kimlik doğrulama projesi için neler yaptım?"

AI: *#auth etiketli girdileri arar ve özetler*
"Geçen ay kimlik doğrulama projesi üzerinde 12 kez çalıştınız:
- OAuth token yenileme hatasını düzelttiniz
- 2FA uyguladınız
- JWT token'lara geçiş yaptınız
- Şifre sıfırlama akışı eklediniz
En aktif hafta 15-20 Eylül arası 5 girdi ile."
```

#### 🧠 **Öğrenme Pattern Analizi**
```
Siz: "Bu yıl Python testing hakkında neler öğrendim?"

AI: *#python #testing etiketli girdileri arar*
"TIL girdilerinize göre öğrendikleriniz:
- pytest fixtures ve parametrization (Mart)
- pytest-cov ile coverage raporlama (Haziran)
- unittest.mock ile mocking (Ağustos)
- Hypothesis ile property-based testing (Eylül)"
```

#### 💪 **Fitness İlerleme Takibi**
```
Siz: "Bu ay geçen aya göre daha fazla egzersiz yapıyor muyum?"

AI: *#spor girdilerini analiz eder*
"Bu ay: 18 spor girdisi (ort. 4.5/hafta)
Geçen ay: 12 spor girdisi (ort. 3/hafta)
%50 artış var! En tutarlı aktivite: koşu (8 girdi)"
```

#### 🎯 **Verimlilik İçgörüleri**
```
Siz: "Çalışma alışkanlıklarımda ne gibi paternler görüyorsun?"

AI: *#iş girdilerini zaman ve etiketlere göre analiz eder*
"İş günlüğünüzden paternler:
- En verimli saatler: 09:00-11:00 (en yoğun girdi yoğunluğu)
- Salı ve Perşembe günleri derin çalışma yapma eğilimindesiniz
- Bug fix'ler genellikle öğleden sonra oluyor
- #frontend görevlerinde daha düzenli mola veriyorsunuz"
```

#### 💼 **Toplantı Takipleri**
```
Siz: "Tasarım ekibiyle yapılan toplantılardan çıkan aksiyon maddeleri neler?"

AI: *#toplantı #tasarım girdilerini arar*
"6 tasarım ekibi toplantısı bulundu. Bahsedilen aksiyon maddeleri:
- Dashboard için renk paletini tamamla (5 Eylül)
- Mobil mockup'ları incele (12 Eylül)
- Yeni navigasyon hakkında geri bildirim al (19 Eylül)
- Kullanıcı test oturumu planla (26 Eylül - hala beklemede)"
```

#### 🤝 **Kişisel CRM**
```
Siz: "Pazarlamadan Ahmet ile son etkileşimim ne zamandı?"

AI: *'Ahmet' ve #pazarlama içeren girdileri arar*
"Son iletişim: 20 Eylül
'Pazarlamadan Ahmet ile Q4 kampanyası hakkında hızlı senkronizasyon.
Cuma'ya kadar brief'i gönderecek. Önümüzdeki hafta takip et. #pazarlama #ahmet'"
```

#### 💡 **Fikir Bulma**
```
Siz: "Kaydet için aklıma gelen tüm özellikleri göster"

AI: *#kaydet #fikir etiketli girdileri arar*
"Kaydet için 8 özellik fikri kaydetmişsiniz:
- Günlük dosyaları için şifreleme ekle (2 Eylül)
- PDF formatına export (10 Eylül)
- Mobil yardımcı uygulama (15 Eylül)
- Sesli girdi özelliği (18 Eylül)
..."
```

#### ✍️ **AI ile Hızlı Girdi**
```
Siz: "Günlük girdisi ekle: Kullanıcı dashboard yeniden tasarımını bitirdim.
Responsive layout sorunları yüzünden beklenenden uzun sürdü.
Sonuçtan memnunum. #iş #frontend #tasarım"

AI: ✅ Günlük girdiniz 14:32'de eklendi
```

### Basit Komutlar

Tek satırlık komutlar da kullanabilirsiniz:

- "Günlük girdisi ekle: Bugün kimlik doğrulama hatasını düzelttim #iş"
- "Günlüğümde 'Apollo projesi' ara"
- "Bu ayki günlük istatistiklerim neler?"
- "Tüm etiketlerimi listele"
- "Geçen haftaki tüm #spor girdilerimi göster"

### JSON Çıktısı

Kaydet ayrıca programatik erişim için JSON çıktısını da destekler:

```bash
kaydet --search iş --format json
kaydet --tags --format json
kaydet --stats --format json
```

## Geliştirme
Kaydet üzerinde yerel olarak çalışmak için depoyu klonlayın ve düzenlenebilir modda kurun:

```bash
git clone https://github.com/miratcan/kaydet.git
cd kaydet
pip install -e .

# isteğe bağlı: formatlama/lint ekstralarını kurun
pip install -e .[dev]

# stil denetimlerini çalıştırın
ruff check src
black --check src
```

CLI'yi kaynaktan `python -m kaydet` ile çalıştırın.

## Katkıda Bulunma

Katkılarınızı bekliyoruz! Hata raporları, özellik istekleri veya kod katkıları olsun, bir sorun açmaktan veya bir pull isteği göndermekten çekinmeyin.

## Lisans

Kaydet, müsamahakâr [MIT Lisansı](LICENSE) altında yayınlanmıştır.

Sürüm geçmişi için [CHANGELOG.md](CHANGELOG.md) dosyasına bakın.

---

<div align="center">

💡 **Kaydet'i faydalı buldunuz mu?**

[⭐ Depoyu yıldızlayın](https://github.com/miratcan/kaydet) başkalarının da keşfetmesine yardımcı olmak için!

[Mirat Can Bayrak](https://github.com/miratcan) tarafından Concerta ile yapılmıştır

</div>