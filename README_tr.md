# Kaydet — Terminal Günlüğünüz

Kaydet, günlük düşüncelerinizi kendi makinenizdeki düz metin dosyalarında saklayan, hafif bir komut satırı günlüğüdür. Alışkın olduğunuz iş akışınıza dahil olmak için tasarlanmıştır: hızlı bir not için çağırın, daha uzun düşünceleriniz için editörünüze geçiş yapın veya nostaljik hissettiğinizde arşiv klasörünüzü açın.

## Kullanım Alanları

Basit bir günlüğün ötesinde, `kaydet`'in hızlı komut satırı erişimi, zaman damgaları ve güçlü etiketleme sisteminin birleşimi, onu çeşitli kayıt tutma ihtiyaçları için çok yönlü bir araç haline getirir.

### İş Günlüğü (Work Log)
Görevleri, ilerlemeyi ve toplantı notlarını takip edin. Projeye veya müşteriye göre sınıflandırmak için etiketleri kullanın.

```bash
kaydet "Geliştirme sunucusundaki kimlik doğrulama hatası düzeltildi. #proje-apollo"
kaydet "Tasarım ekibiyle yeni arayüz hakkında toplantı yapıldı. #toplantı #proje-apollo"
```

### Kişisel Bilgi Bankası (Today I Learned)
Öğrendiğiniz yeni komutları, kod parçacıklarını veya ilginç bilgileri hızla kaydedin.

```bash
kaydet "TIL: `pytest --cov-report=html` komutu taranabilir bir kapsama raporu oluşturur. #python #test"
```

### Alışkanlık ve Spor Takibi (Habit and Fitness Tracker)
Antrenmanları, günlük alışkanlıkları veya zamanla takip etmek istediğiniz herhangi bir aktiviteyi kaydedin.

```bash
kaydet "5km koşu 28 dakikada tamamlandı. #spor #koşu"
kaydet "'Pragmatik Programcı' kitabından 20 sayfa okundu. #alışkanlık #okuma"
```

### Basit Zaman Yönetimi (Simple Time Tracking)
Harcanan zaman hakkında bir fikir edinmek için görevlere ne zaman başlayıp ne zaman durduğunuzu kaydedin.

```bash
kaydet "BAŞLA: Kullanıcı kimlik doğrulama modülünü yeniden düzenleme. #proje-apollo"
kaydet "BİTTİ: Kullanıcı kimlik doğrulama modülünü yeniden düzenleme. #proje-apollo"
```

### Fikir Yakalayıcı (Idea Catcher)
Terminaldeki iş akışınızı bozmadan fikirleri anında yakalayın.

```bash
kaydet "Yeni özellik fikri: günlük dosyaları için şifreleme ekle. #kaydet #fikir"
```

### Duygu Günlüğü (Mood Journal)
Günün farklı saatlerinde nasıl hissettiğinizi hızlıca not alın. Zamanla `#duygu` etiketlerinizi aratarak duygu durumunuzdaki desenleri görebilirsiniz.

```bash
kaydet "Bugün enerjik ve motive hissediyorum. ✨ #duygu"
```

### Basit Masraf Takibi (Simple Expense Tracker)
İş harcamalarını veya seyahat masraflarını anında kaydedin. Düz metin formatı, daha sonra bu verileri işlemeyi kolaylaştırır.

```bash
kaydet "Müşteri A ile öğle yemeği: 650 TL #masraf #müşteri-a"
```

### Kişisel CRM (İlişki Yönetimi)
Profesyonel veya kişisel çevrenizdeki insanlarla olan etkileşimlerinizi takip edin.

```bash
kaydet "Ahmet Yılmaz ile görüştük. Teklifi Cuma'ya kadar gönderecek. #ahmet-yılmaz"
```

## Öne Çıkanlar
- **Terminal Odaklı** – Shell'inizde kalır ve yapılandırdığınız metin editörünüze saygı duyar.
- **Verileriniz Sizin** – Basit zaman damgalı metin dosyaları, istediğiniz gibi senkronize etmek için mükemmeldir.
- **Yapılandırılabilir** – Dosya adlandırmayı, başlıkları, editör komutunu ve depolama konumunu ayarlayın.
- **Nazik Hatırlatıcılar** – Bir süredir bir şey yazmadıysanız isteğe bağlı bir dürtme.
- **Çapraz Platform** – Python 3.8+ çalışan her yerde çalışır.

## Kurulum
Kaydet, PyPI üzerinde yayınlanmıştır ve diğer herhangi bir Python CLI gibi kurulur:

```bash
pip install kaydet
```

İzole ortamları mı tercih ediyorsunuz? Kaydet, [pipx](https://github.com/pypa/pipx) ile de harika çalışır:

```bash
pipx install kaydet
```

> 💡 PyPI'ın güncellenmesini mi bekliyorsunuz? Bunun yerine en son sürümü GitHub'dan yükleyin:
> `pip install git+https://github.com/miratcan/kaydet.git`

## Hızlı Başlangıç
```bash
# Bugünün dosyasına kısa bir not ekle
kaydet "Yan proje üzerinde ilerleme kaydettim."

# Bir notu sınıflandırmak için satır içi hashtag'ler ekle
kaydet "Arkadaşlarla akşam yemeği #aile #şükran"

# Daha uzun bir not için favori editörüne geç
kaydet --editor

# Tüm günlük dosyalarını tutan klasörü aç
kaydet --folder

# Hızlı etiket yönetimi
kaydet --folder aile     # etiketi aç
kaydet --tags            # etiketleri listele
kaydet --doctor          # etiket arşivlerini yeniden oluştur

# Geçmiş notlarda bir kelime veya etiket parçası ara
kaydet --search şükran
```

## Yapılandırma
Kaydet, ayarlarını `~/.config/kaydet/config.ini` içinde (veya `XDG_CONFIG_HOME` tarafından işaret edilen konumda) saklar. Dosya ilk çalıştırmada oluşturulur ve değerlerden herhangi birini değiştirebilirsiniz. Minimal bir örnek:

```ini
[SETTINGS]
DAY_FILE_PATTERN = %Y-%m-%d.txt
DAY_TITLE_PATTERN = %Y/%m/%d - %A
LOG_DIR = /Users/kullanici/.kaydet
EDITOR = nvim
```

## Geliştirme
Kaydet üzerinde yerel olarak çalışmak için depoyu klonlayın ve düzenlenebilir modda kurun:

```bash
git clone https://github.com/miratcan/kaydet.git
cd kaydet
pip install -e .

# isteğe bağlı: formatlama/lint ekstra bağımlılıklarını kur
pip install -e .[dev]

# stil denetimlerini çalıştır
ruff check src
black --check src
```

## Lisans
Kaydet, müsamahakâr [MIT Lisansı](LICENSE) altında yayınlanmıştır.

Sürüm geçmişi için [CHANGELOG.md](CHANGELOG.md) dosyasına bakın.
