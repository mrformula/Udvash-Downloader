# উদ্ভাস অনলাইন ভিডিও ডাউনলোডার 🎥

এই টুলটি উদ্ভাস অনলাইন ক্লাসের ভিডিও এবং নোট ডাউনলোড করার জন্য তৈরি করা হয়েছে।

## 📋 ফিচার সমূহ

- 🎬 ভিডিও ডাউনলোড
  - মাল্টিপল কোয়ালিটি সাপোর্ট (360p, 480p, 720p, 1080p)
  - ইউটিউব ভার্সন ডাউনলোড (যদি উপলব্ধ থাকে)
  - ডাউনলোড স্পীড এবং প্রোগ্রেস ট্র্যাকিং
  - aria2c দিয়ে হাই-স্পীড ডাউনলোড

- 📝 নোট ডাউনলোড
  - PDF নোট অটোমেটিক ডাউনলোড
  - স্মার্ট ফাইল নেমিং

- 🔄 ব্যাচ ডাউনলোড
  - একসাথে অনেকগুলো ক্লাস ডাউনলোড
  - কোর্স এবং সাবজেক্ট অনুযায়ী ফিল্টারিং
  - রিজিউম সাপোর্ট

- 🎨 ইউজার ফ্রেন্ডলি ইন্টারফেস
  - প্রোগ্রেস বার
  - কালারফুল আউটপুট
  - স্ট্যাটাস আপডেট

## ⚙️ ইনস্টলেশন

### প্রয়োজনীয় টুলস

1. Python 3.7+
2. Google Chrome ব্রাউজার
3. aria2c (ফাস্টার ডাউনলোডের জন্য)

### প্যাকেজ ইনস্টলেশন 

প্রয়োজনীয় প্যাকেজ ইনস্টল
```bash
pip install selenium requests beautifulsoup4 rich yt-dlp aria2p tqdm
```
aria2c ইনস্টল (অপশনাল - ফাস্টার ডাউনলোডের জন্য)
Windows:
প্রয়োজনীয় প্যাকেজ ইনস্টল
```bash
choco install aria2
```


### Chrome WebDriver

- Chrome ব্রাউজারের সাথে কম্প্যাটিবল Chrome WebDriver ডাউনলোড করে PATH এ রাখুন
- অথবা `webdriver_manager` প্যাকেজ ইনস্টল করুন:
```bash
pip install webdriver_manager
```

## 🚀 ব্যবহার পদ্ধতি

### 1. সিঙ্গেল ক্লাস ডাউনলোড
```bash
python video_downloader.py
```

### 2. মাল্টিপল ক্লাস ডাউনলোড

```bash
python master_downloader.py
```

### কুকিজ সেটআপ

1. উদ্ভাস অনলাইনে লগইন করুন
2. ব্রাউজারের DevTools খুলুন (F12)
3. Network ট্যাবে যান
4. কুকিজ কপি করুন
5. প্রোগ্রাম রান করার সময় কুকিজ পেস্ট করুন

## ⚡ বৈশিষ্ট্য

- স্মার্ট এরর হ্যান্ডলিং
- অটোমেটিক রিট্রাই
- কুকিজ সেভিং
- মাল্টিথ্রেডেড ডাউনলোড
- ইন্টেলিজেন্ট ফাইল নেমিং
- প্রোগ্রেস ট্র্যাকিং
- রিজিউম সাপোর্ট


## ⚠️ সতর্কতা

- শুধুমাত্র নিজের একাউন্টের ভিডিও ডাউনলোড করুন
- অন্যের কুকিজ ব্যবহার করবেন না
- একসাথে অনেক ফাইল ডাউনলোড করলে ইন্টারনেট স্পীড স্লো হতে পারে

## 🤝 কন্ট্রিবিউশন

পুল রিকোয়েস্ট স্বাগত! বাগ রিপোর্ট বা ফিচার রিকোয়েস্টের জন্য ইস্যু ক্রিয়েট করুন।

## 📜 লাইসেন্স

MIT License

## 📞 সাপোর্ট

কোন সমস্যা হলে ইস্যু ক্রিয়েট করুন।


