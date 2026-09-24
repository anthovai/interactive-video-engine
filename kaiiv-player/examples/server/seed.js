// Put one sample lesson in data.json, with one interaction of every kind.
//
//     KAIIV_API_KEY=... node seed.js path/to/video.mp4
//
// Through author(), the same path an authoring screen would take, so the
// answers are split out by the engine and stored apart from the content —
// data.json never holds an asterisk-marked sentence.
//
// The video is yours: any MP4 of a minute or so. It is copied to
// media/lesson.mp4, which is not committed.

'use strict';

const fs = require('fs');
const path = require('path');
const {author, load, save} = require('./server');

const video = process.argv[2];
if (!video || !fs.existsSync(video)) {
    process.stderr.write('usage: node seed.js path/to/video.mp4\n');
    process.exit(1);
}
fs.mkdirSync(path.join(__dirname, 'media'), {recursive: true});
fs.copyFileSync(video, path.join(__dirname, 'media/lesson.mp4'));

const ITEMS = [
    {start: 3, type: 'choice', label: 'คำถามที่ 1', feedback: 'ระบบตรวจว่ามีคนอยู่หน้ากล้องเป็นระยะ',
        authored: {text: 'ระหว่างเรียนบทเรียนที่มีการเฝ้าดู ผู้เรียนต้องทำอย่างไร', options: [
            {text: 'อยู่หน้ากล้องตลอดเวลา', correct: true},
            {text: 'ปิดกล้องได้ถ้าเสียงยังดังอยู่', correct: false},
            {text: 'สลับไปหน้าอื่นได้ตามต้องการ', correct: false}]}},
    {start: 8, type: 'truefalse', label: 'คำถามที่ 2', feedback: 'ทุกครั้งที่ออกจากหน้าต่างถูกบันทึกเป็นหลักฐาน',
        authored: {text: 'การออกจากหน้าต่างบทเรียนถูกบันทึกไว้', correct: true}},
    {start: 13, type: 'multichoice', label: 'คำถามที่ 3',
        feedback: 'สิ่งที่บันทึกคือเหตุการณ์ ไม่ใช่ภาพหรือลักษณะของผู้เรียน',
        authored: {text: 'ระบบบันทึกเหตุการณ์ใดไว้เป็นหลักฐานบ้าง (เลือกได้หลายข้อ)', options: [
            {text: 'ออกจากหน้าต่างบทเรียน', correct: true},
            {text: 'ไม่พบใบหน้าหน้ากล้อง', correct: true},
            {text: 'สีเสื้อของผู้เรียน', correct: false},
            {text: 'เวลาที่เริ่มและจบบทเรียน', correct: true}]}},
    {start: 18, type: 'shorttext', label: 'คำถามที่ 4', feedback: 'เก็บเป็นเวกเตอร์ตัวเลข ไม่ใช่รูปถ่าย',
        authored: {text: 'ข้อมูลใบหน้าถูกเก็บไว้ในรูปแบบใด (ตอบเป็นคำเดียว)',
            accept: ['เวกเตอร์', 'vector', 'embedding']}},
    {start: 23, type: 'blanks', label: 'คำถามที่ 5', feedback: 'ทั้งสองอย่างเป็นการเทียบตัวเลข ไม่ใช่การเทียบรูป',
        authored: {text: 'เติมคำในช่องว่าง',
            lines: ['ระบบเก็บใบหน้าเป็น *เวกเตอร์/vector* แล้วเทียบด้วยค่า *ระยะห่าง/distance*']}},
    {start: 28, type: 'label', label: 'ข้อความ',
        authored: {text: 'ส่วนถัดไปเป็นขั้นตอนการยืนยันตัวตนก่อนเริ่มทำข้อสอบ เตรียมบัตรประจำตัวและตรวจว่ามีแสงพอ'}},
    {start: 33, type: 'dragtext', label: 'คำถามที่ 6',
        feedback: 'ลำดับของขั้นตอนคือสิ่งที่ทำให้การปลอมด้วยรูปถ่ายไม่ผ่าน',
        authored: {text: 'ลากคำไปเติมให้ถูกช่อง',
            lines: ['ระบบ *ตรวจจับ* ใบหน้าก่อน แล้วจึง *เทียบ* กับที่ลงทะเบียนไว้']}},
    {start: 38, type: 'marktheword', label: 'คำถามที่ 7', feedback: 'สองคำนี้คือสิ่งที่ระบบเก็บ ส่วนที่เหลือไม่ได้เก็บ',
        authored: {text: 'เลือกคำที่เป็นสิ่งที่ระบบบันทึกไว้',
            passage: 'ระบบบันทึก *เหตุการณ์* และ *เวลา* แต่ไม่บันทึก เสียง หรือ หน้าจอ ของผู้เรียน'}},
    {start: 43, end: 48, type: 'image', display: 'button', label: 'แผนผังขั้นตอน',
        authored: {url: '/media/diagram.svg', alt: 'แผนผังขั้นตอนการยืนยันตัวตน',
            caption: 'ขั้นตอนการยืนยันตัวตนก่อนเข้าสอบ'}},
    {start: 48, end: 53, type: 'link', display: 'button', label: 'นโยบายข้อมูล',
        authored: {url: 'https://example.com/', title: 'อ่านนโยบายการใช้ข้อมูลส่วนบุคคล'}},
];

(async () => {
    const data = load();
    data.lessons['1'] = {
        id: '1',
        title: 'บทเรียนตัวอย่าง',
        lang: 'th',
        video: {provider: 'file', src: '/media/lesson.mp4'},
        rules: {mustanswer: true, allowreview: true, maxattempts: 0},
        interactions: [],
    };
    // A fresh lesson has no record against it yet.
    data.responses = data.responses.filter((r) => r.lesson !== '1');
    Object.keys(data.progress).filter((k) => k.startsWith('1:')).forEach((k) => delete data.progress[k]);
    save(data);

    for (const item of ITEMS) {
        const result = await author('1', item);
        process.stdout.write(`  ${item.type} at ${item.start}s: `
            + (result.ok ? 'saved' : `FAILED ${result.error} ${result.detail || ''}`) + '\n');
        if (!result.ok) {
            process.exitCode = 1;
        }
    }
})();
