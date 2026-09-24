# KAISER Interactive Video Player

ตัวเล่นวิดีโอแบบมีปฏิสัมพันธ์สำหรับใส่ในเว็บของระบบไหนก็ได้ วิดีโอหยุดถามคำถาม ข้ามคำถามไม่ได้
และ**เบราว์เซอร์ไม่เคยได้เฉลยหรือตรวจคำตอบเอง**

ใช้คู่กับเครื่องยนต์ตรวจคำตอบ [`kaiiv-service`](../kaiiv-service) ปลั๊กอิน Moodle
[`mod_kaiiv`](../moodle/plugins/mod_kaiiv) ก็สร้างจากตัวเล่นนี้ตัวเดียวกัน

> **ไม่มีระบบเดิมให้ต่อ?** ใช้ [`kaiiv-studio`](../kaiiv-studio) ระบบสำเร็จรูปที่มีหน้าสร้างคำถาม
> ผู้ใช้ และรายงานคะแนนครบ รันด้วย `docker compose up` คำสั่งเดียว ไม่ต้องเขียนโค้ดเพิ่ม

---

## ภาพรวม: สามชิ้น และแต่ละชิ้นถืออะไร

```
 เบราว์เซอร์                      เซิร์ฟเวอร์ของระบบคุณ                 kaiiv-service
 ┌──────────────┐  คำตอบ      ┌─────────────────────────┐  /judge     ┌──────────────┐
 │ kaiiv-player │ ─────────▶ │ เก็บคำถาม เฉลย คำตอบ      │ ─────────▶ │ ตรวจ ไม่เก็บอะไร │
 │ (ไฟล์นี้)     │ ◀───────── │ ถือกุญแจของเครื่องยนต์     │ ◀───────── │               │
 └──────────────┘  ผลตรวจ     └─────────────────────────┘             └──────────────┘
```

| สิ่งนี้ | อยู่ที่ไหน | ห้ามอยู่ที่ไหน |
|---|---|---|
| กุญแจของเครื่องยนต์ (`KAIIV_API_KEY`) | เซิร์ฟเวอร์ของคุณ | หน้าเว็บ |
| เฉลย | ฐานข้อมูลของคุณ | หน้าเว็บ |
| การตรวจ | เครื่องยนต์ ถูกเรียกโดยเซิร์ฟเวอร์ของคุณ | หน้าเว็บ |
| ประวัติการตอบของผู้เรียน | ฐานข้อมูลของคุณ | เครื่องยนต์ (มันไม่เก็บอะไรเลย) |

**ห้ามให้เบราว์เซอร์เรียกเครื่องยนต์ตรงๆ** — หน้าเว็บที่เรียกได้ก็คือหน้าเว็บที่มีกุญแจ
และใครก็ตามที่เปิด developer tools ก็จะสั่งเครื่องยนต์ได้เหมือนกัน

---

## ลองก่อนใน 3 คำสั่ง

ต้องมี Docker และ Node 18 ขึ้นไป

```bash
cd kaiiv-service && KAIIV_API_KEY=<กุญแจยาวๆ> docker compose up -d --build
```

```bash
cd kaiiv-player/examples/server && KAIIV_API_KEY=<กุญแจเดียวกัน> node seed.js <ไฟล์วิดีโอ.mp4>
```

```bash
cd kaiiv-player/examples/server && KAIIV_API_KEY=<กุญแจเดียวกัน> node server.js
```

แล้วเปิด http://127.0.0.1:8200/ จะได้บทเรียนตัวอย่างที่มีคำถามครบทั้ง 10 ชนิด

`examples/server/server.js` คือตัวอย่างการต่อที่ครบที่สุดและสั้นที่สุด (ไม่มี package ภายนอก)
**อ่านไฟล์นั้นก่อนเขียนของระบบคุณเอง**

---

## ใส่ในหน้าเว็บ

