// What the player says, in the two languages it ships with.
//
// The same sentences as mod_kaiiv's language files, so a lesson reads the same
// inside Moodle and out of it. A page can replace any of them through the
// `strings` option, or add a language by passing a whole set.
//
// The keys are the renderers' names for them, not Moodle's: `continuelabel`
// because `continue` is a reserved word, `notsaved` without its error: prefix
// because a colon is not usable as a property name.

const en = {
    correct: 'Correct',
    wrong: 'Not quite',
    tryagain: 'Try again',
    continuelabel: 'Continue',
    submitanswer: 'Submit',
    youranswer: 'Your answer',
    istrue: 'True',
    isfalse: 'False',
    pickatleastone: 'Tick at least one answer before submitting.',
    unsupported: 'This kind of interaction cannot be shown by this version of the player.',
    interactionword: 'Interaction',
    notsaved: 'Your answer could not be marked, so it has not been recorded and it has '
        + 'not used up an attempt. Try again in a moment.',
    noattemptsleft: 'You have no attempts left on this question.',
    alreadycorrect: 'You have already answered this question correctly.',
    play: 'Play',
    pause: 'Pause',
    back10: 'Back 10s',
    types: {
        choice: 'One answer',
        multichoice: 'Several answers',
        truefalse: 'True or false',
        shorttext: 'Typed answer',
        blanks: 'Fill in the blanks',
        dragtext: 'Drag the words',
        marktheword: 'Mark the words',
        label: 'Caption',
        image: 'Image',
        link: 'Link',
    },
};

const th = {
    correct: 'ถูกต้อง',
    wrong: 'ยังไม่ถูก',
    tryagain: 'ลองใหม่',
    continuelabel: 'เล่นต่อ',
    submitanswer: 'ส่งคำตอบ',
    youranswer: 'คำตอบของคุณ',
    istrue: 'ถูก',
    isfalse: 'ผิด',
    pickatleastone: 'เลือกอย่างน้อยหนึ่งข้อก่อนส่งคำตอบ',
    unsupported: 'ตัวเล่นรุ่นนี้แสดงรายการชนิดนี้ไม่ได้',
    interactionword: 'รายการบนไทม์ไลน์',
    notsaved: 'ตรวจคำตอบของคุณไม่ได้ ระบบจึงยังไม่บันทึก และไม่ได้ตัดสิทธิ์ตอบของคุณไป '
        + 'ลองอีกครั้งในอีกสักครู่',
    noattemptsleft: 'คุณใช้สิทธิ์ตอบข้อนี้ครบแล้ว',
    alreadycorrect: 'คุณตอบข้อนี้ถูกไปแล้ว',
    play: 'เล่น',
    pause: 'หยุด',
    back10: 'ถอย 10 วิ',
    types: {
        choice: 'ตอบข้อเดียว',
        multichoice: 'ตอบหลายข้อ',
        truefalse: 'ถูกหรือผิด',
        shorttext: 'พิมพ์คำตอบ',
        blanks: 'เติมคำในช่องว่าง',
        dragtext: 'ลากคำไปเติม',
        marktheword: 'เลือกคำในข้อความ',
        label: 'ข้อความ',
        image: 'รูปภาพ',
        link: 'ลิงก์',
    },
};

export const LANGUAGES = {en, th};

/**
 * One language's strings with the page's overrides on top.
 *
 * @param {String} lang 'en', 'th', or anything else, which falls back to English
 * @param {Object} overrides
 * @returns {Object}
 */
export const resolveStrings = (lang, overrides) => {
    const base = LANGUAGES[lang] || en;
    const given = overrides || {};
    return {
        ...en,
        ...base,
        ...given,
        types: {...en.types, ...base.types, ...(given.types || {})},
    };
};
