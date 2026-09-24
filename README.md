# Interactive Video Engine (KAISER)

วิดีโอแบบมีปฏิสัมพันธ์สำหรับ Moodle — หยุดวิดีโอถามคำถาม ข้ามคำถามไม่ได้ และ**ไม่ส่งเฉลยไปถึงเบราว์เซอร์**
การตรวจคำตอบทั้งหมดเกิดที่เครื่องยนต์ฝั่งเซิร์ฟเวอร์

| โฟลเดอร์ | คืออะไร |
|---|---|
| `moodle/plugins/mod_kaiiv/` | ปลั๊กอินกิจกรรม Moodle (4.5 ขึ้นไป) ตัวเล่นพัฒนาต่อจาก H5P Interactive Video |
| `kaiiv-service/` | เครื่องยนต์ตรวจคำตอบ (FastAPI) ไม่เก็บข้อมูลใดๆ รันด้วย Docker |
| `docs/INTERACTIVE-VIDEO-API.md` | API ภายในระหว่างระบบกับเครื่องยนต์ |

รองรับ 10 ชนิด: ตอบข้อเดียว, ตอบหลายข้อ, ถูกหรือผิด, พิมพ์คำตอบ, เติมคำ, ลากคำไปเติม,
เลือกคำในข้อความ, ข้อความ, รูปภาพ, ลิงก์

## ติดตั้ง

คู่มือสำหรับผู้ดูแลระบบอยู่ที่ [`moodle/plugins/mod_kaiiv/INSTALL.md`](moodle/plugins/mod_kaiiv/INSTALL.md)

## สร้างไฟล์ติดตั้ง

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
cd moodle/plugins/mod_kaiiv && node tests/smoke.js && python tests/check_fork.py
```

## ลิขสิทธิ์

ตัวเล่นพัฒนาต่อจาก [H5P Interactive Video](https://github.com/h5p/h5p-interactive-video) และ
[h5p-lib-controls](https://github.com/h5p/h5p-lib-controls) ซึ่งใช้สัญญาอนุญาต MIT
ประกาศลิขสิทธิ์อยู่ใน `moodle/plugins/mod_kaiiv/thirdparty/`