```html
<link rel="stylesheet" href="/kaiiv/kaiiv-player.css">
<div id="lesson"></div>
<script src="/kaiiv/kaiiv-player.js"></script>
<script>
  KaiivPlayer.create('#lesson', {
    video: {provider: 'file', src: '/media/lesson.mp4'},
    items: ITEMS_FROM_YOUR_SERVER,
    lang: 'th',
    answer: (id, response) => fetch('/your/answer/endpoint', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({interaction: id, response: response}),
    }).then((r) => r.json()),
    progress: ({position, finished, leaving}) => { /* บันทึกว่าดูถึงไหน */ },
  });
</script>
```

วางทั้งโฟลเดอร์ `dist/` ไว้ที่เดียวกัน — `kaiiv-player.css` อ้างถึง `fonts/` และ `images/` แบบ relative

ถ้าใช้ bundler ให้ import `dist/kaiiv-player.esm.js` แทน:
`import {create} from '@kaiser/kaiiv-player';`

### ตัวเลือกของ `create(element, options)`

| ตัวเลือก | จำเป็น | ความหมาย |
|---|---|---|
| `video` | ✅ | `{provider: 'file', src}`, `{provider: 'hls', src}`, `{provider: 'youtube', videoid}`, `{provider: 'vimeo', videoid}` |
| `items` | ✅ | ที่เครื่องยนต์ตอบกลับจาก `/timeline` — **ส่งต่อทั้งก้อน ไม่ต้องแปลง** |
| `answer(id, response)` | ✅ | ส่งคำตอบไปเซิร์ฟเวอร์ของคุณ คืน Promise ของผลตรวจ (ดูด้านล่าง) |
| `progress({position, finished, leaving})` | | บันทึกว่าดูถึงไหน ถ้า `leaving` เป็นจริง หน้ากำลังปิด ให้ใช้ `navigator.sendBeacon` |
| `mustanswer` | | ค่าเริ่มต้น `true` — วิดีโอไปต่อไม่ได้ถ้ายังไม่ตอบ |
| `resumeat` | | วินาทีที่ให้เล่นต่อ ตัวเล่นจะไม่ข้ามคำถามที่ยังไม่ได้ตอบให้ |
| `title`, `posterstart` | | ชื่อบนหน้าจอเริ่ม |
| `bookmarks` | | `[{at: 15, label: 'บทที่ 2'}]` |
| `lang` | | `'th'` หรือ `'en'` (ค่าเริ่มต้น `'en'`) |
| `strings` | | แทนข้อความใดก็ได้ ดูชื่อใน `src/strings.js` |
| `logger` | | `{debug, info, warn, error}` ค่าเริ่มต้นคือ console |
| `attachStream(video, url)` | | ใส่สตรีม HLS ในเบราว์เซอร์ที่เล่นเองไม่ได้ ถ้าไม่ใส่จะใช้ `window.Hls` (hls.js) ถ้ามี |
| `onBackend(backend)`, `onAnswer(id, verdict)`, `onEnd()` | | แจ้งเหตุการณ์ |

`create()` คืน Promise ของ `{root, instance, player}`

### ผลตรวจที่ `answer()` ต้องคืน

ส่งต่อคำตอบของเครื่องยนต์จาก `/judge` ได้เลย **เฉพาะฟิลด์เหล่านี้** (อย่าส่ง `store` กลับไป):

```json
{"ok": true, "correct": false, "revealed": false, "may_retry": true,
 "attempts": 1, "answers": [], "feedback": ""}
```

ถ้าเครื่องยนต์ปฏิเสธ ให้ส่ง `{"ok": false, "error": "<รหัสจากเครื่องยนต์>"}`
ตัวเล่นรู้จัก `no_attempts_left` และ `already_correct` และจะบอกผู้เรียนตรงๆ
ส่วนรหัสอื่นจะแสดงว่า "ยังไม่ได้บันทึก ลองอีกครั้ง"

---

## สิ่งที่เซิร์ฟเวอร์ของคุณต้องทำ

ครบสี่อย่างนี้ก็ใช้ได้ ตัวอย่างอยู่ใน `examples/server/server.js` ทุกข้อ
สัญญาของเครื่องยนต์ละเอียดอยู่ที่ [`docs/INTERACTIVE-VIDEO-API.md`](../docs/INTERACTIVE-VIDEO-API.md)

