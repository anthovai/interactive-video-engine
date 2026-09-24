# Interactive Video Engine (KAISER)

วิดีโอแบบมีปฏิสัมพันธ์ ใช้ได้ทั้งใน Moodle และในเว็บของระบบอื่น — หยุดวิดีโอถามคำถาม ข้ามคำถามไม่ได้ และ**ไม่ส่งเฉลยไปถึงเบราว์เซอร์**
การตรวจคำตอบทั้งหมดเกิดที่เครื่องยนต์ฝั่งเซิร์ฟเวอร์

| โฟลเดอร์ | คืออะไร |
|---|---|
| `kaiiv-studio/` | **ระบบสำเร็จรูปที่ไม่ต้องมี Moodle**: สร้างบทเรียน ใส่คำถาม จัดการผู้ใช้ ดูคะแนน รันด้วย `docker compose up` |
| `kaiiv-player/` | ตัวเล่นสำหรับหน้าเว็บของระบบไหนก็ได้ พัฒนาต่อจาก H5P Interactive Video มีเซิร์ฟเวอร์ตัวอย่างใน `examples/server` |
| `moodle/plugins/mod_kaiiv/` | ปลั๊กอินกิจกรรม Moodle (4.5 ขึ้นไป) สร้างจาก `kaiiv-player` ตัวเดียวกัน |
| `kaiiv-service/` | เครื่องยนต์ตรวจคำตอบ (FastAPI) ไม่เก็บข้อมูลใดๆ รันด้วย Docker |
| `docs/INTERACTIVE-VIDEO-API.md` | API ภายในระหว่างระบบกับเครื่องยนต์ |

รองรับ 10 ชนิด: ตอบข้อเดียว, ตอบหลายข้อ, ถูกหรือผิด, พิมพ์คำตอบ, เติมคำ, ลากคำไปเติม,
เลือกคำในข้อความ, ข้อความ, รูปภาพ, ลิงก์

## ติดตั้ง

- **ใช้เลยโดยไม่ต้องมี Moodle หรือระบบอื่น**: [`kaiiv-studio/README.md`](kaiiv-studio/README.md)
- **ใส่ในเว็บของระบบอื่น**: [`kaiiv-player/README.md`](kaiiv-player/README.md)
- **ติดตั้งใน Moodle**: [`moodle/plugins/mod_kaiiv/INSTALL.md`](moodle/plugins/mod_kaiiv/INSTALL.md)

## สร้างไฟล์ติดตั้ง

```bash
cd kaiiv-player && npm ci && npm run build
```

```bash
cd moodle/plugins/mod_kaiiv && npm ci && npm run build
```

```bash
python moodle/plugins/mod_kaiiv/tools/package.py
```

ได้ `dist/mod_kaiiv-<เวอร์ชัน>.zip` และ `dist/kaiiv-service-<เวอร์ชัน>.zip`

## ทดสอบ

```bash
cd kaiiv-service && python -m pytest -q
```

```bash
cd kaiiv-studio && pip install -r requirements.txt pytest && python -m pytest
```

```bash
cd kaiiv-player && npm test
```

```bash
cd moodle/plugins/mod_kaiiv && node tests/smoke.js
```

## ลิขสิทธิ์

ตัวเล่นพัฒนาต่อจาก [H5P Interactive Video](https://github.com/h5p/h5p-interactive-video) และ
[h5p-lib-controls](https://github.com/h5p/h5p-lib-controls) ซึ่งใช้สัญญาอนุญาต MIT
และรวม jQuery / jQuery UI (MIT) กับ Font Awesome Free (ฟอนต์ SIL OFL 1.1)
ประกาศลิขสิทธิ์อยู่ใน `kaiiv-player/thirdparty/`