**1. ตอนผู้สอนบันทึกคำถาม** → `POST /author` → เก็บ `content` กับ `answers` คนละช่อง
ห้ามเก็บข้อความต้นฉบับที่มีดอกจัน (`*ปารีส*`) — นั่นคือเฉลยที่อยู่ในข้อความ

**2. ตอนผู้เรียนเปิดหน้า** → `POST /timeline` พร้อมคำถามทั้งหมด (มีเฉลย) และ `seen`
ของผู้เรียนคนนั้น → เอา `items` ที่ได้ใส่ลงหน้าเว็บ **ทำบนเซิร์ฟเวอร์ตอนสร้างหน้า**
อย่าเปิด endpoint ให้เบราว์เซอร์ขอ timeline เอง

**3. ตอนผู้เรียนตอบ** → `POST /judge` พร้อม

- `attempts`: ตอบข้อนี้ไปแล้วกี่ครั้ง
- `answered_correctly`: เคยตอบถูกหรือยัง

เครื่องยนต์จะ**ปฏิเสธ**ถ้าหมดสิทธิ์แล้ว หรือเคยตอบถูกแล้ว (409) — ส่งสองค่านี้ให้ถูกเสมอ
ไม่อย่างนั้นผู้เรียนที่ยิง request ตรงจะแก้คำตอบผิดเป็นถูกได้หลังเห็นเฉลยแล้ว
ถ้าผ่าน ให้บันทึก `store` กับ `correct` เป็นแถวใหม่

**4. ตอนคิดคะแนน** → `POST /score` พร้อมคำถามทั้งหมดและ `seen`

`seen` คือ `{"<id ของคำถาม>": {"response": ..., "correct": true, "attempts": 2}}`
ใช้คำตอบล่าสุดของแต่ละข้อ

---

## ข้อควรรู้

- ตัวเล่นตั้ง `window.H5P` ให้โค้ดที่ fork มาใช้ หน้าที่มี H5P ตัวจริงอยู่แล้ว**ยังไม่ได้ทดสอบ**
- jQuery และ jQuery UI อยู่ใน `kaiiv-player.js` แล้ว ไม่ต้องมีในหน้า และจะไม่ไปแตะ jQuery ของหน้า
- CSS ทุกกฎอยู่ใต้ `.kaiiv` ไม่กระทบส่วนอื่นของหน้า
- หน้าจอเล็ก ตัวเล่นแสดงคำถามเป็นปุ่มที่กดแล้วเปิดกล่อง (พฤติกรรมเดิมของ H5P)

ทดสอบแล้วใน Chromium: ไฟล์ MP4 ทั้ง 10 ชนิด บนหน้าเว็บธรรมดา (`examples/server`) และใน Moodle 5.1

**ยังไม่ได้ทดสอบ**: YouTube, Vimeo, HLS, Safari/Firefox, มือถือจริง, มากกว่าหนึ่งตัวเล่นในหน้าเดียว

---

## สร้างจากซอร์ส

```bash
npm ci && npm run build && npm test
```

`dist/` ถูก commit ไว้ ลูกค้าที่แค่ใช้งานไม่ต้องมี Node

หลังแก้ `src/` หรือ `styles/` ให้ build ปลั๊กอิน Moodle ใหม่ด้วย เพราะมันสร้างจากซอร์สเดียวกัน:

```bash
cd ../moodle/plugins/mod_kaiiv && npm run build && node tests/smoke.js
```

## ลิขสิทธิ์

เปลือกของตัวเล่นพัฒนาต่อจาก H5P Interactive Video และ h5p-lib-controls (MIT)
ไฟล์ build รวม jQuery และ jQuery UI (MIT) และ Font Awesome Free (ฟอนต์ SIL OFL 1.1)
ประกาศลิขสิทธิ์ทั้งหมดอยู่ใน `thirdparty/` — **ต้องส่งต่อโฟลเดอร์นี้ไปด้วยเสมอ**
